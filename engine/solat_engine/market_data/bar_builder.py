"""
Bar builder for constructing OHLC bars from quote ticks.

Builds 1m bars from quotes and derives higher timeframes.
UTC-aligned, deterministic bar construction.
"""

from datetime import datetime, timedelta
from typing import Any

from solat_engine.data.aggregate import aggregate_bars, get_bin_start
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.logging import get_logger
from solat_engine.market_data.models import BarUpdate, Quote

logger = get_logger(__name__)


class BarBuilder:
    """
    Builds 1m OHLC bars from incoming quotes.

    Features:
    - UTC minute-aligned bars
    - Bar finalization on minute rollover
    - Derived timeframe aggregation (5m, 15m, 1h, 4h)
    - Callbacks for bar completion
    """

    def __init__(
        self,
        symbol: str,
        on_bar_complete: Any = None,
        derived_timeframes: list[SupportedTimeframe] | None = None,
    ):
        """
        Initialize bar builder.

        Args:
            symbol: Symbol this builder tracks
            on_bar_complete: Async callback(BarUpdate) when bar completes
            derived_timeframes: Timeframes to derive from 1m (default: all)
        """
        self._symbol = symbol
        self._on_bar_complete = on_bar_complete
        self._derived_timeframes = derived_timeframes or [
            SupportedTimeframe.M5,
            SupportedTimeframe.M15,
            SupportedTimeframe.H1,
            SupportedTimeframe.H4,
        ]

        # Current incomplete bar state
        self._current_bar_start: datetime | None = None
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._tick_count: int = 0

        # Buffer for 1m bars (for aggregation)
        self._m1_buffer: list[HistoricalBar] = []
        self._max_buffer_size = 300  # ~5 hours of 1m bars

        # Track volume warning (only warn once per symbol)
        self._volume_warned = False

    @property
    def symbol(self) -> str:
        """Get symbol."""
        return self._symbol

    @property
    def has_open_bar(self) -> bool:
        """Check if there's an incomplete bar."""
        return self._current_bar_start is not None

    @property
    def current_bar_start(self) -> datetime | None:
        """Get current bar start time."""
        return self._current_bar_start

    def process_quote(self, quote: Quote) -> list[BarUpdate]:
        """
        Process an incoming quote.

        May finalize current bar and emit bar updates.

        Args:
            quote: Incoming quote

        Returns:
            List of BarUpdate events (may include 1m + derived)
        """
        if quote.symbol != self._symbol:
            logger.warning(
                "Quote symbol %s doesn't match builder symbol %s",
                quote.symbol,
                self._symbol,
            )
            return []

        updates: list[BarUpdate] = []

        # Calculate bar start for this quote
        bar_start = self._get_bar_start(quote.ts_utc)

        # Check if we need to finalize current bar
        if self._current_bar_start is not None and bar_start > self._current_bar_start:
            # Finalize current bar
            bar_updates = self._finalize_bar()
            updates.extend(bar_updates)

        # Update current bar with quote
        self._update_bar(quote, bar_start)

        return updates

    def _get_bar_start(self, ts: datetime) -> datetime:
        """Get the 1m bar start time for a timestamp."""
        return get_bin_start(ts, SupportedTimeframe.M1)

    def _update_bar(self, quote: Quote, bar_start: datetime) -> None:
        """Update current bar with quote data."""
        price = quote.mid  # Use mid price for OHLC

        if self._current_bar_start != bar_start:
            # New bar
            self._current_bar_start = bar_start
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._tick_count = 1
        else:
            # Update existing bar
            if self._high is None or price > self._high:
                self._high = price
            if self._low is None or price < self._low:
                self._low = price
            self._close = price
            self._tick_count += 1

    def _finalize_bar(self) -> list[BarUpdate]:
        """
        Finalize current bar and check derived timeframes.

        Returns:
            List of BarUpdate events
        """
        if self._current_bar_start is None or self._open is None:
            return []

        updates: list[BarUpdate] = []

        # Create 1m bar
        m1_bar = HistoricalBar(
            timestamp_utc=self._current_bar_start,
            instrument_symbol=self._symbol,
            timeframe=SupportedTimeframe.M1,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=0.0,  # Volume not available from quotes
        )

        # Warn once about missing volume
        if not self._volume_warned:
            logger.info(
                "Volume not available for %s realtime bars (using 0)",
                self._symbol,
            )
            self._volume_warned = True

        # Emit 1m bar update
        m1_update = BarUpdate(
            symbol=self._symbol,
            timeframe=SupportedTimeframe.M1,
            bar=m1_bar,
            source="realtime",
        )
        updates.append(m1_update)

        # Add to buffer for aggregation
        self._m1_buffer.append(m1_bar)
        if len(self._m1_buffer) > self._max_buffer_size:
            self._m1_buffer = self._m1_buffer[-self._max_buffer_size :]

        # Check derived timeframes
        derived_updates = self._check_derived_timeframes()
        updates.extend(derived_updates)

        # Reset current bar state
        self._current_bar_start = None
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._tick_count = 0

        logger.debug(
            "Finalized %s 1m bar at %s (O=%.5f H=%.5f L=%.5f C=%.5f)",
            self._symbol,
            m1_bar.timestamp_utc.isoformat(),
            m1_bar.open,
            m1_bar.high,
            m1_bar.low,
            m1_bar.close,
        )

        return updates

    def _check_derived_timeframes(self) -> list[BarUpdate]:
        """
        Check if any derived timeframe bins are complete.

        Returns:
            List of derived BarUpdate events
        """
        if not self._m1_buffer:
            return []

        updates: list[BarUpdate] = []
        latest_bar = self._m1_buffer[-1]
        bar_end = latest_bar.timestamp_utc + timedelta(minutes=1)

        for tf in self._derived_timeframes:
            # Check if we're at a timeframe boundary
            if self._is_timeframe_boundary(bar_end, tf):
                # Aggregate available 1m bars for this bin
                derived_bar = self._aggregate_for_timeframe(tf, bar_end)
                if derived_bar:
                    update = BarUpdate(
                        symbol=self._symbol,
                        timeframe=tf,
                        bar=derived_bar,
                        source="realtime",
                    )
                    updates.append(update)

        return updates

    def _is_timeframe_boundary(self, ts: datetime, tf: SupportedTimeframe) -> bool:
        """Check if timestamp is at a timeframe boundary."""
        minutes = tf.minutes
        total_minutes = ts.hour * 60 + ts.minute
        return total_minutes % minutes == 0

    def _aggregate_for_timeframe(
        self,
        tf: SupportedTimeframe,
        bin_end: datetime,
    ) -> HistoricalBar | None:
        """
        Aggregate 1m bars for a specific timeframe bin.

        Args:
            tf: Target timeframe
            bin_end: End of the bin (exclusive)

        Returns:
            Aggregated bar or None if insufficient data
        """
        minutes = tf.minutes
        bin_start = bin_end - timedelta(minutes=minutes)

        # Get 1m bars in this bin
        bars_in_bin = [
            bar
            for bar in self._m1_buffer
            if bin_start <= bar.timestamp_utc < bin_end
        ]

        if not bars_in_bin:
            return None

        # Need all bars for complete bin (or at least 80%)
        if len(bars_in_bin) < minutes * 0.8:
            logger.debug(
                "Incomplete %s bin for %s: %d/%d bars",
                tf.value,
                self._symbol,
                len(bars_in_bin),
                minutes,
            )
            # Still emit with available data

        # Aggregate
        aggregated = aggregate_bars(bars_in_bin, tf)
        if aggregated:
            return aggregated[0]

        return None

    def force_finalize(self) -> list[BarUpdate]:
        """
        Force finalize current incomplete bar.

        Useful for session end or disconnection.

        Returns:
            BarUpdate events if there was an incomplete bar
        """
        if self.has_open_bar:
            return self._finalize_bar()
        return []

    def get_buffer_bars(
        self,
        timeframe: SupportedTimeframe = SupportedTimeframe.M1,
    ) -> list[HistoricalBar]:
        """
        Get buffered bars.

        Args:
            timeframe: Timeframe to get (only M1 directly available)

        Returns:
            List of bars
        """
        if timeframe == SupportedTimeframe.M1:
            return self._m1_buffer.copy()

        # Aggregate for other timeframes
        return aggregate_bars(self._m1_buffer, timeframe)

    def clear_buffer(self) -> None:
        """Clear the 1m bar buffer."""
        self._m1_buffer.clear()


