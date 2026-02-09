"""
Diagnostics API routes.

Provides system health and performance metrics:
- Memory usage and cache stats
- WebSocket connection info
- Rate limiter usage
- Stream health status
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from solat_engine.api.rate_limit import (
    get_overlay_cache,
    get_overlay_rate_limiter,
    get_signals_cache,
    get_signals_rate_limiter,
)
from solat_engine.logging import get_logger
from solat_engine.market_data.publisher import get_publisher
from solat_engine.runtime.ws_throttle import get_ws_throttler

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])
logger = get_logger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class MemoryDiagnostics(BaseModel):
    """Memory usage diagnostics."""

    caches: dict[str, Any] = Field(default_factory=dict)
    estimated_mb: float = 0.0
    timestamp: str


class WsDiagnostics(BaseModel):
    """WebSocket diagnostics."""

    connected_clients: int = 0
    messages_per_sec_in: float = 0.0
    messages_per_sec_out: float = 0.0
    throttler_stats: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class RateLimiterDiagnostics(BaseModel):
    """Rate limiter diagnostics."""

    overlay: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class StreamHealthDiagnostics(BaseModel):
    """Stream health diagnostics."""

    mode: str = "unknown"
    connected: bool = False
    stale: bool = False
    fallback_active: bool = False
    stream_failures: int = 0
    fallback_count: int = 0
    last_quote_ts: str | None = None
    backfill_stats: dict[str, Any] = Field(default_factory=dict)
    publisher_stats: dict[str, int] = Field(default_factory=dict)
    timestamp: str


class FullDiagnostics(BaseModel):
    """Complete diagnostics snapshot."""

    memory: MemoryDiagnostics
    websocket: WsDiagnostics
    rate_limiters: RateLimiterDiagnostics
    stream_health: StreamHealthDiagnostics
    timestamp: str


# =============================================================================
# Global state references (set by main.py)
# =============================================================================

# These are set by main.py during startup
_ws_clients_ref: list | None = None
_market_controller_ref: Any = None


def set_ws_clients_ref(clients: list) -> None:
    """Set reference to WebSocket clients list."""
    global _ws_clients_ref
    _ws_clients_ref = clients


def set_market_controller_ref(controller: Any) -> None:
    """Set reference to market data controller."""
    global _market_controller_ref
    _market_controller_ref = controller


# =============================================================================
# Routes
# =============================================================================


@router.get("/memory", response_model=MemoryDiagnostics)
async def get_memory_diagnostics() -> MemoryDiagnostics:
    """
    Get memory usage diagnostics.

    Returns cache sizes and estimated memory usage.
    """
    overlay_cache = get_overlay_cache()
    signals_cache = get_signals_cache()

    # Estimate memory (rough estimates)
    # Assume ~1KB per cache entry, ~100 bytes per quote
    estimated_mb = 0.0

    caches = {
        "overlay_cache": overlay_cache.get_stats(),
        "signals_cache": signals_cache.get_stats(),
    }

    # Add estimates
    estimated_mb += caches["overlay_cache"]["current_entries"] * 1.0 / 1024  # ~1KB/entry
    estimated_mb += caches["signals_cache"]["current_entries"] * 0.5 / 1024  # ~0.5KB/entry

    return MemoryDiagnostics(
        caches=caches,
        estimated_mb=round(estimated_mb, 2),
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/ws", response_model=WsDiagnostics)
async def get_ws_diagnostics() -> WsDiagnostics:
    """
    Get WebSocket diagnostics.

    Returns connected client count and message rates.
    """
    connected_clients = len(_ws_clients_ref) if _ws_clients_ref else 0

    throttler = get_ws_throttler()
    throttler_stats = throttler.get_stats()

    return WsDiagnostics(
        connected_clients=connected_clients,
        messages_per_sec_in=0.0,  # Would need tracking
        messages_per_sec_out=0.0,  # Would need tracking
        throttler_stats=throttler_stats,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/rate_limiters", response_model=RateLimiterDiagnostics)
async def get_rate_limiter_diagnostics() -> RateLimiterDiagnostics:
    """
    Get rate limiter diagnostics.

    Returns current window usage for overlay/signals.
    """
    overlay_limiter = get_overlay_rate_limiter()
    signals_limiter = get_signals_rate_limiter()

    return RateLimiterDiagnostics(
        overlay=overlay_limiter.get_stats(),
        signals=signals_limiter.get_stats(),
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/stream_health", response_model=StreamHealthDiagnostics)
async def get_stream_health_diagnostics() -> StreamHealthDiagnostics:
    """
    Get stream health diagnostics.

    Returns Lightstreamer status, fallback state, and backfill history.
    """
    publisher = get_publisher()
    publisher_stats = publisher.get_stats()

    # Get controller stats if available
    controller_data = {}
    if _market_controller_ref is not None:
        try:
            status = _market_controller_ref.get_status()
            stats = _market_controller_ref.stats

            controller_data = {
                "mode": status.mode.value,
                "connected": status.connected,
                "stale": status.stale,
                "fallback_active": stats.current_mode.value == "poll",
                "stream_failures": stats.stream_failures,
                "fallback_count": stats.fallback_count,
                "last_quote_ts": (
                    stats.last_quote_ts.isoformat() if stats.last_quote_ts else None
                ),
                "backfill_stats": {
                    "backfills_triggered": stats.backfills_triggered,
                    "bars_backfilled": stats.bars_backfilled,
                },
            }
        except Exception as e:
            logger.warning("Error getting controller stats: %s", e)

    return StreamHealthDiagnostics(
        mode=controller_data.get("mode", "unknown"),
        connected=controller_data.get("connected", False),
        stale=controller_data.get("stale", False),
        fallback_active=controller_data.get("fallback_active", False),
        stream_failures=controller_data.get("stream_failures", 0),
        fallback_count=controller_data.get("fallback_count", 0),
        last_quote_ts=controller_data.get("last_quote_ts"),
        backfill_stats=controller_data.get("backfill_stats", {}),
        publisher_stats=publisher_stats,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/all", response_model=FullDiagnostics)
async def get_all_diagnostics() -> FullDiagnostics:
    """
    Get complete diagnostics snapshot.

    Combines all diagnostics endpoints into a single response.
    """
    memory = await get_memory_diagnostics()
    ws = await get_ws_diagnostics()
    rate_limiters = await get_rate_limiter_diagnostics()
    stream_health = await get_stream_health_diagnostics()

    return FullDiagnostics(
        memory=memory,
        websocket=ws,
        rate_limiters=rate_limiters,
        stream_health=stream_health,
        timestamp=datetime.now(UTC).isoformat(),
    )
