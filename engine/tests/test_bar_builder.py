"""
Tests for bar builder functionality.

Tests the construction of OHLC bars from quote ticks.
Uses synthetic data - NO REAL NETWORK CALLS.
"""

from datetime import UTC, datetime, timedelta

import pytest

from solat_engine.data.models import SupportedTimeframe
from solat_engine.market_data.bar_builder import BarBuilder, MultiSymbolBarBuilder
from solat_engine.market_data.models import Quote

# =============================================================================
# Fixtures
# =============================================================================


def make_quote(
    symbol: str = "EURUSD",
    epic: str = "CS.D.EURUSD.CFD.IP",
    bid: float = 1.0850,
    ask: float = 1.0852,
    ts_utc: datetime | None = None,
) -> Quote:
    """Create a test quote."""
    if ts_utc is None:
        ts_utc = datetime.now(UTC)
    return Quote.from_bid_ask(
        symbol=symbol,
        epic=epic,
        bid=bid,
        ask=ask,
        ts_utc=ts_utc,
    )


def make_quote_sequence(
    symbol: str,
    start: datetime,
    count: int,
    interval_seconds: int = 5,
    base_price: float = 1.0850,
) -> list[Quote]:
    """Create a sequence of quotes with varying prices."""
    quotes = []
    for i in range(count):
        ts = start + timedelta(seconds=i * interval_seconds)
        # Vary price slightly
        price = base_price + (i % 10) * 0.0001
        quotes.append(
            make_quote(
                symbol=symbol,
                bid=price - 0.0001,
                ask=price + 0.0001,
                ts_utc=ts,
            )
        )
    return quotes


# =============================================================================
# Basic Bar Builder Tests
# =============================================================================


