"""
Market data API routes for realtime price streaming.

Provides endpoints for:
- Subscribing to market data streams
- Checking stream status
- Getting latest quotes
"""

from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.catalog.store import CatalogueStore
from solat_engine.config import Settings, get_settings_dep
from solat_engine.logging import get_logger
from solat_engine.market_data.models import (
    MarketDataMode,
    MarketStreamStatus,
    Quote,
)
from solat_engine.market_data.publisher import get_publisher

router = APIRouter(prefix="/market", tags=["Market Data"])
logger = get_logger(__name__)

# Lazy-initialized stores
_catalogue_store: CatalogueStore | None = None


def get_catalogue_store() -> CatalogueStore:
    """Get or create catalogue store singleton."""
    global _catalogue_store
    if _catalogue_store is None:
        _catalogue_store = CatalogueStore()
    return _catalogue_store


# =============================================================================
# Service State
# =============================================================================


class MarketSourceProtocol(Protocol):
    """Protocol for market data sources (streaming or polling)."""

    @property
    def is_running(self) -> bool: ...

    def get_status(self) -> MarketStreamStatus: ...

    async def subscribe(self, symbol: str, epic: str) -> None: ...

    async def unsubscribe(self, symbol: str) -> None: ...

    async def unsubscribe_all(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class MarketDataService:
    """
    Market data service state.

    Manages the streaming/polling source lifecycle.
    """

    def __init__(self) -> None:
        self._source: MarketSourceProtocol | None = None
        self._mode: MarketDataMode = MarketDataMode.POLL
        self._subscriptions: dict[str, str] = {}  # symbol -> epic
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def mode(self) -> MarketDataMode:
        return self._mode

    def set_source(self, source: MarketSourceProtocol, mode: MarketDataMode) -> None:
        self._source = source
        self._mode = mode

    async def start(self) -> None:
        if self._source and not self._started:
            await self._source.start()
            self._started = True

    async def stop(self) -> None:
        if self._source and self._started:
            await self._source.stop()
            self._started = False

    async def subscribe(self, symbol: str, epic: str) -> None:
        if self._source:
            await self._source.subscribe(symbol, epic)
            self._subscriptions[symbol] = epic

    async def unsubscribe(self, symbol: str) -> None:
        if self._source and symbol in self._subscriptions:
            await self._source.unsubscribe(symbol)
            del self._subscriptions[symbol]

    async def unsubscribe_all(self) -> None:
        if self._source:
            await self._source.unsubscribe_all()
            self._subscriptions.clear()

    def get_status(self) -> MarketStreamStatus:
        if self._source:
            return self._source.get_status()
        return MarketStreamStatus(connected=False, mode=self._mode)

    def get_subscriptions(self) -> dict[str, str]:
        return self._subscriptions.copy()


# Global service instance
_market_service: MarketDataService | None = None


def get_market_service() -> MarketDataService:
    """Get market data service singleton."""
    global _market_service
    if _market_service is None:
        _market_service = MarketDataService()
    return _market_service


def reset_market_service() -> None:
    """Reset market service (for testing)."""
    global _market_service
    _market_service = None


# =============================================================================
# Request/Response Models
# =============================================================================


class SubscribeRequest(BaseModel):
    """Request to subscribe to market data."""

    symbols: list[str] = Field(
        ...,
        description="Symbols to subscribe to",
        min_length=1,
        max_length=20,  # Limit concurrent subscriptions
    )
    mode: str = Field(
        default="stream",
        description="Connection mode: stream (Lightstreamer) or poll (REST)",
    )
    cadence_ms: int = Field(
        default=1500,
        description="Poll interval in ms (poll mode only)",
        ge=500,
        le=10000,
    )


class SubscribeResponse(BaseModel):
    """Response from subscribe operation."""

    ok: bool = True
    subscribed: list[str] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
    mode: str = "stream"
    message: str = ""
    warnings: list[str] = Field(default_factory=list)


class UnsubscribeRequest(BaseModel):
    """Request to unsubscribe from market data."""

    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols to unsubscribe from (empty = all)",
    )


