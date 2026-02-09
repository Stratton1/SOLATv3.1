"""
Market data models for realtime price streaming.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from solat_engine.data.models import HistoricalBar, SupportedTimeframe


class MarketDataMode(str, Enum):
    """Market data connection mode."""

    STREAM = "stream"  # Lightstreamer streaming
    POLL = "poll"  # REST polling fallback


class Quote(BaseModel):
    """
    A single price quote (tick).

    Represents a bid/ask snapshot from the broker.
    """

    symbol: str = Field(..., description="Canonical symbol (e.g., EURUSD)")
    epic: str = Field(..., description="IG epic identifier")
    bid: float = Field(..., description="Bid price")
    ask: float = Field(..., description="Ask price")
    mid: float = Field(..., description="Mid price ((bid+ask)/2)")
    ts_utc: datetime = Field(..., description="Quote timestamp (UTC)")
    update_time: str | None = Field(
        default=None,
        description="Raw update time string from broker",
    )

    @classmethod
    def from_bid_ask(
        cls,
        symbol: str,
        epic: str,
        bid: float,
        ask: float,
        ts_utc: datetime,
        update_time: str | None = None,
    ) -> "Quote":
        """Create Quote from bid/ask, computing mid price."""
        return cls(
            symbol=symbol,
            epic=epic,
            bid=bid,
            ask=ask,
            mid=(bid + ask) / 2,
            ts_utc=ts_utc,
            update_time=update_time,
        )


class MarketStreamStatus(BaseModel):
    """
    Status of market data connection.

    Tracks connection state, staleness, and active subscriptions.
    """

    connected: bool = Field(default=False, description="Whether connected to broker")
    mode: MarketDataMode = Field(
        default=MarketDataMode.POLL,
        description="Current connection mode",
    )
    last_tick_ts: datetime | None = Field(
        default=None,
        description="Timestamp of last received tick",
    )
    stale: bool = Field(
        default=False,
        description="True if no ticks received recently (possible disconnection)",
    )
    stale_threshold_s: int = Field(
        default=10,
        description="Seconds without ticks before considered stale",
    )
    subscriptions: list[str] = Field(
        default_factory=list,
        description="Currently subscribed symbols",
    )
    reconnect_attempts: int = Field(
        default=0,
        description="Number of reconnection attempts",
    )
    last_error: str | None = Field(
        default=None,
        description="Last error message if any",
    )


class SubscriptionRequest(BaseModel):
    """
    Request to subscribe to market data.

    Specifies symbols and connection mode.
    """

    symbols: list[str] = Field(..., description="Symbols to subscribe to")
    mode: MarketDataMode = Field(
        default=MarketDataMode.STREAM,
        description="Preferred mode (stream or poll)",
    )
    cadence_ms: int = Field(
        default=1500,
        description="Poll interval in ms (only for poll mode)",
    )


class BarUpdate(BaseModel):
    """
    Notification of a completed bar.

    Emitted when a bar is finalized (e.g., minute close).
    """

    symbol: str = Field(..., description="Symbol")
    timeframe: SupportedTimeframe = Field(..., description="Bar timeframe")
    bar: HistoricalBar = Field(..., description="The completed bar")
    source: str = Field(
        default="realtime",
        description="Source: realtime, backfill, or historical",
    )

    def to_ws_payload(self) -> dict[str, Any]:
        """Convert to WebSocket event payload."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "bar": {
                "ts": self.bar.timestamp_utc.isoformat(),
                "o": self.bar.open,
                "h": self.bar.high,
                "l": self.bar.low,
                "c": self.bar.close,
                "v": self.bar.volume,
            },
            "source": self.source,
        }


class QuoteCache(BaseModel):
    """
    Bounded in-memory cache for latest quotes per symbol.

    Thread-safe access via the MarketDataService.
    Uses LRU eviction when at capacity.
    """

    quotes: dict[str, Quote] = Field(
        default_factory=dict,
        description="Symbol -> latest quote",
    )
    max_age_s: int = Field(
        default=60,
        description="Max age before quote considered stale",
    )
    max_symbols: int = Field(
        default=100,
        description="Maximum symbols to cache (LRU eviction)",
    )

    # Track access order for LRU
    _access_order: list[str] = []

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._access_order = list(self.quotes.keys())

    def update(self, quote: Quote) -> None:
        """Update cached quote for symbol with LRU eviction."""
        symbol = quote.symbol

        # Update or add quote
        self.quotes[symbol] = quote

        # Update access order
        if symbol in self._access_order:
            self._access_order.remove(symbol)
        self._access_order.append(symbol)

        # Evict oldest if over capacity
        while len(self.quotes) > self.max_symbols:
            oldest = self._access_order.pop(0)
            self.quotes.pop(oldest, None)

    def get(self, symbol: str) -> Quote | None:
        """Get cached quote for symbol (updates access order)."""
        quote = self.quotes.get(symbol)
        if quote is not None:
            # Update access order
            if symbol in self._access_order:
                self._access_order.remove(symbol)
            self._access_order.append(symbol)
        return quote

    def get_all(self) -> dict[str, Quote]:
        """Get all cached quotes."""
        return self.quotes.copy()

    def clear(self) -> None:
        """Clear all cached quotes."""
        self.quotes.clear()
        self._access_order.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.quotes)


class BarBuffer(BaseModel):
    """
    Circular buffer for recent bars per symbol/timeframe.

    Keeps bounded memory footprint.
    """

    symbol: str
    timeframe: SupportedTimeframe
    bars: list[HistoricalBar] = Field(default_factory=list)
    max_bars: int = Field(default=500, description="Maximum bars to keep in memory")

    def append(self, bar: HistoricalBar) -> None:
        """Append bar, evicting oldest if at capacity."""
        self.bars.append(bar)
        if len(self.bars) > self.max_bars:
            self.bars = self.bars[-self.max_bars :]

    def get_latest(self, n: int = 1) -> list[HistoricalBar]:
        """Get latest N bars."""
        return self.bars[-n:]

    def get_range(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[HistoricalBar]:
        """Get bars in timestamp range."""
        result = []
        for bar in self.bars:
            if start and bar.timestamp_utc < start:
                continue
            if end and bar.timestamp_utc > end:
                continue
            result.append(bar)
        return result