class TestBarBuilderBasic:
    """Basic bar builder functionality tests."""

    def test_create_builder(self) -> None:
        """Can create a bar builder."""
        builder = BarBuilder(symbol="EURUSD")
        assert builder.symbol == "EURUSD"
        assert not builder.has_open_bar

    def test_process_first_quote_opens_bar(self) -> None:
        """First quote should open a new bar."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)
        quote = make_quote(ts_utc=ts)

        updates = builder.process_quote(quote)

        assert builder.has_open_bar
        assert builder.current_bar_start == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert updates == []  # No bar completed yet

    def test_quotes_in_same_minute_update_bar(self) -> None:
        """Multiple quotes in same minute should update same bar."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Send 3 quotes in the same minute
        builder.process_quote(make_quote(bid=1.0850, ask=1.0852, ts_utc=ts))
        builder.process_quote(
            make_quote(bid=1.0860, ask=1.0862, ts_utc=ts + timedelta(seconds=20))
        )
        builder.process_quote(
            make_quote(bid=1.0840, ask=1.0842, ts_utc=ts + timedelta(seconds=40))
        )

        assert builder.has_open_bar
        assert builder.current_bar_start == ts

    def test_minute_rollover_finalizes_bar(self) -> None:
        """Quote in new minute should finalize previous bar."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)

        # Quote in first minute
        builder.process_quote(make_quote(ts_utc=ts))

        # Quote in second minute
        ts2 = datetime(2024, 1, 15, 10, 1, 15, tzinfo=UTC)
        updates = builder.process_quote(make_quote(ts_utc=ts2))

        # Should have 1m bar update (and possibly derived timeframes)
        assert len(updates) >= 1
        m1_update = updates[0]
        assert m1_update.timeframe == SupportedTimeframe.M1
        assert m1_update.symbol == "EURUSD"
        assert m1_update.bar.timestamp_utc == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_wrong_symbol_ignored(self) -> None:
        """Quote for wrong symbol should be ignored."""
        builder = BarBuilder(symbol="EURUSD")
        quote = make_quote(symbol="GBPUSD")

        updates = builder.process_quote(quote)

        assert updates == []
        assert not builder.has_open_bar


# =============================================================================
# OHLC Calculation Tests
# =============================================================================


class TestBarBuilderOHLC:
    """Tests for OHLC calculation in bar builder."""

    def test_open_is_first_quote_mid(self) -> None:
        """Bar open should be first quote's mid price."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        builder.process_quote(make_quote(bid=1.0850, ask=1.0852, ts_utc=ts))
        builder.process_quote(
            make_quote(bid=1.0860, ask=1.0862, ts_utc=ts + timedelta(seconds=20))
        )

        # Force finalize
        updates = builder.force_finalize()

        assert len(updates) >= 1
        # First quote mid: (1.0850 + 1.0852) / 2 = 1.0851
        assert updates[0].bar.open == pytest.approx(1.0851, rel=1e-5)

    def test_high_is_max_mid(self) -> None:
        """Bar high should be maximum mid price."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        builder.process_quote(make_quote(bid=1.0850, ask=1.0852, ts_utc=ts))  # mid=1.0851
        builder.process_quote(
            make_quote(bid=1.0870, ask=1.0872, ts_utc=ts + timedelta(seconds=20))
        )  # mid=1.0871 MAX
        builder.process_quote(
            make_quote(bid=1.0840, ask=1.0842, ts_utc=ts + timedelta(seconds=40))
        )  # mid=1.0841

        updates = builder.force_finalize()

        assert updates[0].bar.high == pytest.approx(1.0871, rel=1e-5)

    def test_low_is_min_mid(self) -> None:
        """Bar low should be minimum mid price."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        builder.process_quote(make_quote(bid=1.0850, ask=1.0852, ts_utc=ts))  # mid=1.0851
        builder.process_quote(
            make_quote(bid=1.0830, ask=1.0832, ts_utc=ts + timedelta(seconds=20))
        )  # mid=1.0831 MIN
        builder.process_quote(
            make_quote(bid=1.0860, ask=1.0862, ts_utc=ts + timedelta(seconds=40))
        )  # mid=1.0861

        updates = builder.force_finalize()

        assert updates[0].bar.low == pytest.approx(1.0831, rel=1e-5)

    def test_close_is_last_quote_mid(self) -> None:
        """Bar close should be last quote's mid price."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        builder.process_quote(make_quote(bid=1.0850, ask=1.0852, ts_utc=ts))
        builder.process_quote(
            make_quote(bid=1.0860, ask=1.0862, ts_utc=ts + timedelta(seconds=20))
        )
        builder.process_quote(
            make_quote(bid=1.0855, ask=1.0857, ts_utc=ts + timedelta(seconds=40))
        )  # mid=1.0856 LAST

        updates = builder.force_finalize()

        assert updates[0].bar.close == pytest.approx(1.0856, rel=1e-5)


# =============================================================================
# Derived Timeframe Tests
# =============================================================================


class TestDerivedTimeframes:
    """Tests for derived timeframe generation."""

    def test_5m_bar_emitted_at_boundary(self) -> None:
        """5m bar should be emitted when 5-minute boundary is reached."""
        builder = BarBuilder(
            symbol="EURUSD",
            derived_timeframes=[SupportedTimeframe.M5],
        )

        # Generate quotes for 6 minutes (10:00 to 10:05)
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Process quotes for minutes 0-4
        for minute in range(5):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        # Quote at minute 5 should trigger 5m bar
        ts_5 = start + timedelta(minutes=5, seconds=15)
        updates = builder.process_quote(make_quote(ts_utc=ts_5))

        # Should have M1 bars + M5 bar
        timeframes = [u.timeframe for u in updates]
        assert SupportedTimeframe.M5 in timeframes

    def test_15m_bar_emitted_at_boundary(self) -> None:
        """15m bar should be emitted at :15, :30, :45, :00."""
        builder = BarBuilder(
            symbol="EURUSD",
            derived_timeframes=[SupportedTimeframe.M15],
        )

        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Process quotes for 15 minutes
        for minute in range(15):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        # Quote at minute 15 should trigger 15m bar
        ts_15 = start + timedelta(minutes=15, seconds=15)
        updates = builder.process_quote(make_quote(ts_utc=ts_15))

        timeframes = [u.timeframe for u in updates]
        assert SupportedTimeframe.M15 in timeframes

    def test_1h_bar_emitted_at_hour_boundary(self) -> None:
        """1h bar should be emitted at top of hour."""
        builder = BarBuilder(
            symbol="EURUSD",
            derived_timeframes=[SupportedTimeframe.H1],
        )

        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Process quotes for 60 minutes
        for minute in range(60):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        # Quote at minute 60 (11:00) should trigger 1h bar
        ts_60 = start + timedelta(minutes=60, seconds=15)
        updates = builder.process_quote(make_quote(ts_utc=ts_60))

        timeframes = [u.timeframe for u in updates]
        assert SupportedTimeframe.H1 in timeframes


# =============================================================================
# Force Finalize Tests
# =============================================================================


class TestForceFinalize:
    """Tests for force finalization of incomplete bars."""

    def test_force_finalize_with_open_bar(self) -> None:
        """force_finalize should finalize incomplete bar."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)

        builder.process_quote(make_quote(ts_utc=ts))
        assert builder.has_open_bar

        updates = builder.force_finalize()

        assert len(updates) >= 1
        assert not builder.has_open_bar

    def test_force_finalize_without_open_bar(self) -> None:
        """force_finalize with no open bar should return empty."""
        builder = BarBuilder(symbol="EURUSD")

        updates = builder.force_finalize()

        assert updates == []


