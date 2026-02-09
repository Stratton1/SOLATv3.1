"""
Tests for timeframe aggregation.

Tests aggregation from 1m base data to derived timeframes (5m, 15m, 30m, 1h, 4h).
30m is derived-only (IG has no MINUTE_30). Uses fixed test datasets - NO REAL IG CALLS.
"""

from datetime import UTC, datetime, timedelta

from solat_engine.data.aggregate import (
    aggregate_bars,
    aggregate_from_1m,
    get_bin_start,
    validate_aggregation_alignment,
)
from solat_engine.data.models import HistoricalBar, SupportedTimeframe

# =============================================================================
# Fixtures
# =============================================================================


def make_m1_bar(
    timestamp: datetime,
    symbol: str = "EURUSD",
    open_: float = 1.1000,
    high: float = 1.1010,
    low: float = 1.0990,
    close: float = 1.1005,
    volume: float = 100.0,
) -> HistoricalBar:
    """Create a 1-minute bar."""
    return HistoricalBar(
        timestamp_utc=timestamp,
        instrument_symbol=symbol,
        timeframe=SupportedTimeframe.M1,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def make_m1_sequence(
    start: datetime,
    count: int,
    symbol: str = "EURUSD",
    base_price: float = 1.1000,
) -> list[HistoricalBar]:
    """Create a sequence of 1m bars with predictable prices."""
    bars = []
    for i in range(count):
        ts = start + timedelta(minutes=i)
        # Vary prices slightly for each bar
        bar = make_m1_bar(
            timestamp=ts,
            symbol=symbol,
            open_=base_price + i * 0.0001,
            high=base_price + i * 0.0001 + 0.0010,
            low=base_price + i * 0.0001 - 0.0005,
            close=base_price + i * 0.0001 + 0.0005,
            volume=100.0 + i * 10,
        )
        bars.append(bar)
    return bars


# =============================================================================
# Basic Aggregation Tests
# =============================================================================


class TestAggregateBasic:
    """Basic aggregation functionality tests."""

    def test_aggregate_empty_list(self) -> None:
        """Aggregating empty list should return empty list."""
        result = aggregate_bars([], SupportedTimeframe.M5)
        assert result == []

    def test_aggregate_5m_from_5_m1_bars(self) -> None:
        """Five 1m bars should aggregate to one 5m bar."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=5)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)

        assert len(result) == 1
        assert result[0].timeframe == SupportedTimeframe.M5
        assert result[0].timestamp_utc == start

    def test_aggregate_15m_from_15_m1_bars(self) -> None:
        """Fifteen 1m bars should aggregate to one 15m bar."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=15)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M15)

        assert len(result) == 1
        assert result[0].timeframe == SupportedTimeframe.M15
        assert result[0].timestamp_utc == start

    def test_aggregate_30m_from_30_m1_bars(self) -> None:
        """Thirty 1m bars should aggregate to one 30m bar (derived-only timeframe)."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=30)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M30)

        assert len(result) == 1
        assert result[0].timeframe == SupportedTimeframe.M30
        assert result[0].timestamp_utc == start

    def test_aggregate_1h_from_60_m1_bars(self) -> None:
        """Sixty 1m bars should aggregate to one 1h bar."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=60)

        result = aggregate_bars(m1_bars, SupportedTimeframe.H1)

        assert len(result) == 1
        assert result[0].timeframe == SupportedTimeframe.H1
        assert result[0].timestamp_utc == start

    def test_aggregate_4h_from_240_m1_bars(self) -> None:
        """240 1m bars should aggregate to one 4h bar."""
        start = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)  # 08:00 (4h boundary)
        m1_bars = make_m1_sequence(start, count=240)

        result = aggregate_bars(m1_bars, SupportedTimeframe.H4)

        assert len(result) == 1
        assert result[0].timeframe == SupportedTimeframe.H4
        assert result[0].timestamp_utc == start


