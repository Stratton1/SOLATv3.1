"""
Tests for data quality validation.

Tests detection of gaps, duplicates, out-of-order timestamps, and spikes.
NO REAL IG CALLS - uses fixed test data.
"""

from datetime import UTC, datetime, timedelta

from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.quality import (
    check_data_quality,
    check_monotonic_timestamps,
    check_no_duplicates,
    estimate_missing_bars,
)

# =============================================================================
# Fixtures
# =============================================================================


def make_bar(
    timestamp: datetime,
    symbol: str = "EURUSD",
    timeframe: SupportedTimeframe = SupportedTimeframe.M1,
    open_: float = 1.1000,
    high: float = 1.1010,
    low: float = 1.0990,
    close: float = 1.1005,
    volume: float = 100.0,
) -> HistoricalBar:
    """Create a test bar."""
    return HistoricalBar(
        timestamp_utc=timestamp,
        instrument_symbol=symbol,
        timeframe=timeframe,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def make_clean_bars(
    start: datetime,
    count: int,
    symbol: str = "EURUSD",
    timeframe: SupportedTimeframe = SupportedTimeframe.M1,
) -> list[HistoricalBar]:
    """Create a sequence of clean (no issues) bars."""
    minutes = timeframe.minutes
    bars = []
    for i in range(count):
        ts = start + timedelta(minutes=i * minutes)
        bar = make_bar(
            timestamp=ts,
            symbol=symbol,
            timeframe=timeframe,
            open_=1.1000 + i * 0.0001,
            high=1.1010 + i * 0.0001,
            low=1.0990 + i * 0.0001,
            close=1.1005 + i * 0.0001,
        )
        bars.append(bar)
    return bars


# =============================================================================
# Duplicate Detection Tests
# =============================================================================


class TestDuplicateDetection:
    """Tests for duplicate timestamp detection."""

    def test_no_duplicates_clean_data(self) -> None:
        """Clean data should have no duplicates."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=100)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.duplicate_count == 0
        assert not any(i.issue_type == "duplicate" for i in report.issues)

    def test_detects_single_duplicate(self) -> None:
        """Should detect a single duplicate timestamp."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=10)
        # Add a duplicate of bar 5
        bars.append(make_bar(start + timedelta(minutes=5)))

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.duplicate_count == 1
        assert any(i.issue_type == "duplicate" for i in report.issues)

    def test_detects_multiple_duplicates(self) -> None:
        """Should detect multiple duplicate timestamps."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=10)
        # Add duplicates
        bars.append(make_bar(start + timedelta(minutes=3)))
        bars.append(make_bar(start + timedelta(minutes=7)))

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.duplicate_count == 2

    def test_check_no_duplicates_returns_timestamps(self) -> None:
        """check_no_duplicates should return list of duplicate timestamps."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=5)
        dup_ts = start + timedelta(minutes=2)
        bars.append(make_bar(dup_ts))

        duplicates = check_no_duplicates(bars)

        assert len(duplicates) == 1
        assert duplicates[0] == dup_ts


# =============================================================================
# Gap Detection Tests
# =============================================================================


class TestGapDetection:
    """Tests for gap detection."""

    def test_no_gaps_clean_data(self) -> None:
        """Clean data should have no gaps."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=100)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.gap_count == 0

    def test_detects_small_gap(self) -> None:
        """Should detect a gap beyond tolerance."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=1)),
            make_bar(start + timedelta(minutes=5)),  # Gap of 4 minutes (> 1.5x)
            make_bar(start + timedelta(minutes=6)),
        ]

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            gap_tolerance_multiplier=1.5,
        )

        assert report.gap_count == 1
        gap_issues = [i for i in report.issues if i.issue_type == "gap"]
        assert len(gap_issues) == 1
        assert gap_issues[0].severity == "warning"  # < 5x is warning

    def test_detects_large_gap_as_error(self) -> None:
        """Large gaps (> 5x expected) should be errors."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=10)),  # Gap of 10 minutes (> 5x)
        ]

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            gap_tolerance_multiplier=1.5,
        )

        assert report.gap_count == 1
        gap_issues = [i for i in report.issues if i.issue_type == "gap"]
        assert gap_issues[0].severity == "error"

    def test_gap_tolerance_configurable(self) -> None:
        """Gap tolerance should be configurable."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=3)),  # Gap of 3 minutes
        ]

        # With low tolerance (1.5x), this is a gap
        report_strict = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            gap_tolerance_multiplier=1.5,
        )
        assert report_strict.gap_count == 1

        # With high tolerance (5x), this is not a gap
        report_lenient = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            gap_tolerance_multiplier=5.0,
        )
        assert report_lenient.gap_count == 0

    def test_gaps_for_5m_timeframe(self) -> None:
        """Gap detection should work for 5m timeframe."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start, timeframe=SupportedTimeframe.M5),
            make_bar(start + timedelta(minutes=5), timeframe=SupportedTimeframe.M5),
            make_bar(start + timedelta(minutes=20), timeframe=SupportedTimeframe.M5),  # Gap
        ]

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M5,
            gap_tolerance_multiplier=1.5,
        )

        assert report.gap_count == 1


# =============================================================================
# Out-of-Order Detection Tests
# =============================================================================


class TestOutOfOrderDetection:
    """Tests for out-of-order timestamp detection."""

    def test_no_out_of_order_clean_data(self) -> None:
        """Clean data should have no out-of-order timestamps."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=50)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.out_of_order_count == 0

    def test_detects_out_of_order(self) -> None:
        """Should detect out-of-order timestamps."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=2)),
            make_bar(start + timedelta(minutes=1)),  # Out of order
            make_bar(start + timedelta(minutes=3)),
        ]

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.out_of_order_count == 1
        ooo_issues = [i for i in report.issues if i.issue_type == "out_of_order"]
        assert len(ooo_issues) == 1
        assert ooo_issues[0].severity == "error"

    def test_check_monotonic_timestamps(self) -> None:
        """check_monotonic_timestamps should return False for out-of-order."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ordered = make_clean_bars(start, count=10)
        unordered = ordered.copy()
        unordered[3], unordered[5] = unordered[5], unordered[3]

        assert check_monotonic_timestamps(ordered) is True
        assert check_monotonic_timestamps(unordered) is False

    def test_monotonic_empty_and_single(self) -> None:
        """Empty and single-bar lists should be monotonic."""
        assert check_monotonic_timestamps([]) is True
        bar = make_bar(datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        assert check_monotonic_timestamps([bar]) is True


# =============================================================================
# Spike Detection Tests
# =============================================================================


class TestSpikeDetection:
    """Tests for price spike detection."""

    def test_no_spikes_normal_data(self) -> None:
        """Normal price movements should not trigger spike detection."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=50)

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            detect_spikes=True,
            spike_threshold=0.1,  # 10%
        )

        assert report.spike_count == 0

    def test_detects_spike(self) -> None:
        """Should detect large price spike."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start, close=1.1000),
            make_bar(start + timedelta(minutes=1), open_=1.2500),  # 13.6% jump
        ]

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            detect_spikes=True,
            spike_threshold=0.1,
        )

        assert report.spike_count == 1
        spike_issues = [i for i in report.issues if i.issue_type == "spike"]
        assert len(spike_issues) == 1
        assert spike_issues[0].severity == "warning"

    def test_spike_detection_disabled(self) -> None:
        """Spike detection should be disableable."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start, close=1.1000),
            make_bar(start + timedelta(minutes=1), open_=1.5000),  # Huge spike
        ]

        report = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            detect_spikes=False,
        )

        assert report.spike_count == 0

    def test_spike_threshold_configurable(self) -> None:
        """Spike threshold should be configurable."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start, close=1.1000),
            make_bar(start + timedelta(minutes=1), open_=1.1600),  # 5.5% jump
        ]

        # With 5% threshold, this is a spike
        report_strict = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            detect_spikes=True,
            spike_threshold=0.05,
        )
        assert report_strict.spike_count == 1

        # With 10% threshold, this is not a spike
        report_lenient = check_data_quality(
            bars,
            symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            detect_spikes=True,
            spike_threshold=0.10,
        )
        assert report_lenient.spike_count == 0