class MultiSymbolBarBuilder:
    """
    Manages bar builders for multiple symbols.

    Factory for creating and accessing per-symbol builders.
    """

    def __init__(
        self,
        on_bar_complete: Any = None,
        derived_timeframes: list[SupportedTimeframe] | None = None,
    ):
        """
        Initialize multi-symbol bar builder.

        Args:
            on_bar_complete: Callback for bar completion
            derived_timeframes: Timeframes to derive
        """
        self._builders: dict[str, BarBuilder] = {}
        self._on_bar_complete = on_bar_complete
        self._derived_timeframes = derived_timeframes

    def get_builder(self, symbol: str) -> BarBuilder:
        """
        Get or create builder for symbol.

        Args:
            symbol: Symbol to get builder for

        Returns:
            BarBuilder instance
        """
        if symbol not in self._builders:
            self._builders[symbol] = BarBuilder(
                symbol=symbol,
                on_bar_complete=self._on_bar_complete,
                derived_timeframes=self._derived_timeframes,
            )
        return self._builders[symbol]

    def process_quote(self, quote: Quote) -> list[BarUpdate]:
        """
        Process quote through appropriate builder.

        Args:
            quote: Incoming quote

        Returns:
            List of BarUpdate events
        """
        builder = self.get_builder(quote.symbol)
        return builder.process_quote(quote)

    def force_finalize_all(self) -> list[BarUpdate]:
        """
        Force finalize all incomplete bars.

        Returns:
            All BarUpdate events
        """
        updates: list[BarUpdate] = []
        for builder in self._builders.values():
            updates.extend(builder.force_finalize())
        return updates

    def get_symbols(self) -> list[str]:
        """Get all symbols with builders."""
        return list(self._builders.keys())

    def remove_builder(self, symbol: str) -> None:
        """Remove builder for symbol."""
        if symbol in self._builders:
            del self._builders[symbol]

    def clear(self) -> None:
        """Clear all builders."""
        self._builders.clear()
