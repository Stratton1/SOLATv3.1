"""
Chart overlay API routes.

Provides server-side computation of indicators and signal markers
for the chart terminal UI.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from solat_engine.api.data_routes import get_parquet_store
from solat_engine.api.rate_limit import (
    get_overlay_cache,
    get_overlay_rate_limiter,
    get_signals_cache,
    get_signals_rate_limiter,
)
from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.data.models import SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.strategies.indicators import (
    atr,
    bollinger_bands,
    ema,
    ichimoku,
    macd,
    rsi,
    sma,
    stochastic,
)

router = APIRouter(prefix="/chart", tags=["Chart"])
logger = get_logger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================


class OverlayRequest(BaseModel):
    """Request for chart overlay computation."""

    symbol: str = Field(..., description="Instrument symbol")
    timeframe: str = Field(default="1m", description="Bar timeframe")
    indicators: list[str] = Field(
        ...,
        description="Indicators to compute (e.g., ema_20, sma_50, ichimoku)",
        min_length=1,
        max_length=10,
    )
    start: datetime | None = Field(
        default=None, description="Start time (UTC)"
    )
    end: datetime | None = Field(
        default=None, description="End time (UTC)"
    )
    limit: int = Field(
        default=500,
        description="Max bars to include",
        ge=50,
        le=2000,
    )


class OverlayData(BaseModel):
    """Single indicator overlay data."""

    name: str
    type: str  # "line", "band", "cloud", "histogram"
    data: list[dict[str, Any]]


class OverlayResponse(BaseModel):
    """Response with computed overlays."""

    symbol: str
    timeframe: str
    bars: list[dict[str, Any]]
    overlays: list[OverlayData]
    count: int


class SignalMarker(BaseModel):
    """A signal marker for the chart."""

    timestamp: str
    type: str  # "entry_long", "entry_short", "exit_long", "exit_short"
    price: float
    label: str | None = None
    strategy: str | None = None
    trade_id: str | None = None


class SignalsRequest(BaseModel):
    """Request for signal markers."""

    symbol: str = Field(..., description="Instrument symbol")
    timeframe: str = Field(default="1m", description="Bar timeframe")
    start: datetime | None = Field(
        default=None, description="Start time (UTC)"
    )
    end: datetime | None = Field(
        default=None, description="End time (UTC)"
    )
    strategy: str | None = Field(
        default=None, description="Filter by strategy name"
    )


class SignalsResponse(BaseModel):
    """Response with signal markers."""

    symbol: str
    markers: list[SignalMarker]
    count: int


# =============================================================================
# Indicator Parsing
# =============================================================================


def parse_indicator(indicator: str) -> tuple[str, dict[str, Any]]:
    """
    Parse indicator string into name and parameters.

    Examples:
        "ema_20" -> ("ema", {"period": 20})
        "sma_50" -> ("sma", {"period": 50})
        "rsi_14" -> ("rsi", {"period": 14})
        "macd" -> ("macd", {})
        "bb_20_2" -> ("bollinger", {"period": 20, "std_dev": 2.0})
        "ichimoku" -> ("ichimoku", {})
        "stoch_14_3" -> ("stochastic", {"k_period": 14, "d_period": 3})
        "atr_14" -> ("atr", {"period": 14})
    """
    parts = indicator.lower().split("_")
    name = parts[0]

    if name in ("ema", "sma", "rsi", "atr"):
        period = int(parts[1]) if len(parts) > 1 else 14
        return name, {"period": period}

    if name == "macd":
        fast = int(parts[1]) if len(parts) > 1 else 12
        slow = int(parts[2]) if len(parts) > 2 else 26
        signal = int(parts[3]) if len(parts) > 3 else 9
        return "macd", {"fast": fast, "slow": slow, "signal": signal}

    if name in ("bb", "bollinger"):
        period = int(parts[1]) if len(parts) > 1 else 20
        std = float(parts[2]) if len(parts) > 2 else 2.0
        return "bollinger", {"period": period, "std_dev": std}

    if name == "ichimoku":
        return "ichimoku", {}

    if name in ("stoch", "stochastic"):
        k_period = int(parts[1]) if len(parts) > 1 else 14
        d_period = int(parts[2]) if len(parts) > 2 else 3
        return "stochastic", {"k_period": k_period, "d_period": d_period}

    raise ValueError(f"Unknown indicator: {indicator}")


def compute_indicator(
    name: str,
    params: dict[str, Any],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    timestamps: list[str],
) -> OverlayData:
    """Compute a single indicator and return overlay data."""

    if name == "ema":
        period = params["period"]
        values = ema(closes, period)
        return OverlayData(
            name=f"EMA({period})",
            type="line",
            data=[
                {"ts": ts, "value": v}
                for ts, v in zip(timestamps, values, strict=True)
            ],
        )

    if name == "sma":
        period = params["period"]
        values = sma(closes, period)
        return OverlayData(
            name=f"SMA({period})",
            type="line",
            data=[
                {"ts": ts, "value": v}
                for ts, v in zip(timestamps, values, strict=True)
            ],
        )

    if name == "rsi":
        period = params["period"]
        values = rsi(closes, period)
        return OverlayData(
            name=f"RSI({period})",
            type="oscillator",
            data=[
                {"ts": ts, "value": v}
                for ts, v in zip(timestamps, values, strict=True)
            ],
        )

    if name == "atr":
        period = params["period"]
        values = atr(highs, lows, closes, period)
        return OverlayData(
            name=f"ATR({period})",
            type="line",
            data=[
                {"ts": ts, "value": v}
                for ts, v in zip(timestamps, values, strict=True)
            ],
        )

    if name == "macd":
        macd_line, signal_line, histogram = macd(
            closes,
            params.get("fast", 12),
            params.get("slow", 26),
            params.get("signal", 9),
        )
        return OverlayData(
            name="MACD",
            type="macd",
            data=[
                {"ts": ts, "macd": m, "signal": s, "histogram": h}
                for ts, m, s, h in zip(
                    timestamps, macd_line, signal_line, histogram, strict=True
                )
            ],
        )

    if name == "bollinger":
        period = params["period"]
        std_dev = params["std_dev"]
        upper, middle, lower = bollinger_bands(closes, period, std_dev)
        return OverlayData(
            name=f"BB({period},{std_dev})",
            type="band",
            data=[
                {"ts": ts, "upper": up, "middle": mid, "lower": lo}
                for ts, up, mid, lo in zip(
                    timestamps, upper, middle, lower, strict=True
                )
            ],
        )

    if name == "ichimoku":
        result = ichimoku(highs, lows, closes)
        return OverlayData(
            name="Ichimoku",
            type="cloud",
            data=[
                {
                    "ts": ts,
                    "tenkan": result["tenkan"][i],
                    "kijun": result["kijun"][i],
                    "senkou_a": result["senkou_a"][i],
                    "senkou_b": result["senkou_b"][i],
                    "chikou": result["chikou"][i],
                }
                for i, ts in enumerate(timestamps)
            ],
        )

    if name == "stochastic":
        k_values, d_values = stochastic(
            highs,
            lows,
            closes,
            params.get("k_period", 14),
            params.get("d_period", 3),
        )
        return OverlayData(
            name=f"Stoch({params.get('k_period', 14)},{params.get('d_period', 3)})",
            type="oscillator",
            data=[
                {"ts": ts, "k": k, "d": d}
                for ts, k, d in zip(timestamps, k_values, d_values, strict=True)
            ],
        )

    raise ValueError(f"Unknown indicator: {name}")


# =============================================================================
# Routes
# =============================================================================


@router.post("/overlays", response_model=OverlayResponse)
async def compute_overlays(
    request: OverlayRequest,
    http_request: Request,
    store: ParquetStore = Depends(get_parquet_store),
) -> OverlayResponse:
    """
    Compute chart overlays (indicators) for given bars.

    Rate limited: 1 request/sec, cached for 5s.

    Supports:
    - EMA/SMA with configurable period (e.g., ema_20, sma_50)
    - RSI (e.g., rsi_14)
    - MACD (e.g., macd or macd_12_26_9)
    - Bollinger Bands (e.g., bb_20_2)
    - Ichimoku Cloud
    - Stochastic (e.g., stoch_14_3)
    - ATR (e.g., atr_14)

    All computations are done on the engine (not frontend) to ensure
    consistency with strategy calculations.
    """
    # Rate limit check (returns 429 if exceeded)
    rate_limiter = get_overlay_rate_limiter()
    client_id = rate_limiter.get_client_id(http_request)
    rate_limiter.check(client_id)

    # Check cache first
    cache = get_overlay_cache()
    cache_key_args = (
        request.symbol,
        request.timeframe,
        tuple(sorted(request.indicators)),
        request.start.isoformat() if request.start else None,
        request.end.isoformat() if request.end else None,
        request.limit,
    )
    cached = cache.get(*cache_key_args)
    if cached is not None:
        logger.debug("Overlay cache hit for %s", request.symbol)
        return cached
    # Parse timeframe
    try:
        tf = SupportedTimeframe(request.timeframe)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe: {request.timeframe}",
        )

    # Resolve storage symbol
    storage_symbol = resolve_storage_symbol(request.symbol)

    # Get bars from store
    bars = store.read_bars(
        symbol=storage_symbol,
        timeframe=tf,
        start=request.start,
        end=request.end,
        limit=request.limit,
    )

    if not bars:
        return OverlayResponse(
            symbol=request.symbol,
            timeframe=request.timeframe,
            bars=[],
            overlays=[],
            count=0,
        )

    # Extract price series
    opens = [bar.open for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    closes = [bar.close for bar in bars]
    timestamps = [bar.timestamp_utc.isoformat() for bar in bars]

    # Compute each indicator
    overlays: list[OverlayData] = []
    for indicator in request.indicators:
        try:
            name, params = parse_indicator(indicator)
            overlay = compute_indicator(
                name, params, opens, highs, lows, closes, timestamps
            )
            overlays.append(overlay)
        except ValueError as e:
            logger.warning("Invalid indicator %s: %s", indicator, e)
        except Exception as e:
            logger.error("Error computing %s: %s", indicator, e)

    # Convert bars to response format
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

    response = OverlayResponse(
        symbol=request.symbol,
        timeframe=request.timeframe,
        bars=bar_dicts,
        overlays=overlays,
        count=len(bars),
    )

    # Cache the response
    cache.set(response, *cache_key_args)

    return response


@router.get("/overlays/{symbol}")
async def get_overlays(
    http_request: Request,
    symbol: str,
    timeframe: str = Query(default="1m", description="Bar timeframe"),
    indicators: str = Query(
        default="ema_20,ema_50",
        description="Comma-separated indicators",
    ),
    limit: int = Query(default=500, ge=50, le=2000),
    store: ParquetStore = Depends(get_parquet_store),
) -> OverlayResponse:
    """
    GET version of overlay computation.

    Rate limited: 1 request/sec, cached for 5s.
    """
    indicator_list = [i.strip() for i in indicators.split(",") if i.strip()]

    request = OverlayRequest(
        symbol=symbol,
        timeframe=timeframe,
        indicators=indicator_list,
        limit=limit,
    )

    return await compute_overlays(request, http_request, store=store)


@router.post("/signals", response_model=SignalsResponse)
async def get_signals(
    request: SignalsRequest,
    http_request: Request,
) -> SignalsResponse:
    """
    Get signal markers (entry/exit points) for chart display.

    Rate limited: 1 request/sec, cached for 10s.

    Returns executed trades as markers for visualization.
    Integrates with backtest results and live execution history.
    """
    # Rate limit check (returns 429 if exceeded)
    rate_limiter = get_signals_rate_limiter()
    client_id = rate_limiter.get_client_id(http_request)
    rate_limiter.check(client_id)

    # Check cache first
    cache = get_signals_cache()
    cache_key_args = (
        request.symbol,
        request.timeframe,
        request.start.isoformat() if request.start else None,
        request.end.isoformat() if request.end else None,
        request.strategy,
    )
    cached = cache.get(*cache_key_args)
    if cached is not None:
        logger.debug("Signals cache hit for %s", request.symbol)
        return cached

    # TODO: Integrate with execution history and backtest results
    # For now, return empty list - markers come from execution events
    response = SignalsResponse(
        symbol=request.symbol,
        markers=[],
        count=0,
    )

    # Cache the response
    cache.set(response, *cache_key_args)

    return response


@router.get("/signals/{symbol}")
async def get_signals_simple(
    http_request: Request,
    symbol: str,
    timeframe: str = Query(default="1m"),
    strategy: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> SignalsResponse:
    """
    GET version of signals query.

    Rate limited: 1 request/sec, cached for 10s.
    """
    request = SignalsRequest(
        symbol=symbol,
        timeframe=timeframe,
        strategy=strategy,
    )

    return await get_signals(request, http_request)


@router.get("/available-indicators")
async def list_available_indicators() -> dict[str, Any]:
    """
    List all available indicators and their parameters.

    Useful for UI dropdown population.
    """
    return {
        "indicators": [
            {
                "name": "ema",
                "display": "EMA",
                "description": "Exponential Moving Average",
                "params": {"period": {"type": "int", "default": 20, "min": 2, "max": 200}},
                "example": "ema_20",
            },
            {
                "name": "sma",
                "display": "SMA",
                "description": "Simple Moving Average",
                "params": {"period": {"type": "int", "default": 50, "min": 2, "max": 200}},
                "example": "sma_50",
            },
            {
                "name": "rsi",
                "display": "RSI",
                "description": "Relative Strength Index",
                "params": {"period": {"type": "int", "default": 14, "min": 2, "max": 50}},
                "example": "rsi_14",
                "separate_pane": True,
            },
            {
                "name": "macd",
                "display": "MACD",
                "description": "Moving Average Convergence Divergence",
                "params": {
                    "fast": {"type": "int", "default": 12},
                    "slow": {"type": "int", "default": 26},
                    "signal": {"type": "int", "default": 9},
                },
                "example": "macd_12_26_9",
                "separate_pane": True,
            },
            {
                "name": "bollinger",
                "display": "Bollinger Bands",
                "description": "Bollinger Bands with configurable std dev",
                "params": {
                    "period": {"type": "int", "default": 20},
                    "std_dev": {"type": "float", "default": 2.0},
                },
                "example": "bb_20_2",
            },
            {
                "name": "ichimoku",
                "display": "Ichimoku Cloud",
                "description": "Ichimoku Kinko Hyo indicator",
                "params": {},
                "example": "ichimoku",
            },
            {
                "name": "stochastic",
                "display": "Stochastic",
                "description": "Stochastic Oscillator",
                "params": {
                    "k_period": {"type": "int", "default": 14},
                    "d_period": {"type": "int", "default": 3},
                },
                "example": "stoch_14_3",
                "separate_pane": True,
            },
            {
                "name": "atr",
                "display": "ATR",
                "description": "Average True Range",
                "params": {"period": {"type": "int", "default": 14}},
                "example": "atr_14",
                "separate_pane": True,
            },
        ]
    }