class UnsubscribeResponse(BaseModel):
    """Response from unsubscribe operation."""

    ok: bool = True
    unsubscribed: list[str] = Field(default_factory=list)
    message: str = ""


class StatusResponse(BaseModel):
    """Market data status response."""

    connected: bool
    mode: str
    stale: bool
    subscriptions: list[str]
    last_tick_ts: str | None
    reconnect_attempts: int
    last_error: str | None


class QuotesResponse(BaseModel):
    """Latest quotes response."""

    quotes: dict[str, dict[str, Any]]
    count: int


# =============================================================================
# Routes
# =============================================================================


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_market_data(
    request: SubscribeRequest,
    settings: Settings = Depends(get_settings_dep),
    catalogue: CatalogueStore = Depends(get_catalogue_store),
) -> SubscribeResponse:
    """
    Subscribe to realtime market data for symbols.

    Starts streaming or polling based on mode preference.
    Quotes and bar updates are broadcast via WebSocket.

    Max 20 concurrent subscriptions (performance limit).
    """
    # Validate mode
    try:
        mode = MarketDataMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be 'stream' or 'poll'",
        )

    # Check if IG is configured
    if not settings.has_ig_credentials:
        return SubscribeResponse(
            ok=False,
            message="IG credentials not configured",
            failed=[{"symbol": s, "error": "IG not configured"} for s in request.symbols],
        )

    # Get catalogue for epic lookup
    items = {item.symbol: item for item in catalogue.load()}

    # Validate symbols and get epics
    subscribed: list[str] = []
    failed: list[dict[str, str]] = []

    for symbol in request.symbols:
        if symbol not in items:
            failed.append({"symbol": symbol, "error": "Symbol not in catalogue"})
            continue
        item = items[symbol]
        if not item.epic:
            failed.append({"symbol": symbol, "error": "No epic mapping"})
            continue

        subscribed.append(symbol)

    if not subscribed:
        return SubscribeResponse(
            ok=False,
            subscribed=[],
            failed=failed,
            mode=mode.value,
            message="No valid symbols to subscribe",
        )

    # Get or create market service
    service = get_market_service()

    # Initialize source if not started
    if not service.is_started:
        try:
            from solat_engine.api.ig_routes import get_ig_client
            ig_client = get_ig_client(settings=settings)
            publisher = get_publisher()

            # Import here to avoid circular imports
            from solat_engine.market_data.bar_builder import MultiSymbolBarBuilder
            from solat_engine.market_data.polling import PollingMarketSource
            from solat_engine.market_data.streaming import StreamingMarketSource

            # Create bar builder
            bar_builder = MultiSymbolBarBuilder()

            # Quote handler - updates cache and publishes
            async def on_quote(quote: Quote) -> None:
                # Publish quote (with throttling)
                await publisher.publish_quote(quote)

                # Build bars from quote
                bar_updates = bar_builder.process_quote(quote)
                for update in bar_updates:
                    await publisher.publish_bar(update)

            # Status handler
            async def on_status(status: MarketStreamStatus) -> None:
                await publisher.publish_status(status)

            # Create source based on mode
            source: MarketSourceProtocol
            if mode == MarketDataMode.STREAM:
                source = StreamingMarketSource(
                    ig_client=ig_client,
                    on_quote=on_quote,
                    on_status_change=on_status,
                )
            else:
                source = PollingMarketSource(
                    client=ig_client,
                    poll_interval_ms=request.cadence_ms,
                    on_quote=on_quote,
                )

            service.set_source(source, mode)
            await service.start()

            # Set WS clients reference for publisher
            from solat_engine.main import state
            publisher.set_ws_clients(state.websocket_clients)

        except Exception as e:
            logger.error("Failed to start market data service: %s", e)
            return SubscribeResponse(
                ok=False,
                subscribed=[],
                failed=[{"symbol": s, "error": str(e)} for s in subscribed],
                mode=mode.value,
                message=f"Failed to start market data: {e}",
            )

    # Subscribe to each symbol
    for symbol in subscribed:
        epic = items[symbol].epic
        # epic is guaranteed non-None because we filtered in the loop above
        assert epic is not None
        await service.subscribe(symbol, epic)
        logger.info("Subscribed to %s (%s)", symbol, epic)

    # Check execution allowlist and warn for symbols not on it
    warnings: list[str] = []
    try:
        from solat_engine.api.execution_routes import _execution_router

        if _execution_router and _execution_router._symbol_allowlist is not None:
            for sym in subscribed:
                if sym not in _execution_router._symbol_allowlist:
                    warnings.append(
                        f"{sym} is not on the execution allowlist - "
                        f"orders for this symbol will be rejected"
                    )
    except Exception:
        pass  # Non-critical: don't block subscribe if allowlist check fails

    return SubscribeResponse(
        ok=True,
        subscribed=subscribed,
        failed=failed,
        mode=mode.value,
        message=f"Subscribed to {len(subscribed)} symbols",
        warnings=warnings,
    )


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe_market_data(request: UnsubscribeRequest) -> UnsubscribeResponse:
    """
    Unsubscribe from market data.

    If symbols is empty, unsubscribes from all.
    """
    service = get_market_service()

    if not service.is_started:
        return UnsubscribeResponse(
            ok=True,
            unsubscribed=[],
            message="Market data service not running",
        )

    unsubscribed: list[str] = []

    if not request.symbols:
        # Unsubscribe all
        current = service.get_subscriptions()
        await service.unsubscribe_all()
        unsubscribed = list(current.keys())
        logger.info("Unsubscribed from all symbols")
    else:
        for symbol in request.symbols:
            await service.unsubscribe(symbol)
            unsubscribed.append(symbol)
            logger.info("Unsubscribed from %s", symbol)

    return UnsubscribeResponse(
        ok=True,
        unsubscribed=unsubscribed,
        message=f"Unsubscribed from {len(unsubscribed)} symbols",
    )