class TestSupportedTimeframe30m:
    """30m is derived-only (no IG fetch)."""

    def test_m30_minutes(self) -> None:
        assert SupportedTimeframe.M30.minutes == 30

    def test_m30_is_ig_native_false(self) -> None:
        assert SupportedTimeframe.M30.is_ig_native is False

    def test_m30_ig_resolution_raises(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="30m is not available from IG"):
            _ = SupportedTimeframe.M30.ig_resolution

    def test_aggregate_from_1m_includes_m30_by_default(self) -> None:
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=60)
        result = aggregate_from_1m(m1_bars)
        assert SupportedTimeframe.M30 in result
        assert len(result[SupportedTimeframe.M30]) == 2  # 60/30 = 2 bars


# =============================================================================
# OHLCV Aggregation Rules Tests
# =============================================================================


class TestAggregateOHLCV:
    """Tests for OHLCV aggregation rules."""

    def test_open_is_first_open(self) -> None:
        """Aggregated open should be the first bar's open."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_m1_bar(start, open_=1.1000),
            make_m1_bar(start + timedelta(minutes=1), open_=1.1100),
            make_m1_bar(start + timedelta(minutes=2), open_=1.1200),
            make_m1_bar(start + timedelta(minutes=3), open_=1.1300),
            make_m1_bar(start + timedelta(minutes=4), open_=1.1400),
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        assert result[0].open == 1.1000  # First bar's open

    def test_high_is_max_high(self) -> None:
        """Aggregated high should be the maximum high."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_m1_bar(start, high=1.1010),
            make_m1_bar(start + timedelta(minutes=1), high=1.1050),  # Max
            make_m1_bar(start + timedelta(minutes=2), high=1.1020),
            make_m1_bar(start + timedelta(minutes=3), high=1.1030),
            make_m1_bar(start + timedelta(minutes=4), high=1.1040),
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        assert result[0].high == 1.1050  # Maximum high

    def test_low_is_min_low(self) -> None:
        """Aggregated low should be the minimum low."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_m1_bar(start, low=1.0990),
            make_m1_bar(start + timedelta(minutes=1), low=1.0980),
            make_m1_bar(start + timedelta(minutes=2), low=1.0950),  # Min
            make_m1_bar(start + timedelta(minutes=3), low=1.0970),
            make_m1_bar(start + timedelta(minutes=4), low=1.0960),
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        assert result[0].low == 1.0950  # Minimum low

    def test_close_is_last_close(self) -> None:
        """Aggregated close should be the last bar's close."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_m1_bar(start, close=1.1005),
            make_m1_bar(start + timedelta(minutes=1), close=1.1015),
            make_m1_bar(start + timedelta(minutes=2), close=1.1025),
            make_m1_bar(start + timedelta(minutes=3), close=1.1035),
            make_m1_bar(start + timedelta(minutes=4), close=1.1045),  # Last
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        assert result[0].close == 1.1045  # Last bar's close

    def test_volume_is_sum(self) -> None:
        """Aggregated volume should be the sum of all volumes."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_m1_bar(start, volume=100),
            make_m1_bar(start + timedelta(minutes=1), volume=200),
            make_m1_bar(start + timedelta(minutes=2), volume=150),
            make_m1_bar(start + timedelta(minutes=3), volume=250),
            make_m1_bar(start + timedelta(minutes=4), volume=300),
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        assert result[0].volume == 1000  # Sum of volumes


# =============================================================================
# Boundary Alignment Tests
# =============================================================================


class TestAggregateBoundaryAlignment:
    """Tests for UTC boundary alignment."""

    def test_5m_bin_starts_at_0_5_10_etc(self) -> None:
        """5m bins should start at :00, :05, :10, etc."""
        # Create 20 1m bars starting at 10:03
        start = datetime(2024, 1, 15, 10, 3, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=20)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)

        # Should have bins starting at 10:00, 10:05, 10:10, 10:15, 10:20
        # But data starts at 10:03, so first complete bin is 10:05
        bin_starts = [b.timestamp_utc.minute for b in result]
        for minute in bin_starts:
            assert minute % 5 == 0

    def test_15m_bin_starts_at_0_15_30_45(self) -> None:
        """15m bins should start at :00, :15, :30, :45."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=60)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M15)

        assert len(result) == 4  # 60 minutes = 4 x 15m bars
        bin_starts = [b.timestamp_utc.minute for b in result]
        assert bin_starts == [0, 15, 30, 45]

    def test_1h_bin_starts_at_top_of_hour(self) -> None:
        """1h bins should start at :00."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=120)

        result = aggregate_bars(m1_bars, SupportedTimeframe.H1)

        assert len(result) == 2  # 120 minutes = 2 hours
        for bar in result:
            assert bar.timestamp_utc.minute == 0

    def test_4h_bin_alignment(self) -> None:
        """4h bins should start at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00."""
        start = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=480)  # 8 hours

        result = aggregate_bars(m1_bars, SupportedTimeframe.H4)

        assert len(result) == 2  # 480 minutes = 2 x 4h bars
        assert result[0].timestamp_utc.hour == 8
        assert result[1].timestamp_utc.hour == 12


# =============================================================================
# Partial Bin Tests
# =============================================================================


class TestAggregatePartialBins:
    """Tests for handling partial bins."""

    def test_partial_bin_at_start(self) -> None:
        """Bars not aligned to bin boundary should create partial first bin."""
        # Start at 10:03 (not aligned to 5m boundary)
        start = datetime(2024, 1, 15, 10, 3, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=10)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)

        # First bin starts at 10:00 (has only 2 bars: 10:03, 10:04)
        # Second bin starts at 10:05 (has 5 bars)
        # Third bin starts at 10:10 (has 3 bars: 10:10, 10:11, 10:12)
        assert len(result) == 3

    def test_partial_bin_at_end(self) -> None:
        """Incomplete bin at end should still be included."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=8)  # 5 + 3

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)

        assert len(result) == 2
        # Second bin has only 3 bars but is still included