# =============================================================================
# Buffer Tests
# =============================================================================


class TestBarBuffer:
    """Tests for bar buffer management."""

    def test_buffer_accumulates_bars(self) -> None:
        """Bars should accumulate in buffer."""
        builder = BarBuilder(symbol="EURUSD")
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Generate 3 complete bars
        for minute in range(4):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        buffer = builder.get_buffer_bars(SupportedTimeframe.M1)
        assert len(buffer) == 3  # 3 complete bars (4th is still open)

    def test_buffer_respects_max_size(self) -> None:
        """Buffer should not exceed max size."""
        builder = BarBuilder(symbol="EURUSD")
        builder._max_buffer_size = 5  # Set small for test

        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Generate 10 complete bars
        for minute in range(11):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        buffer = builder.get_buffer_bars(SupportedTimeframe.M1)
        assert len(buffer) <= 5

    def test_clear_buffer(self) -> None:
        """clear_buffer should empty the buffer."""
        builder = BarBuilder(symbol="EURUSD")
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        for minute in range(3):
            ts = start + timedelta(minutes=minute, seconds=30)
            builder.process_quote(make_quote(ts_utc=ts))

        builder.clear_buffer()
        buffer = builder.get_buffer_bars(SupportedTimeframe.M1)
        assert len(buffer) == 0


# =============================================================================
# MultiSymbolBarBuilder Tests
# =============================================================================


class TestMultiSymbolBarBuilder:
    """Tests for multi-symbol bar builder."""

    def test_get_builder_creates_on_demand(self) -> None:
        """get_builder should create builder for new symbol."""
        multi = MultiSymbolBarBuilder()

        builder1 = multi.get_builder("EURUSD")
        builder2 = multi.get_builder("GBPUSD")

        assert builder1.symbol == "EURUSD"
        assert builder2.symbol == "GBPUSD"
        assert "EURUSD" in multi.get_symbols()
        assert "GBPUSD" in multi.get_symbols()

    def test_get_builder_returns_same_instance(self) -> None:
        """get_builder should return same instance for same symbol."""
        multi = MultiSymbolBarBuilder()

        builder1 = multi.get_builder("EURUSD")
        builder2 = multi.get_builder("EURUSD")

        assert builder1 is builder2

    def test_process_quote_routes_to_correct_builder(self) -> None:
        """process_quote should route to correct builder."""
        multi = MultiSymbolBarBuilder()
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)

        multi.process_quote(make_quote(symbol="EURUSD", ts_utc=ts))
        multi.process_quote(make_quote(symbol="GBPUSD", ts_utc=ts))

        assert multi.get_builder("EURUSD").has_open_bar
        assert multi.get_builder("GBPUSD").has_open_bar

    def test_force_finalize_all(self) -> None:
        """force_finalize_all should finalize all builders."""
        multi = MultiSymbolBarBuilder()
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)

        multi.process_quote(make_quote(symbol="EURUSD", ts_utc=ts))
        multi.process_quote(make_quote(symbol="GBPUSD", ts_utc=ts))

        updates = multi.force_finalize_all()

        assert len(updates) >= 2  # At least one bar per symbol
        symbols = [u.symbol for u in updates]
        assert "EURUSD" in symbols
        assert "GBPUSD" in symbols

    def test_remove_builder(self) -> None:
        """remove_builder should remove builder for symbol."""
        multi = MultiSymbolBarBuilder()
        multi.get_builder("EURUSD")
        multi.get_builder("GBPUSD")

        multi.remove_builder("EURUSD")

        assert "EURUSD" not in multi.get_symbols()
        assert "GBPUSD" in multi.get_symbols()

    def test_clear(self) -> None:
        """clear should remove all builders."""
        multi = MultiSymbolBarBuilder()
        multi.get_builder("EURUSD")
        multi.get_builder("GBPUSD")

        multi.clear()

        assert multi.get_symbols() == []


# =============================================================================
# UTC Alignment Tests
# =============================================================================


class TestUTCAlignment:
    """Tests for UTC minute alignment."""

    def test_bar_start_aligned_to_minute(self) -> None:
        """Bar start should be aligned to minute boundary."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 5, 37, tzinfo=UTC)  # 10:05:37

        builder.process_quote(make_quote(ts_utc=ts))

        assert builder.current_bar_start == datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC)

    def test_bar_timestamp_is_utc(self) -> None:
        """Finalized bar should have UTC timestamp."""
        builder = BarBuilder(symbol="EURUSD")
        ts = datetime(2024, 1, 15, 10, 0, 30, tzinfo=UTC)

        builder.process_quote(make_quote(ts_utc=ts))
        updates = builder.force_finalize()

        assert updates[0].bar.timestamp_utc.tzinfo == UTC
