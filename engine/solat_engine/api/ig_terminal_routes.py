"""
IG-normalized terminal API routes.

Canonical route surface for account, market data, and order flows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.api.execution_routes import get_execution_router, get_ig_client
from solat_engine.catalog.seed import get_seed_instruments
from solat_engine.catalog.store import CatalogueStore
from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.config import Settings, get_settings_dep
from solat_engine.data.aggregate import aggregate_bars
from solat_engine.data.ig_history import IGHistoryFetcher
from solat_engine.data.models import SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.execution.models import OrderIntent, OrderSide, OrderType
from solat_engine.execution.router import ExecutionRouter
from solat_engine.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["IG Terminal"])

_catalogue_store: CatalogueStore | None = None
_parquet_store: ParquetStore | None = None
_DEBUG_LOG_PATH = Path("/Users/joseph/Projects/SOLAT_ALL/solat_v3.1/.cursor/debug.log")
_bars_fallback_blocked_until: dict[str, datetime] = {}
_bars_403_cooloff_until: dict[str, datetime] = {}


def get_catalogue_store(settings: Settings = Depends(get_settings_dep)) -> CatalogueStore:
    global _catalogue_store
    if _catalogue_store is None:
        _catalogue_store = CatalogueStore()
    seed_items = get_seed_instruments()
    prefer_spreadbet = settings.ig_required_account_type.upper() == "SPREADBET"
    if _catalogue_store.count() == 0:
        _catalogue_store.bootstrap(seed_items, is_live=settings.is_live or prefer_spreadbet)
    if prefer_spreadbet:
        _catalogue_store.sync_epics_from_seed(seed_items, is_live=True)
    return _catalogue_store


def get_parquet_store(settings: Settings = Depends(get_settings_dep)) -> ParquetStore:
    global _parquet_store
    if _parquet_store is None or _parquet_store._data_dir != settings.data_dir:
        _parquet_store = ParquetStore(settings.data_dir)
    return _parquet_store


def _catalog_maps(catalogue: CatalogueStore) -> tuple[dict[str, Any], dict[str, Any]]:
    items = catalogue.load()
    by_symbol = {item.symbol.upper(): item for item in items}
    by_epic = {item.epic: item for item in items if item.epic}
    return by_symbol, by_epic


def _resolve_symbol_and_epic(
    *,
    symbol: str | None,
    epic: str | None,
    by_symbol: dict[str, Any],
    by_epic: dict[str, Any],
) -> tuple[str, str]:
    if epic:
        item = by_epic.get(epic)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Unknown epic: {epic}")
        return item.symbol, epic
    if symbol:
        item = by_symbol.get(symbol.upper())
        if item is None or not item.epic:
            raise HTTPException(status_code=404, detail=f"Unknown symbol or missing epic: {symbol}")
        return item.symbol, item.epic
    raise HTTPException(status_code=400, detail="Either symbol or epic is required")


class AccountResponse(BaseModel):
    account_id: str
    account_type: str | None = None
    balance: float
    equity: float
    margin: float
    available: float
    currency: str | None = None
    status: str | None = None


class PositionsResponse(BaseModel):
    positions: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class OrdersResponse(BaseModel):
    orders: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class UniverseResponse(BaseModel):
    instruments: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class QuotesResponse(BaseModel):
    quotes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    count: int = 0
    failed: list[dict[str, str]] = Field(default_factory=list)


class BarsResponse(BaseModel):
    epic: str
    symbol: str
    tf: str
    bars: list[dict[str, Any]]
    count: int
    start: str | None = None
    end: str | None = None
    requested_limit: int | None = None
    coverage_pct: float | None = None
    source: str | None = None


def _to_float(value: Decimal | float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _estimate_fetch_start(tf: SupportedTimeframe, limit: int, end_ts: datetime) -> datetime:
    # Keep fetch windows bounded so chart requests remain responsive.
    minutes_per_bar = {
        SupportedTimeframe.M1: 1,
        SupportedTimeframe.M5: 5,
        SupportedTimeframe.M15: 15,
        SupportedTimeframe.M30: 30,
        SupportedTimeframe.H1: 60,
        SupportedTimeframe.H4: 240,
    }[tf]
    lookback_minutes = max(minutes_per_bar * limit, minutes_per_bar * 200)
    return end_ts - timedelta(minutes=lookback_minutes)


def _minimum_expected_bars(tf: SupportedTimeframe, requested_limit: int) -> int:
    baseline = {
        SupportedTimeframe.M1: 1440,
        SupportedTimeframe.M5: 1000,
        SupportedTimeframe.M15: 800,
        SupportedTimeframe.M30: 600,
        SupportedTimeframe.H1: 500,
        SupportedTimeframe.H4: 300,
    }[tf]
    return min(requested_limit, baseline)


def _contains_403_warning(warnings: list[str]) -> bool:
    return any("status 403" in w for w in warnings)


def _minimum_backfill_span(tf: SupportedTimeframe) -> timedelta:
    # Keep a lower bound for window step-down during 403 adaptation.
    return timedelta(minutes=tf.minutes * 20)


class MarketOrderRequest(BaseModel):
    symbol: str | None = None
    epic: str | None = None
    direction: str
    size: float = Field(gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = "manual_market_order"


class WorkingOrderRequest(BaseModel):
    symbol: str | None = None
    epic: str | None = None
    direction: str
    size: float = Field(gt=0)
    order_type: str = Field(description="LIMIT or STOP")
    level: float = Field(gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None
    good_till_date: str | None = None


class AmendPositionRequest(BaseModel):
    stop_loss: float | None = None
    take_profit: float | None = None


@router.get("/account", response_model=AccountResponse)
async def get_account(
    settings: Settings = Depends(get_settings_dep),
    client: Any = Depends(get_ig_client),
) -> AccountResponse:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    account = await client.get_account_details_with_balance()
    balance = float(account.get("balance") or 0.0)
    pnl = float(account.get("profit_loss") or 0.0)
    margin = float(account.get("deposit") or 0.0)
    available = float(account.get("available") or 0.0)
    return AccountResponse(
        account_id=str(account.get("account_id") or ""),
        account_type=account.get("account_type"),
        balance=balance,
        equity=balance + pnl,
        margin=margin,
        available=available,
        currency=account.get("currency"),
        status=account.get("status"),
    )


@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    client: Any = Depends(get_ig_client),
) -> PositionsResponse:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    _, by_epic = _catalog_maps(catalogue)
    raw = await client.list_positions()
    out: list[dict[str, Any]] = []
    for row in raw:
        pos = row.get("position", {})
        market = row.get("market", {})
        epic = market.get("epic") or pos.get("epic")
        mapped = by_epic.get(epic)
        out.append(
            {
                "deal_id": pos.get("dealId"),
                "symbol": mapped.symbol if mapped else None,
                "epic": epic,
                "direction": pos.get("direction"),
                "size": float(pos.get("size") or 0.0),
                "entry_price": float(pos.get("openLevel") or 0.0),
                "current_price": float(market.get("bid") or market.get("offer") or 0.0),
                "stop_level": pos.get("stopLevel"),
                "limit_level": pos.get("limitLevel"),
                "created_date": pos.get("createdDateUTC") or pos.get("createdDate"),
                "market_status": market.get("marketStatus"),
            }
        )
    return PositionsResponse(positions=out, count=len(out))


@router.get("/orders", response_model=OrdersResponse)
async def get_orders(
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    client: Any = Depends(get_ig_client),
) -> OrdersResponse:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    _, by_epic = _catalog_maps(catalogue)
    raw = await client.get_working_orders()
    out: list[dict[str, Any]] = []
    for row in raw:
        order_data = row.get("workingOrderData", row)
        market_data = row.get("marketData", {})
        epic = order_data.get("epic") or market_data.get("epic")
        mapped = by_epic.get(epic)
        out.append(
            {
                "deal_id": order_data.get("dealId"),
                "symbol": mapped.symbol if mapped else None,
                "epic": epic,
                "direction": order_data.get("direction"),
                "size": float(order_data.get("size") or 0.0),
                "order_type": order_data.get("orderType"),
                "level": order_data.get("level"),
                "stop_level": order_data.get("stopDistance") or order_data.get("stopLevel"),
                "limit_level": order_data.get("limitDistance") or order_data.get("limitLevel"),
                "good_till_date": order_data.get("goodTillDate"),
                "currency": order_data.get("currencyCode"),
            }
        )
    return OrdersResponse(orders=out, count=len(out))


@router.get("/universe", response_model=UniverseResponse)
async def get_universe(
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    store: ParquetStore = Depends(get_parquet_store),
    tf: str = Query(default="15m"),
) -> UniverseResponse:
    try:
        timeframe = SupportedTimeframe(tf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {e}")
    summaries = store.get_summary(timeframe=timeframe)
    rows_by_symbol = {str(row.get("symbol", "")).upper(): int(row.get("row_count", 0) or 0) for row in summaries}
    baseline = _minimum_expected_bars(timeframe, 1000)
    items = [item for item in catalogue.load() if item.epic]
    out = [
        {
            "symbol": item.symbol,
            "epic": item.epic,
            "display_name": item.display_name,
            "asset_class": item.asset_class.value,
            "min_size": _to_float(item.dealing_rules.min_deal_size) if item.dealing_rules else None,
            "pip_value": _to_float(item.pip_size),
            "is_enriched": item.is_enriched,
            "history_row_count": rows_by_symbol.get(item.symbol.upper(), 0),
            "history_score": round(
                min(rows_by_symbol.get(item.symbol.upper(), 0) / max(baseline, 1), 1.0) * 100.0,
                1,
            ),
            "history_supported": rows_by_symbol.get(item.symbol.upper(), 0) >= max(50, timeframe.minutes * 4),
        }
        for item in items
    ]

    out.sort(
        key=lambda row: (
            str(row.get("asset_class", "")),
            -float(row.get("history_score", 0.0)),
            str(row.get("symbol", "")),
        )
    )
    return UniverseResponse(instruments=out, count=len(out))


@router.get("/quotes", response_model=QuotesResponse)
async def get_quotes(
    epics: str | None = Query(default=None),
    symbols: str | None = Query(default=None),
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    client: Any = Depends(get_ig_client),
) -> QuotesResponse:
    # region agent log H1 H4 endpoint entry
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "id": f"log_{int(datetime.now().timestamp()*1000)}_quotes_entry",
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "location": "ig_terminal_routes.py:get_quotes:entry",
                        "message": "get_quotes called",
                        "data": {"epics": epics, "symbols": symbols},
                        "runId": "pre-fix",
                        "hypothesisId": "H1_H4",
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    by_symbol, by_epic = _catalog_maps(catalogue)
    target_epics: list[str] = []
    if epics:
        target_epics.extend([e.strip() for e in epics.split(",") if e.strip()])
    if symbols:
        for sym in [s.strip().upper() for s in symbols.split(",") if s.strip()]:
            item = by_symbol.get(sym)
            if item and item.epic:
                target_epics.append(item.epic)
    if not target_epics:
        target_epics = list(by_epic.keys())[:40]
    # Deduplicate preserving order.
    target_epics = list(dict.fromkeys(target_epics))

    quotes: dict[str, dict[str, Any]] = {}
    failed: list[dict[str, str]] = []
    for epic in target_epics:
        try:
            details = await client.get_market_details(epic)
            if details is None or details.snapshot is None:
                failed.append({"epic": epic, "error": "No market snapshot"})
                continue
            snap = details.snapshot
            bid = snap.get("bid")
            ask = snap.get("offer")
            if bid is None or ask is None:
                failed.append({"epic": epic, "error": "Bid/ask unavailable"})
                continue
            mapped = by_epic.get(epic)
            mid = (float(bid) + float(ask)) / 2.0
            quotes[epic] = {
                "epic": epic,
                "symbol": mapped.symbol if mapped else None,
                "bid": float(bid),
                "ask": float(ask),
                "last": mid,
                "time": snap.get("updateTime"),
                "market_status": snap.get("marketStatus"),
            }
            # region agent log H1 quote populated
            try:
                with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {
                                "id": f"log_{int(datetime.now().timestamp()*1000)}_quotes_value",
                                "timestamp": int(datetime.now().timestamp() * 1000),
                                "location": "ig_terminal_routes.py:get_quotes:value",
                                "message": "quote snapshot mapped",
                                "data": {
                                    "epic": epic,
                                    "symbol": mapped.symbol if mapped else None,
                                    "bid": float(bid),
                                    "ask": float(ask),
                                    "market_status": snap.get("marketStatus"),
                                },
                                "runId": "pre-fix",
                                "hypothesisId": "H1",
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
        except Exception as e:  # noqa: BLE001
            failed.append({"epic": epic, "error": str(e)})

    return QuotesResponse(quotes=quotes, count=len(quotes), failed=failed)


@router.get("/bars", response_model=BarsResponse)
async def get_bars(
    epic: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    tf: str = Query(default="1h"),
    limit: int = Query(default=1000, ge=1, le=10000),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    store: ParquetStore = Depends(get_parquet_store),
    client: Any = Depends(get_ig_client),
) -> BarsResponse:
    requested_limit = limit
    by_symbol, by_epic = _catalog_maps(catalogue)
    resolved_symbol, resolved_epic = _resolve_symbol_and_epic(
        symbol=symbol, epic=epic, by_symbol=by_symbol, by_epic=by_epic
    )
    try:
        timeframe = SupportedTimeframe(tf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {e}")
    bars = store.read_bars(
        symbol=resolve_storage_symbol(resolved_symbol),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )
    source = "cache"
    # IG-first data path for charts:
    # if local cache is empty OR sparse and IG is configured, fetch from IG and hydrate cache.
    fallback_key = f"{resolved_symbol}:{tf}"
    blocked_until = _bars_fallback_blocked_until.get(fallback_key)
    blocked_403_until = _bars_403_cooloff_until.get(fallback_key)
    now_utc = datetime.now(UTC)
    fallback_blocked = (blocked_until is not None and blocked_until > now_utc) or (
        blocked_403_until is not None and blocked_403_until > now_utc
    )
    cached_count = len(bars)
    expected_min = _minimum_expected_bars(timeframe, requested_limit)
    sparse_without_explicit_window = start is None and end is None and cached_count < expected_min
    needs_backfill = cached_count == 0 or sparse_without_explicit_window
    if needs_backfill and settings.has_ig_credentials and timeframe.is_ig_native and not fallback_blocked:
        try:
            fetcher = IGHistoryFetcher(client)
            if start is not None or end is not None:
                end_ts = _coerce_utc(end or datetime.now(UTC))
                start_ts = _coerce_utc(start or _estimate_fetch_start(timeframe, limit, end_ts))
                fetched, _warnings = await fetcher.fetch_by_date_range(
                    epic=resolved_epic,
                    symbol=resolved_symbol,
                    resolution=timeframe,
                    start=start_ts,
                    end=end_ts,
                )
            else:
                # Sparse cache remediation:
                # - bounded attempts
                # - on 403, step down window size (do not keep widening)
                # - for higher TFs, fetch 1m + derive for denser recovery.
                target = expected_min
                end_ts = now_utc
                start_ts = _coerce_utc(_estimate_fetch_start(timeframe, target, end_ts))
                window_span = end_ts - start_ts
                min_span = _minimum_backfill_span(timeframe)
                cursor_end = end_ts
                merged_target_by_ts: dict[datetime, Any] = {}
                merged_m1_by_ts: dict[datetime, Any] = {}
                hit_403 = False
                max_attempts = 8

                for _attempt in range(max_attempts):
                    if len(merged_target_by_ts) >= target:
                        break
                    window_start = cursor_end - window_span
                    fetched_m1_chunk: list[Any] = []
                    fetched_chunk, warnings_tf = await fetcher.fetch_by_date_range(
                        epic=resolved_epic,
                        symbol=resolved_symbol,
                        resolution=timeframe,
                        start=window_start,
                        end=cursor_end,
                    )
                    has_403 = _contains_403_warning(warnings_tf)
                    for bar in fetched_chunk:
                        merged_target_by_ts[bar.timestamp_utc] = bar

                    if timeframe != SupportedTimeframe.M1:
                        fetched_m1_chunk, warnings_m1 = await fetcher.fetch_by_date_range(
                            epic=resolved_epic,
                            symbol=resolved_symbol,
                            resolution=SupportedTimeframe.M1,
                            start=window_start,
                            end=cursor_end,
                        )
                        has_403 = has_403 or _contains_403_warning(warnings_m1)
                        for bar in fetched_m1_chunk:
                            merged_m1_by_ts[bar.timestamp_utc] = bar
                        if fetched_m1_chunk:
                            for bar in aggregate_bars(fetched_m1_chunk, timeframe):
                                merged_target_by_ts[bar.timestamp_utc] = bar

                    if has_403:
                        # Adaptive step-down: shrink window and retry nearby range first.
                        if window_span <= min_span:
                            hit_403 = True
                            break
                        window_span = max(window_span / 2, min_span)
                        continue

                    fetched_any = bool(fetched_chunk) or bool(fetched_m1_chunk)
                    if not fetched_any:
                        cursor_end = window_start
                        continue

                    earliest = min(
                        [b.timestamp_utc for b in fetched_chunk]
                        + [b.timestamp_utc for b in fetched_m1_chunk]
                    )
                    cursor_end = earliest

                fetched = sorted(merged_target_by_ts.values(), key=lambda b: b.timestamp_utc)
                if merged_m1_by_ts:
                    fetched = sorted(
                        [*merged_m1_by_ts.values(), *fetched],
                        key=lambda b: (b.timeframe.value, b.timestamp_utc),
                    )
                if hit_403:
                    _bars_403_cooloff_until[fallback_key] = now_utc + timedelta(minutes=5)
                else:
                    _bars_403_cooloff_until.pop(fallback_key, None)
            if fetched:
                store.write_bars(fetched, run_id="ig_terminal_bars_fallback")
                _bars_fallback_blocked_until.pop(fallback_key, None)
                source = "ig_fallback" if cached_count == 0 else "cache+ig_fallback"
                bars = store.read_bars(
                    symbol=resolve_storage_symbol(resolved_symbol),
                    timeframe=timeframe,
                    start=start,
                    end=end,
                    limit=limit,
                )
        except Exception as exc:  # noqa: BLE001
            _bars_fallback_blocked_until[fallback_key] = datetime.now(UTC) + timedelta(seconds=60)
            logger.warning(
                "IG bars fallback failed for %s/%s (%s): %s",
                resolved_symbol,
                tf,
                resolved_epic,
                exc,
            )
    payload = [
        {
            "ts": b.timestamp_utc.isoformat(),
            "o": b.open,
            "h": b.high,
            "l": b.low,
            "c": b.close,
            "v": b.volume,
        }
        for b in bars
    ]
    coverage_pct = (
        round((len(payload) / requested_limit) * 100.0, 2) if requested_limit > 0 else None
    )
    return BarsResponse(
        epic=resolved_epic,
        symbol=resolved_symbol,
        tf=tf,
        bars=payload,
        count=len(payload),
        start=payload[0]["ts"] if payload else None,
        end=payload[-1]["ts"] if payload else None,
        requested_limit=requested_limit,
        coverage_pct=coverage_pct,
        source=source,
    )


@router.post("/orders/market")
async def place_market_order(
    request: MarketOrderRequest,
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> dict[str, Any]:
    # DEMO-first safety posture in this pass.
    if exec_router.state.mode.value != "DEMO":
        raise HTTPException(status_code=403, detail="Market orders are DEMO-only in this phase")
    if not exec_router.state.demo_arm_enabled:
        raise HTTPException(status_code=400, detail="DEMO arm must be enabled")
    if not exec_router.state.connected:
        raise HTTPException(status_code=400, detail="Execution is not connected")

    by_symbol, by_epic = _catalog_maps(catalogue)
    symbol, _ = _resolve_symbol_and_epic(
        symbol=request.symbol, epic=request.epic, by_symbol=by_symbol, by_epic=by_epic
    )
    side = request.direction.upper()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="direction must be BUY or SELL")
    intent = OrderIntent(
        symbol=symbol,
        side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
        size=request.size,
        order_type=OrderType.MARKET,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        bot="manual",
        reason_codes=[request.reason or "manual_market_order"],
    )
    ack = await exec_router.route_intent(intent)
    return {
        "ok": ack.status.value in {"FILLED", "ACKNOWLEDGED", "PENDING"},
        "status": ack.status.value,
        "intent_id": str(ack.intent_id),
        "deal_id": ack.deal_id,
        "error": ack.rejection_reason,
    }


@router.post("/orders/working")
async def place_working_order(
    request: WorkingOrderRequest,
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    settings: Settings = Depends(get_settings_dep),
    client: Any = Depends(get_ig_client),
) -> dict[str, Any]:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    by_symbol, by_epic = _catalog_maps(catalogue)
    _, resolved_epic = _resolve_symbol_and_epic(
        symbol=request.symbol, epic=request.epic, by_symbol=by_symbol, by_epic=by_epic
    )
    direction = request.direction.upper()
    order_type = request.order_type.upper()
    if direction not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="direction must be BUY or SELL")
    if order_type not in {"LIMIT", "STOP"}:
        raise HTTPException(status_code=400, detail="order_type must be LIMIT or STOP")
    return await client.place_working_order(
        epic=resolved_epic,
        direction=direction,
        size=request.size,
        order_type=order_type,
        level=request.level,
        stop_level=request.stop_loss,
        limit_level=request.take_profit,
        good_till_date=request.good_till_date,
    )


@router.put("/positions/{deal_id}")
async def amend_position(
    deal_id: str,
    request: AmendPositionRequest,
    settings: Settings = Depends(get_settings_dep),
    client: Any = Depends(get_ig_client),
) -> dict[str, Any]:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    if request.stop_loss is None and request.take_profit is None:
        raise HTTPException(status_code=400, detail="At least one of stop_loss/take_profit is required")
    return await client.amend_position(
        deal_id=deal_id,
        stop_level=request.stop_loss,
        limit_level=request.take_profit,
    )


@router.delete("/positions/{deal_id}")
async def close_position(
    deal_id: str,
    size: float | None = Query(default=None, gt=0),
    settings: Settings = Depends(get_settings_dep),
    client: Any = Depends(get_ig_client),
) -> dict[str, Any]:
    if not settings.has_ig_credentials:
        raise HTTPException(status_code=400, detail="IG credentials not configured")
    positions = await client.list_positions()
    target = None
    for row in positions:
        pos = row.get("position", {})
        if pos.get("dealId") == deal_id:
            target = pos
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Position not found: {deal_id}")
    direction = (target.get("direction") or "").upper()
    close_direction = "SELL" if direction == "BUY" else "BUY"
    return await client.close_position(
        deal_id=deal_id,
        direction=close_direction,
        size=size,
    )
