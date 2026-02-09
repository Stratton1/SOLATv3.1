"""
Polling-based market data source (fallback when streaming unavailable).

Periodically fetches market snapshots via REST API.
"""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from solat_engine.logging import get_logger
from solat_engine.market_data.models import MarketDataMode, MarketStreamStatus, Quote

if TYPE_CHECKING:
    from solat_engine.broker.ig.client import AsyncIGClient

logger = get_logger(__name__)


class PollingMarketSource:
    """
    Polling-based market data source.

    Fetches market snapshots at regular intervals.
    """

    def __init__(
        self,
        client: "AsyncIGClient",
        poll_interval_ms: int = 1500,
        on_quote: Any = None,
    ):
        """
        Initialize polling source.

        Args:
            client: IG client for API calls
            poll_interval_ms: Poll interval in milliseconds
            on_quote: Async callback(Quote) for each quote
        """
        self._client = client
        self._poll_interval_ms = poll_interval_ms
        self._on_quote = on_quote

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._subscriptions: dict[str, str] = {}  # symbol -> epic
        self._last_tick_ts: datetime | None = None
        self._error_count = 0
        self._max_errors = 10

    @property
    def is_running(self) -> bool:
        """Check if polling is active."""
        return self._running

    @property
    def mode(self) -> MarketDataMode:
        """Get connection mode."""
        return MarketDataMode.POLL

    def get_status(self) -> MarketStreamStatus:
        """Get current status."""
        stale = False
        if self._last_tick_ts:
            age = (datetime.now(UTC) - self._last_tick_ts).total_seconds()
            stale = age > 10

        return MarketStreamStatus(
            connected=self._running,
            mode=MarketDataMode.POLL,
            last_tick_ts=self._last_tick_ts,
            stale=stale,
            subscriptions=list(self._subscriptions.keys()),
            reconnect_attempts=0,
        )

    async def subscribe(self, symbol: str, epic: str) -> None:
        """
        Subscribe to a symbol.

        Args:
            symbol: Symbol to subscribe to
            epic: IG epic identifier
        """
        self._subscriptions[symbol] = epic
        logger.info("Polling: subscribed to %s (%s)", symbol, epic)

    async def unsubscribe(self, symbol: str) -> None:
        """
        Unsubscribe from a symbol.

        Args:
            symbol: Symbol to unsubscribe from
        """
        if symbol in self._subscriptions:
            del self._subscriptions[symbol]
            logger.info("Polling: unsubscribed from %s", symbol)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all symbols."""
        self._subscriptions.clear()
        logger.info("Polling: unsubscribed from all symbols")

    async def start(self) -> None:
        """Start polling loop."""
        if self._running:
            logger.warning("Polling already running")
            return

        self._running = True
        self._error_count = 0
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Polling market source started (interval: %dms)",
            self._poll_interval_ms,
        )

    async def stop(self) -> None:
        """Stop polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Polling market source stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        interval_s = self._poll_interval_ms / 1000.0

        while self._running:
            try:
                await self._poll_once()
                self._error_count = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                logger.error(
                    "Polling error (%d/%d): %s",
                    self._error_count,
                    self._max_errors,
                    e,
                )
                if self._error_count >= self._max_errors:
                    logger.error("Max polling errors reached, stopping")
                    self._running = False
                    break

            await asyncio.sleep(interval_s)

    async def _poll_once(self) -> None:
        """Poll all subscribed symbols once."""
        if not self._subscriptions:
            return

        for symbol, epic in list(self._subscriptions.items()):
            try:
                quote = await self._fetch_quote(symbol, epic)
                if quote and self._on_quote:
                    await self._on_quote(quote)
                if quote:
                    self._last_tick_ts = quote.ts_utc
            except Exception as e:
                logger.warning("Failed to poll %s: %s", symbol, e)

    async def _fetch_quote(self, symbol: str, epic: str) -> Quote | None:
        """
        Fetch quote for a symbol via REST API.

        Args:
            symbol: Symbol
            epic: IG epic

        Returns:
            Quote or None if failed
        """
        try:
            # Get market details from IG
            market_details = await self._client.get_market_details(epic)
            if market_details is None or market_details.snapshot is None:
                logger.debug("No market details for %s", symbol)
                return None

            snapshot = market_details.snapshot
            bid = snapshot.get("bid")
            offer = snapshot.get("offer")

            if bid is None or offer is None:
                logger.debug("No bid/offer for %s", symbol)
                return None

            bid = float(bid)
            offer = float(offer)

            # Parse update time if available
            update_time = snapshot.get("updateTime")

            return Quote.from_bid_ask(
                symbol=symbol,
                epic=epic,
                bid=bid,
                ask=offer,
                ts_utc=datetime.now(UTC),
                update_time=update_time,
            )

        except Exception as e:
            logger.debug("Error fetching quote for %s: %s", symbol, e)
            return None


class MockPollingSource:
    """
    Mock polling source for testing.

    Generates synthetic quotes without network calls.
    """

    def __init__(
        self,
        poll_interval_ms: int = 1500,
        on_quote: Any = None,
    ):
        """
        Initialize mock source.

        Args:
            poll_interval_ms: Poll interval
            on_quote: Quote callback
        """
        self._poll_interval_ms = poll_interval_ms
        self._on_quote = on_quote
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._subscriptions: dict[str, str] = {}
        self._last_tick_ts: datetime | None = None

        # Base prices for synthetic data
        self._base_prices: dict[str, float] = {
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "USDJPY": 150.50,
            "AUDUSD": 0.6450,
        }

    @property
    def is_running(self) -> bool:
        """Check if running."""
        return self._running

    @property
    def mode(self) -> MarketDataMode:
        """Get mode."""
        return MarketDataMode.POLL

    def get_status(self) -> MarketStreamStatus:
        """Get status."""
        return MarketStreamStatus(
            connected=self._running,
            mode=MarketDataMode.POLL,
            last_tick_ts=self._last_tick_ts,
            stale=False,
            subscriptions=list(self._subscriptions.keys()),
        )

    async def subscribe(self, symbol: str, epic: str) -> None:
        """Subscribe to symbol."""
        self._subscriptions[symbol] = epic

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from symbol."""
        if symbol in self._subscriptions:
            del self._subscriptions[symbol]

    async def unsubscribe_all(self) -> None:
        """Unsubscribe all."""
        self._subscriptions.clear()

    async def start(self) -> None:
        """Start mock polling."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop mock polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        """Mock poll loop."""
        import random

        interval_s = self._poll_interval_ms / 1000.0

        while self._running:
            try:
                for symbol, epic in list(self._subscriptions.items()):
                    base = self._base_prices.get(symbol, 1.0)
                    # Random walk
                    change = random.uniform(-0.0010, 0.0010)
                    mid = base + change
                    spread = 0.0002

                    quote = Quote.from_bid_ask(
                        symbol=symbol,
                        epic=epic,
                        bid=mid - spread / 2,
                        ask=mid + spread / 2,
                        ts_utc=datetime.now(UTC),
                    )

                    if self._on_quote:
                        await self._on_quote(quote)

                    self._last_tick_ts = quote.ts_utc
                    self._base_prices[symbol] = mid

            except asyncio.CancelledError:
                break

            await asyncio.sleep(interval_s)
