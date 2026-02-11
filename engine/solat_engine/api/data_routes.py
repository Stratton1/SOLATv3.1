"""
Data API routes for historical bars and sync operations.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.api.ig_routes import get_ig_client
from solat_engine.backtest.sweep_utils import auto_derive_timeframe
from solat_engine.catalog.store import CatalogueStore
from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.config import Settings, get_settings_dep
from solat_engine.data.models import (
    DataSyncRequest,
    SupportedTimeframe,
)
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus
from solat_engine.runtime.jobs import get_job_runner

router = APIRouter(prefix="/data", tags=["Data"])
logger = get_logger(__name__)

# Lazy-initialized stores
_parquet_store: ParquetStore | None = None
_catalogue_store: CatalogueStore | None = None


def get_settings() -> Settings:
    """Compatibility helper for tests and dependency injection."""
    return get_settings_dep()


def get_parquet_store(settings: Settings = Depends(get_settings_dep)) -> ParquetStore:
    """Get or create Parquet store singleton."""
    global _parquet_store
    # In tests, if settings.data_dir changed, we MUST recreate the store
    if _parquet_store is None or _parquet_store._data_dir != settings.data_dir:
        _parquet_store = ParquetStore(settings.data_dir)
    return _parquet_store


def get_catalogue_store() -> CatalogueStore:
    """Get or create catalogue store singleton."""
    global _catalogue_store
    if _catalogue_store is None:
        _catalogue_store = CatalogueStore()
    return _catalogue_store


# =============================================================================
# Request/Response Models
# =============================================================================


class SyncRequest(BaseModel):
    """Request to sync historical data."""

    symbols: list[str] = Field(..., description="List of symbols to sync", min_length=1)
    timeframes: list[str] = Field(
        default=["1m"],
        description="Timeframes to fetch (1m is base, others derived)",
    )
    start: datetime = Field(..., description="Start time (UTC)")
    end: datetime = Field(..., description="End time (UTC)")
    enrich_missing_epics: bool = Field(
        default=True,
        description="Attempt to enrich catalogue for symbols without epics",
    )
    force: bool = Field(
        default=False,
        description="Force re-fetch even if data exists",
    )


class SyncResponse(BaseModel):
    """Response from sync operation."""

    ok: bool = True
    run_id: str
    message: str = ""
    per_symbol_results: list[dict[str, Any]] = Field(default_factory=list)
    total_bars_fetched: int = 0
    total_bars_stored: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    """Response for data summary."""

    summaries: list[dict[str, Any]]
    total_symbols: int
    total_bars: int


class BarsResponse(BaseModel):
    """Response for bars query."""

    symbol: str
    timeframe: str
    bars: list[dict[str, Any]]
    count: int
    start: str | None = None
    end: str | None = None


# =============================================================================
# Routes
# =============================================================================


@router.post("/sync", response_model=SyncResponse)
async def sync_data(
    request: SyncRequest,
    settings: Settings = Depends(get_settings_dep),
    store: ParquetStore = Depends(get_parquet_store),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
) -> SyncResponse:
    """
    Sync historical data from IG for specified symbols.

    Fetches 1m base data and aggregates to requested timeframes.
    Runs in background - returns immediately with run_id.
    Progress events are streamed via WebSocket.
    """
    # Validate timeframes first (before checking credentials)
    try:
        timeframes = [SupportedTimeframe(tf) for tf in request.timeframes]
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {e}. Valid values: 1m, 5m, 15m, 30m, 1h, 4h (30m is derived from 1m only)",
        )

    # 30m is derived-only (IG has no MINUTE_30); sync only IG-native timeframes
    timeframes_ig = [tf for tf in timeframes if tf.is_ig_native]
    if len(timeframes_ig) < len(timeframes):
        logger.info(
            "Sync: 30m skipped (derived from 1m only); syncing timeframes: %s",
            [tf.value for tf in timeframes_ig],
        )
    timeframes = timeframes_ig
    if not timeframes:
        raise HTTPException(
            status_code=400,
            detail="No IG-fetchable timeframes. 30m is derived from 1m only; include 1m, 5m, 15m, 1h, or 4h.",
        )

    # Check if IG is configured
    if not settings.has_ig_credentials:
        return SyncResponse(
            ok=False,
            run_id="",
            message="IG credentials not configured - cannot sync from IG",
            errors=["IG_API_KEY, IG_USERNAME, and IG_PASSWORD must be set"],
        )

    # Create internal request
    sync_request = DataSyncRequest(
        symbols=request.symbols,
        timeframes=timeframes,
        start=request.start,
        end=request.end,
        enrich_missing_epics=request.enrich_missing_epics,
        force=request.force,
    )

    try:
        ig_client = get_ig_client(settings=settings)
    except Exception as e:
        logger.warning("Could not get IG client: %s", e)
        return SyncResponse(
            ok=False,
            run_id="",
            message="Failed to initialize IG client",
            errors=[str(e)],
        )

    # Start background job
    runner = get_job_runner()
    run_id = await runner.start_sync_job(
        request=sync_request,
        ig_client=ig_client,
        catalogue_store=catalogue,
        parquet_store=store,
    )

    return SyncResponse(
        ok=True,
        run_id=run_id,
        message=f"Sync job started for {len(request.symbols)} symbols",
    )


@router.get("/sync/{run_id}", response_model=SyncResponse)
async def get_sync_result(run_id: str) -> SyncResponse:
    """
    Get result of a sync job by run_id.

    Returns current state - may be in progress or completed.
    """
    runner = get_job_runner()

    # Check if still active
    if await runner.is_job_active(run_id):
        return SyncResponse(
            ok=True,
            run_id=run_id,
            message="Job is still running",
        )

    # Get result
    result = await runner.get_job_result(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Sync job '{run_id}' not found")

    return SyncResponse(
        ok=result.ok,
        run_id=result.run_id,
        message="Job completed",
        per_symbol_results=[
            {
                "symbol": r.symbol,
                "epic": r.epic,
                "success": r.success,
                "bars_fetched": r.bars_fetched,
                "bars_stored": r.bars_stored,
                "bars_deduplicated": r.bars_deduplicated,
                "error": r.error,
                "warnings": r.warnings,
            }
            for r in result.per_symbol_results
        ],
        total_bars_fetched=result.total_bars_fetched,
        total_bars_stored=result.total_bars_stored,
        warnings=result.warnings,
        errors=result.errors,
    )


@router.get("/summary", response_model=SummaryResponse)
async def data_summary(
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    timeframe: str | None = Query(default=None, description="Filter by timeframe"),
    store: ParquetStore = Depends(get_parquet_store),
) -> SummaryResponse:
    """
    Get summary of stored historical data.

    Works without IG credentials (reads local Parquet).
    """
    # Parse timeframe if provided
    tf_filter = None
    if timeframe:
        try:
            tf_filter = SupportedTimeframe(timeframe)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}",
            )

    # Resolve storage symbol for lookup
    storage_symbol = resolve_storage_symbol(symbol) if symbol else None
    summaries = store.get_summary(symbol=storage_symbol, timeframe=tf_filter)

    # Map back to catalogue symbols if aliased
    from solat_engine.catalog.symbols import STORAGE_ALIAS_MAP
    REVERSE_ALIAS_MAP = {v: k for k, v in STORAGE_ALIAS_MAP.items()}

    for s in summaries:
        if s["symbol"] in REVERSE_ALIAS_MAP:
            s["original_symbol"] = s["symbol"]  # Keep storage key as well
            s["symbol"] = REVERSE_ALIAS_MAP[s["symbol"]]

    total_bars = sum(s.get("row_count", 0) for s in summaries)
    unique_symbols = len({s.get("symbol") for s in summaries})

    return SummaryResponse(
        summaries=summaries,
        total_symbols=unique_symbols,
        total_bars=total_bars,
    )


@router.get("/availability")
async def data_availability(
    store: ParquetStore = Depends(get_parquet_store)
) -> dict[str, list[str]]:
    """
    Get a compact map of available timeframes per instrument symbol.

    Returns:
        Dict mapping symbol to list of timeframe strings.
    """
    summaries = store.get_summary()

    availability: dict[str, list[str]] = {}

    # Reverse alias map for mapping back to catalogue symbols
    from solat_engine.catalog.symbols import STORAGE_ALIAS_MAP
    REVERSE_ALIAS_MAP = {v: k for k, v in STORAGE_ALIAS_MAP.items()}

    for s in summaries:
        raw_symbol = s.get("symbol")
        timeframe = s.get("timeframe")

        if not raw_symbol or not timeframe:
            continue

        # Map back to catalogue symbol if aliased
        symbol = REVERSE_ALIAS_MAP.get(raw_symbol, raw_symbol)

        if symbol not in availability:
            availability[symbol] = []

        if timeframe not in availability[symbol]:
            availability[symbol].append(timeframe)

    return availability


@router.get("/availability/detail")
async def data_availability_detail(
    store: ParquetStore = Depends(get_parquet_store),
) -> list[dict]:
    """
    Get detailed data availability per symbol per timeframe.

    Returns per-symbol per-timeframe: min_ts, max_ts, bars_count.
    """
    summaries = store.get_summary()

    from solat_engine.catalog.symbols import STORAGE_ALIAS_MAP
    REVERSE_ALIAS_MAP = {v: k for k, v in STORAGE_ALIAS_MAP.items()}

    details = []
    for s in summaries:
        raw_symbol = s.get("symbol")
        timeframe = s.get("timeframe")
        if not raw_symbol or not timeframe:
            continue

        symbol = REVERSE_ALIAS_MAP.get(raw_symbol, raw_symbol)
        details.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_count": s.get("row_count", 0),
            "min_ts": s.get("start_ts"),
            "max_ts": s.get("end_ts"),
        })

    return details


@router.get("/bars", response_model=BarsResponse)
async def get_bars(
    symbol: str = Query(..., description="Instrument symbol"),
    timeframe: str = Query(default="1m", description="Bar timeframe"),
    start: datetime | None = Query(default=None, description="Start time (UTC)"),
    end: datetime | None = Query(default=None, description="End time (UTC)"),
    limit: int = Query(default=1000, ge=1, le=10000, description="Max rows to return"),
    settings: Settings = Depends(get_settings_dep),
    store: ParquetStore = Depends(get_parquet_store),
) -> BarsResponse:
    """
    Query stored bars for a symbol.

    Works without IG credentials (reads local Parquet).
    """
    # Parse timeframe
    try:
        tf = SupportedTimeframe(timeframe)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {timeframe}. Valid values: 1m, 5m, 15m, 30m, 1h, 4h",
        )

    # Resolve storage symbol for lookup
    storage_symbol = resolve_storage_symbol(symbol)

    # Apply max rows limit from config
    limit = min(limit, settings.history_max_rows_per_call)

    bars = store.read_bars(
        symbol=storage_symbol,
        timeframe=tf,
        start=start,
        end=end,
        limit=limit,
    )

    # Convert to dicts for response
    # Use shortened keys for consistency with chart_routes
    bar_dicts = [
        {
            "ts": bar.timestamp_utc.isoformat(),
            "o": bar.open,
            "h": bar.high,
            "l": bar.low,
            "c": bar.close,
            "v": bar.volume,
        }
        for bar in bars
    ]

    return BarsResponse(
        symbol=symbol,
        timeframe=timeframe,
        bars=bar_dicts,
        count=len(bar_dicts),
        start=bar_dicts[0]["ts"] if bar_dicts else (start.isoformat() if start else None),
        end=bar_dicts[-1]["ts"] if bar_dicts else (end.isoformat() if end else None),
    )


@router.delete("/bars/{symbol}/{timeframe}")
async def delete_bars(
    symbol: str,
    timeframe: str,
    store: ParquetStore = Depends(get_parquet_store),
) -> dict[str, Any]:
    """
    Delete stored bars for a symbol/timeframe.

    Use with caution - data will be permanently deleted.
    """
    # Parse timeframe
    try:
        tf = SupportedTimeframe(timeframe)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {timeframe}",
        )

    # Resolve storage symbol
    storage_symbol = resolve_storage_symbol(symbol)
    deleted = store.clear_partition(storage_symbol, tf)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {symbol}/{timeframe}",
        )

    return {"ok": True, "deleted": f"{symbol}/{timeframe}"}


@router.post("/sync/quick")
async def quick_sync(
    days: int = Query(default=30, ge=1, le=365, description="Days of history to fetch"),
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
    store: ParquetStore = Depends(get_parquet_store),
) -> SyncResponse:
    """
    Quick sync: fetch last N days for all seed symbols with 1m + derived timeframes.

    Convenience endpoint for common sync operation.
    """
    if not settings.has_ig_credentials:
        return SyncResponse(
            ok=False,
            run_id="",
            message="IG credentials not configured",
            errors=["IG_API_KEY, IG_USERNAME, and IG_PASSWORD must be set"],
        )

    # Get seed symbols from catalogue
    items = catalogue.load()

    # Filter to enriched items (those with epics)
    enriched_symbols = [item.symbol for item in items if item.is_enriched and item.epic]

    if not enriched_symbols:
        return SyncResponse(
            ok=False,
            run_id="",
            message="No enriched instruments in catalogue. Run /catalog/bootstrap first.",
            errors=["No instruments with IG epics found"],
        )

    # Create request
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)

    request = SyncRequest(
        symbols=enriched_symbols,
        timeframes=["1m", "5m", "15m", "1h", "4h"],
        start=start,
        end=end,
        enrich_missing_epics=False,
        force=False,
    )

    return await sync_data(request, settings=settings, store=store, catalogue=catalogue)


# =============================================================================
# Artefact Index
# =============================================================================


class ArtefactIndexResponse(BaseModel):
    """Response for artefact index scan."""

    bars: list[dict[str, Any]] = Field(default_factory=list)
    backtests: list[dict[str, Any]] = Field(default_factory=list)
    sweeps: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = ""


@router.get("/artefacts/index", response_model=ArtefactIndexResponse)
async def artefacts_index(
    settings: Settings = Depends(get_settings_dep),
    store: ParquetStore = Depends(get_parquet_store),
) -> ArtefactIndexResponse:
    """
    Scan disk for bars, backtests, and sweep artefacts.

    Reads only JSON manifests (no Parquet reads) for speed.
    Limits to 100 items per category, sorted desc by date.
    """
    data_dir = settings.data_dir
    limit = 100

    # --- Bars: reuse store.get_summary() ---
    bars_summaries = store.get_summary()
    from solat_engine.catalog.symbols import STORAGE_ALIAS_MAP
    reverse_alias = {v: k for k, v in STORAGE_ALIAS_MAP.items()}

    bars = []
    for s in bars_summaries:
        raw_sym = s.get("symbol", "")
        bars.append({
            "symbol": reverse_alias.get(raw_sym, raw_sym),
            "timeframe": s.get("timeframe", ""),
            "row_count": s.get("row_count", 0),
            "start_ts": s.get("start_ts"),
            "end_ts": s.get("end_ts"),
        })

    # --- Backtests: scan manifest.json files ---
    backtests_dir = data_dir / "backtests"
    backtests: list[dict[str, Any]] = []
    if backtests_dir.exists():
        for manifest_path in sorted(backtests_dir.glob("*/manifest.json"), reverse=True):
            if len(backtests) >= limit:
                break
            try:
                manifest = json.loads(manifest_path.read_text())
                backtests.append({
                    "run_id": manifest.get("run_id", manifest_path.parent.name),
                    "created_at": manifest.get("created_at", ""),
                    "symbols": manifest.get("symbols", []),
                    "bots": manifest.get("bots", []),
                    "timeframe": manifest.get("timeframe", ""),
                    "sharpe": manifest.get("sharpe"),
                    "total_trades": manifest.get("total_trades", 0),
                    "path": str(manifest_path.parent),
                })
            except Exception:
                continue

    # --- Sweeps: scan manifests + top_picks ---
    sweeps_dir = data_dir / "sweep_results"
    sweeps: list[dict[str, Any]] = []
    if sweeps_dir.exists():
        for sweep_dir in sorted(sweeps_dir.iterdir(), reverse=True):
            if len(sweeps) >= limit:
                break
            if not sweep_dir.is_dir():
                continue
            entry: dict[str, Any] = {
                "sweep_id": sweep_dir.name,
                "path": str(sweep_dir),
            }
            manifest_path = sweep_dir / "preflight.json"
            if manifest_path.exists():
                try:
                    pf = json.loads(manifest_path.read_text())
                    entry["scope"] = pf.get("scope", pf.get("effective_scope", ""))
                    entry["total_combos"] = pf.get("valid_combos", 0)
                    entry["generated_at"] = pf.get("generated_at", "")
                except Exception:
                    pass
            top_picks_path = sweep_dir / "top_picks.json"
            if top_picks_path.exists():
                try:
                    tp = json.loads(top_picks_path.read_text())
                    picks = tp.get("picks", [])
                    if picks:
                        entry["top_sharpe"] = max(
                            (p.get("metrics", {}).get("sharpe", 0) for p in picks),
                            default=0,
                        )
                except Exception:
                    pass
            sweeps.append(entry)

    return ArtefactIndexResponse(
        bars=bars[:limit],
        backtests=backtests,
        sweeps=sweeps,
        generated_at=datetime.now(UTC).isoformat(),
    )


# =============================================================================
# Derive All Timeframes
# =============================================================================

TARGET_DERIVE_TIMEFRAMES = ["15m", "30m", "1h", "4h"]

# Module-level state for derive jobs
_derive_jobs: dict[str, asyncio.Task] = {}
_derive_results: dict[str, dict[str, Any]] = {}


class DeriveAllResponse(BaseModel):
    """Response from derive-all operation."""

    ok: bool = True
    run_id: str = ""
    message: str = ""
    total_symbols: int = 0
    target_timeframes: list[str] = Field(default_factory=list)


@router.post("/derive-all", response_model=DeriveAllResponse)
async def derive_all(
    settings: Settings = Depends(get_settings_dep),
    store: ParquetStore = Depends(get_parquet_store),
) -> DeriveAllResponse:
    """
    Derive 15m/30m/1h/4h bars from existing 1m data for all symbols.

    Runs as a background task. Progress events are streamed via WebSocket.
    """
    # Find symbols with 1m data
    summaries = store.get_summary(timeframe=SupportedTimeframe.M1)
    symbols_with_1m = [s["symbol"] for s in summaries if s.get("row_count", 0) > 0]

    if not symbols_with_1m:
        return DeriveAllResponse(
            ok=False,
            message="No symbols with 1m data found. Sync 1m data first.",
        )

    run_id = f"derive_{uuid4().hex[:8]}"

    async def _run_derive() -> None:
        event_bus = get_event_bus()
        await event_bus.publish(Event(
            type=EventType.DERIVE_STARTED,
            run_id=run_id,
            data={"total_symbols": len(symbols_with_1m), "timeframes": TARGET_DERIVE_TIMEFRAMES},
        ))

        derived_count = 0
        errors: list[str] = []
        total_pairs = len(symbols_with_1m) * len(TARGET_DERIVE_TIMEFRAMES)

        for i, symbol in enumerate(symbols_with_1m):
            for tf in TARGET_DERIVE_TIMEFRAMES:
                try:
                    loop = asyncio.get_event_loop()
                    ok = await loop.run_in_executor(
                        None, auto_derive_timeframe, settings.data_dir, symbol, tf,
                    )
                    if ok:
                        derived_count += 1
                except Exception as e:
                    errors.append(f"{symbol}/{tf}: {e}")

                await event_bus.publish(Event(
                    type=EventType.DERIVE_PROGRESS,
                    run_id=run_id,
                    data={
                        "symbol": symbol,
                        "timeframe": tf,
                        "completed": i * len(TARGET_DERIVE_TIMEFRAMES) + TARGET_DERIVE_TIMEFRAMES.index(tf) + 1,
                        "total": total_pairs,
                    },
                ))

        _derive_results[run_id] = {
            "derived_count": derived_count,
            "errors": errors,
        }

        await event_bus.publish(Event(
            type=EventType.DERIVE_COMPLETED,
            run_id=run_id,
            data={"derived_count": derived_count, "errors": errors},
        ))

    task = asyncio.create_task(_run_derive())
    _derive_jobs[run_id] = task

    return DeriveAllResponse(
        ok=True,
        run_id=run_id,
        message=f"Deriving {len(TARGET_DERIVE_TIMEFRAMES)} timeframes for {len(symbols_with_1m)} symbols",
        total_symbols=len(symbols_with_1m),
        target_timeframes=TARGET_DERIVE_TIMEFRAMES,
    )