@router.get("/status", response_model=StatusResponse)
async def get_market_status() -> StatusResponse:
    """
    Get current market data stream status.

    Includes connection state, mode, staleness, and subscriptions.
    """
    service = get_market_service()
    status = service.get_status()

    return StatusResponse(
        connected=status.connected,
        mode=status.mode.value,
        stale=status.stale,
        subscriptions=status.subscriptions,
        last_tick_ts=status.last_tick_ts.isoformat() if status.last_tick_ts else None,
        reconnect_attempts=status.reconnect_attempts,
        last_error=status.last_error,
    )


@router.get("/quotes", response_model=QuotesResponse)
async def get_latest_quotes(
    symbols: str | None = Query(
        default=None,
        description="Comma-separated symbols to filter (empty = all subscribed)",
    ),
) -> QuotesResponse:
    """
    Get latest cached quotes.

    Returns most recent quote for each subscribed symbol.
    """
    service = get_market_service()
    subscriptions = service.get_subscriptions()

    # Filter symbols if provided
    if symbols:
        filter_set = {s.strip().upper() for s in symbols.split(",")}
    else:
        filter_set = set(subscriptions.keys())

    # Get quotes from publisher cache
    # Note: In a full implementation, we'd have a quote cache in the publisher
    # For now, return empty quotes - the WS stream provides realtime data
    quotes: dict[str, dict[str, Any]] = {}

    for symbol in filter_set:
        if symbol in subscriptions:
            # Placeholder - actual quotes come via WebSocket
            quotes[symbol] = {
                "symbol": symbol,
                "epic": subscriptions[symbol],
                "bid": None,
                "ask": None,
                "mid": None,
                "ts": None,
                "subscribed": True,
            }

    return QuotesResponse(
        quotes=quotes,
        count=len(quotes),
    )


@router.post("/stop")
async def stop_market_data() -> dict[str, Any]:
    """
    Stop the market data service.

    Disconnects from stream/polling and clears subscriptions.
    """
    service = get_market_service()

    if not service.is_started:
        return {"ok": True, "message": "Market data service not running"}

    await service.stop()
    await service.unsubscribe_all()

    return {"ok": True, "message": "Market data service stopped"}