# =============================================================================
# No Lookahead Tests
# =============================================================================


class TestNoLookahead:
    """Tests ensuring no lookahead in aggregation."""

    def test_aggregation_uses_bar_start_time(self) -> None:
        """Aggregated bar timestamp should be bin start, not end."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=5)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)

        # The aggregated bar timestamp should be 10:00 (start of bin)
        # NOT 10:05 (end of bin) - that would be lookahead
        assert result[0].timestamp_utc == start

    def test_bars_sorted_before_aggregation(self) -> None:
        """Input bars in wrong order should still aggregate correctly."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Create bars in reverse order
        bars = [
            make_m1_bar(start + timedelta(minutes=4), open_=1.1040, close=1.1045),
            make_m1_bar(start + timedelta(minutes=2), open_=1.1020, close=1.1025),
            make_m1_bar(start + timedelta(minutes=0), open_=1.1000, close=1.1005),
            make_m1_bar(start + timedelta(minutes=3), open_=1.1030, close=1.1035),
            make_m1_bar(start + timedelta(minutes=1), open_=1.1010, close=1.1015),
        ]

        result = aggregate_bars(bars, SupportedTimeframe.M5)

        # Open should be first bar (10:00), close should be last (10:04)
        assert result[0].open == 1.1000  # From 10:00 bar
        assert result[0].close == 1.1045  # From 10:04 bar


# =============================================================================
# aggregate_from_1m Tests
# =============================================================================