# =============================================================================
# Report Properties Tests
# =============================================================================


class TestReportProperties:
    """Tests for DataQualityReport properties."""

    def test_is_clean_true(self) -> None:
        """is_clean should be True for clean data."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=50)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.is_clean is True

    def test_is_clean_false_with_issues(self) -> None:
        """is_clean should be False when issues exist."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=10)
        bars.append(make_bar(start))  # Add duplicate

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.is_clean is False

    def test_has_errors_true(self) -> None:
        """has_errors should be True when errors exist."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=2)),
            make_bar(start + timedelta(minutes=1)),  # Out of order = error
        ]

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.has_errors is True

    def test_has_errors_false_warnings_only(self) -> None:
        """has_errors should be False when only warnings exist."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=10)
        # Insert duplicate at position 0 so it's still in order
        bars.insert(0, make_bar(start))  # Duplicate = warning (but in correct order)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.has_errors is False
        assert len(report.issues) > 0  # Has warnings

    def test_total_bars_count(self) -> None:
        """total_bars should reflect input count."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=42)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.total_bars == 42


# =============================================================================
# Missing Bars Estimation Tests
# =============================================================================


class TestEstimateMissingBars:
    """Tests for estimate_missing_bars function."""

    def test_no_missing_complete_data(self) -> None:
        """Complete data should have 0 missing bars."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=60)

        result = estimate_missing_bars(bars, SupportedTimeframe.M1)

        assert result["total_missing"] == 0
        assert result["coverage_pct"] == 100.0

    def test_estimates_missing_with_gaps(self) -> None:
        """Should estimate missing bars when gaps exist."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = [
            make_bar(start),
            make_bar(start + timedelta(minutes=1)),
            # Gap: missing minutes 2, 3, 4
            make_bar(start + timedelta(minutes=5)),
            make_bar(start + timedelta(minutes=6)),
        ]

        result = estimate_missing_bars(bars, SupportedTimeframe.M1)

        # Time range 0-6 = 7 bars expected, 4 present
        assert result["total_expected"] == 7
        assert result["total_present"] == 4
        assert result["total_missing"] == 3

    def test_estimates_with_expected_range(self) -> None:
        """Should use expected range when provided."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=30)

        # Expect 60 minutes of data
        expected_end = start + timedelta(minutes=59)
        result = estimate_missing_bars(
            bars,
            SupportedTimeframe.M1,
            expected_start=start,
            expected_end=expected_end,
        )

        assert result["total_expected"] == 60
        assert result["total_present"] == 30
        assert result["total_missing"] == 30
        assert result["coverage_pct"] == 50.0

    def test_empty_bars_returns_zeros(self) -> None:
        """Empty input should return zeros."""
        result = estimate_missing_bars([], SupportedTimeframe.M1)

        assert result["total_expected"] == 0
        assert result["total_present"] == 0
        assert result["total_missing"] == 0
        assert result["coverage_pct"] == 0.0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_single_bar(self) -> None:
        """Single bar should produce no issues."""
        bar = make_bar(datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))

        report = check_data_quality(
            [bar], symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.is_clean is True
        assert report.total_bars == 1

    def test_two_bars_normal(self) -> None:
        """Two consecutive bars should produce no issues."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=2)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.is_clean is True

    def test_very_large_dataset(self) -> None:
        """Should handle large datasets efficiently."""
        start = datetime(2024, 1, 15, 0, 0, 0, tzinfo=UTC)
        bars = make_clean_bars(start, count=10000)

        report = check_data_quality(
            bars, symbol="EURUSD", timeframe=SupportedTimeframe.M1
        )

        assert report.is_clean is True
        assert report.total_bars == 10000
