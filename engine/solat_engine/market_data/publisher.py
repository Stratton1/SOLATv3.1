"""
Market data publisher for EventBus and WebSocket broadcasting.

Handles:
- Quote throttling (max updates/sec per symbol)
- Bar update delivery
- Status change notifications
- Bar persistence to Parquet store
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from solat_engine.logging import get_logger
from solat_engine.market_data.models import BarUpdate, MarketStreamStatus, Quote
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus

if TYPE_CHECKING:
    from solat_engine.data.parquet_store import ParquetStore

logger = get_logger(__name__)


class MarketDataPublisher:
    """
    Publishes market data to EventBus and manages WS throttling.

    Features:
    - Quote throttling (configurable max updates/sec)
    - Batched delivery for high-frequency updates
    - Status change broadcasting
    """

    def __init__(
        self,
        max_quotes_per_sec: int = 10,
        ws_clients: list[Any] | None = None,
        persist_bars: bool = False,
        parquet_store: "ParquetStore | None" = None,
    ):
        """
        Initialize publisher.

        Args:
            max_quotes_per_sec: Max quote updates per second per symbol
            ws_clients: List of WebSocket clients (set by main.py)
            persist_bars: Whether to persist bars to Parquet store
            parquet_store: Parquet store instance for bar persistence
        """
        self._max_quotes_per_sec = max_quotes_per_sec
        self._min_interval = 1.0 / max_quotes_per_sec
        self._ws_clients = ws_clients or []
        self._persist_bars = persist_bars
        self._parquet_store = parquet_store

        # Track last publish time per symbol for throttling
        self._last_quote_time: dict[str, datetime] = defaultdict(
            lambda: datetime.min.replace(tzinfo=UTC)
        )

        # Pending quotes (dropped if throttled)
        self._pending_quotes: dict[str, Quote] = {}

        # Stats
        self._quotes_published = 0
        self._quotes_throttled = 0
        self._bars_published = 0
        self._bars_persisted = 0

    def set_ws_clients(self, clients: list[Any]) -> None:
        """Set WebSocket clients list reference."""
        self._ws_clients = clients

    async def publish_quote(self, quote: Quote) -> bool:
        """
        Publish quote update.

        Applies throttling - if too frequent, drops intermediate quotes.

        Args:
            quote: Quote to publish

        Returns:
            True if published, False if throttled
        """
        now = datetime.now(UTC)
        last_time = self._last_quote_time[quote.symbol]
        elapsed = (now - last_time).total_seconds()

        if elapsed < self._min_interval:
            # Throttled - store pending (will drop if another comes)
            self._pending_quotes[quote.symbol] = quote
            self._quotes_throttled += 1
            return False

        # Publish
        self._last_quote_time[quote.symbol] = now
        self._quotes_published += 1

        # Publish to EventBus
        await self._publish_quote_event(quote)

        # Broadcast to WebSocket clients
        await self._broadcast_quote_ws(quote)

        return True

    async def publish_bar(self, update: BarUpdate) -> None:
        """
        Publish bar update.

        Bars are always delivered (no throttling).
        Optionally persists to Parquet store if enabled.

        Args:
            update: BarUpdate to publish
        """
        self._bars_published += 1

        # Publish to EventBus
        await self._publish_bar_event(update)

        # Broadcast to WebSocket clients
        await self._broadcast_bar_ws(update)

        # Persist to Parquet store if enabled
        if self._persist_bars and self._parquet_store is not None:
            try:
                self._parquet_store.write_bars([update.bar])
                self._bars_persisted += 1
                logger.debug(
                    "Persisted %s %s bar to Parquet",
                    update.symbol,
                    update.timeframe.value,
                )
            except Exception as e:
                logger.warning("Failed to persist bar to Parquet: %s", e)

    async def publish_status(self, status: MarketStreamStatus) -> None:
        """
        Publish market status update.

        Args:
            status: Status to publish
        """
        # Publish to EventBus
        event_bus = get_event_bus()
        await event_bus.publish(
            Event(
                type=EventType.BROKER_CONNECTED
                if status.connected
                else EventType.BROKER_DISCONNECTED,
                data={
                    "connected": status.connected,
                    "stale": status.stale,
                    "mode": status.mode.value,
                    "subscriptions": status.subscriptions,
                    "last_tick_ts": status.last_tick_ts.isoformat()
                    if status.last_tick_ts
                    else None,
                },
            )
        )

        # Broadcast to WebSocket clients
        await self._broadcast_status_ws(status)

    async def _publish_quote_event(self, quote: Quote) -> None:
        """Publish quote to EventBus."""
        event_bus = get_event_bus()
        await event_bus.publish(
            Event(
                type=EventType.QUOTE_RECEIVED,
                data={
                    "symbol": quote.symbol,
                    "epic": quote.epic,
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "mid": quote.mid,
                    "ts": quote.ts_utc.isoformat(),
                },
            )
        )

    async def _publish_bar_event(self, update: BarUpdate) -> None:
        """Publish bar update to EventBus."""
        event_bus = get_event_bus()
        await event_bus.publish(
            Event(
                type=EventType.BAR_RECEIVED,
                data={
                    "symbol": update.symbol,
                    "timeframe": update.timeframe.value,
                    "bar": {
                        "ts": update.bar.timestamp_utc.isoformat(),
                        "o": update.bar.open,
                        "h": update.bar.high,
                        "l": update.bar.low,
                        "c": update.bar.close,
                        "v": update.bar.volume,
                    },
                    "source": update.source,
                },
            )
        )

    async def _broadcast_quote_ws(self, quote: Quote) -> None:
        """Broadcast quote to WebSocket clients."""
        if not self._ws_clients:
            return

        message = {
            "type": "quote_update",
            "symbol": quote.symbol,
            "bid": quote.bid,
            "ask": quote.ask,
            "mid": quote.mid,
            "ts": quote.ts_utc.isoformat(),
        }

        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    async def _broadcast_bar_ws(self, update: BarUpdate) -> None:
        """Broadcast bar update to WebSocket clients."""
        if not self._ws_clients:
            return

        message = {
            "type": "bar_update",
            **update.to_ws_payload(),
        }

        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    async def _broadcast_status_ws(self, status: MarketStreamStatus) -> None:
        """Broadcast status to WebSocket clients."""
        if not self._ws_clients:
            return

        message = {
            "type": "market_status",
            "connected": status.connected,
            "stale": status.stale,
            "mode": status.mode.value,
            "last_tick_ts": status.last_tick_ts.isoformat()
            if status.last_tick_ts
            else None,
            "subscriptions": status.subscriptions,
        }

        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)

    def get_stats(self) -> dict[str, int]:
        """Get publishing statistics."""
        return {
            "quotes_published": self._quotes_published,
            "quotes_throttled": self._quotes_throttled,
            "bars_published": self._bars_published,
            "bars_persisted": self._bars_persisted,
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._quotes_published = 0
        self._quotes_throttled = 0
        self._bars_published = 0
        self._bars_persisted = 0

    def set_persistence(
        self,
        enabled: bool,
        parquet_store: "ParquetStore | None" = None,
    ) -> None:
        """
        Enable or disable bar persistence.

        Args:
            enabled: Whether to persist bars
            parquet_store: Parquet store instance (required if enabled)
        """
        self._persist_bars = enabled
        if parquet_store is not None:
            self._parquet_store = parquet_store


# Global publisher instance
_publisher: MarketDataPublisher | None = None


def get_publisher() -> MarketDataPublisher:
    """Get global publisher instance."""
    global _publisher
    if _publisher is None:
        _publisher = MarketDataPublisher()
    return _publisher


def reset_publisher() -> None:
    """Reset global publisher (for testing)."""
    global _publisher
    _publisher = None