class TestAggregateFrom1m:
    """Tests for aggregate_from_1m function."""

    def test_aggregate_to_all_timeframes(self) -> None:
        """Should aggregate to all derived timeframes by default."""
        start = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=240)

        result = aggregate_from_1m(m1_bars)

        assert SupportedTimeframe.M5 in result
        assert SupportedTimeframe.M15 in result
        assert SupportedTimeframe.M30 in result
        assert SupportedTimeframe.H1 in result
        assert SupportedTimeframe.H4 in result
        assert SupportedTimeframe.M1 not in result  # Base should not be in result

    def test_aggregate_to_specific_timeframes(self) -> None:
        """Should aggregate only to specified timeframes."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=60)

        result = aggregate_from_1m(
            m1_bars,
            target_timeframes=[SupportedTimeframe.M5, SupportedTimeframe.M15],
        )

        assert SupportedTimeframe.M5 in result
        assert SupportedTimeframe.M15 in result
        assert SupportedTimeframe.H1 not in result
        assert SupportedTimeframe.H4 not in result

    def test_aggregate_empty_input(self) -> None:
        """Empty input should return empty dict."""
        result = aggregate_from_1m([])

        assert result == {}

    def test_excludes_1m_from_targets(self) -> None:
        """1m in target list should be ignored."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=10)

        result = aggregate_from_1m(
            m1_bars,
            target_timeframes=[SupportedTimeframe.M1, SupportedTimeframe.M5],
        )

        assert SupportedTimeframe.M1 not in result
        assert SupportedTimeframe.M5 in result


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestGetBinStart:
    """Tests for get_bin_start utility function."""

    def test_5m_bin_start(self) -> None:
        """Should return correct 5m bin start."""
        ts = datetime(2024, 1, 15, 10, 7, 30, tzinfo=UTC)
        bin_start = get_bin_start(ts, SupportedTimeframe.M5)

        assert bin_start == datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC)

    def test_15m_bin_start(self) -> None:
        """Should return correct 15m bin start."""
        ts = datetime(2024, 1, 15, 10, 23, 45, tzinfo=UTC)
        bin_start = get_bin_start(ts, SupportedTimeframe.M15)

        assert bin_start == datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)

    def test_1h_bin_start(self) -> None:
        """Should return correct 1h bin start."""
        ts = datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC)
        bin_start = get_bin_start(ts, SupportedTimeframe.H1)

        assert bin_start == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_4h_bin_start(self) -> None:
        """Should return correct 4h bin start."""
        ts = datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC)
        bin_start = get_bin_start(ts, SupportedTimeframe.H4)

        assert bin_start == datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

    def test_naive_timestamp_handled(self) -> None:
        """Should handle naive timestamp by assuming UTC."""
        ts = datetime(2024, 1, 15, 10, 7, 30)  # No tzinfo
        bin_start = get_bin_start(ts, SupportedTimeframe.M5)

        assert bin_start.tzinfo == UTC


class TestValidateAggregationAlignment:
    """Tests for validate_aggregation_alignment utility function."""

    def test_aligned_bars_no_warnings(self) -> None:
        """Properly aligned bars should produce no warnings."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_m1_sequence(start, count=10)

        result = aggregate_bars(m1_bars, SupportedTimeframe.M5)
        warnings = validate_aggregation_alignment(result, SupportedTimeframe.M5)

        assert warnings == []

    def test_misaligned_bars_produce_warnings(self) -> None:
        """Bars with non-zero seconds should produce warnings."""
        bar = HistoricalBar(
            timestamp_utc=datetime(2024, 1, 15, 10, 5, 30, tzinfo=UTC),
            instrument_symbol="EURUSD",
            timeframe=SupportedTimeframe.M5,
            open=1.1,
            high=1.2,
            low=1.0,
            close=1.15,
            volume=100,
        )

        warnings = validate_aggregation_alignment([bar], SupportedTimeframe.M5)

        assert len(warnings) == 1
        assert "non-zero seconds" in warnings[0]

    def test_wrong_minute_alignment(self) -> None:
        """Bars at wrong minute for timeframe should produce warnings."""
        bar = HistoricalBar(
            timestamp_utc=datetime(2024, 1, 15, 10, 3, 0, tzinfo=UTC),  # Not 5m aligned
            instrument_symbol="EURUSD",
            timeframe=SupportedTimeframe.M5,
            open=1.1,
            high=1.2,
            low=1.0,
            close=1.15,
            volume=100,
        )

        warnings = validate_aggregation_alignment([bar], SupportedTimeframe.M5)

        assert len(warnings) == 1
        assert "not aligned" in warnings[0]
