"""
Tests for ParquetStore - writes, reads, deduplication.

NO REAL IG CALLS - uses local fixtures only.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_store():  # type: ignore[no-untyped-def]
    """Create a temporary ParquetStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ParquetStore(Path(tmpdir))


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


def make_bars(
    start: datetime,
    count: int,
    symbol: str = "EURUSD",
    timeframe: SupportedTimeframe = SupportedTimeframe.M1,
    interval_minutes: int = 1,
) -> list[HistoricalBar]:
    """Create a sequence of test bars."""
    bars = []
    for i in range(count):
        ts = start + timedelta(minutes=i * interval_minutes)
        bar = make_bar(
            timestamp=ts,
            symbol=symbol,
            timeframe=timeframe,
            open_=1.1000 + i * 0.0001,
            high=1.1010 + i * 0.0001,
            low=1.0990 + i * 0.0001,
            close=1.1005 + i * 0.0001,
            volume=100.0 + i,
        )
        bars.append(bar)
    return bars


# =============================================================================
# Write Tests
# =============================================================================


class TestParquetStoreWrite:
    """Tests for ParquetStore write operations."""

    def test_write_single_bar(self, temp_store: ParquetStore) -> None:
        """Writing a single bar should succeed."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bar = make_bar(start)

        written, deduped = temp_store.write_bars([bar], run_id="test-run")

        assert written == 1
        assert deduped == 0

    def test_write_multiple_bars(self, temp_store: ParquetStore) -> None:
        """Writing multiple bars should succeed."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)

        written, deduped = temp_store.write_bars(bars, run_id="test-run")

        assert written == 100
        assert deduped == 0

    def test_write_empty_list(self, temp_store: ParquetStore) -> None:
        """Writing empty list should return zeros."""
        written, deduped = temp_store.write_bars([])

        assert written == 0
        assert deduped == 0

    def test_write_updates_manifest(self, temp_store: ParquetStore) -> None:
        """Writing should update the manifest entry."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=10)

        temp_store.write_bars(bars, run_id="test-run-123")

        manifest = temp_store.get_manifest("EURUSD", SupportedTimeframe.M1)
        assert manifest is not None
        assert manifest.row_count == 10
        assert manifest.last_run_id == "test-run-123"
        assert manifest.first_available_from == start
        assert manifest.last_synced_to == start + timedelta(minutes=9)

    def test_write_multiple_symbols(self, temp_store: ParquetStore) -> None:
        """Writing bars for multiple symbols should create separate partitions."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        eurusd_bars = make_bars(start, count=5, symbol="EURUSD")
        gbpusd_bars = make_bars(start, count=3, symbol="GBPUSD")

        all_bars = eurusd_bars + gbpusd_bars
        written, deduped = temp_store.write_bars(all_bars)

        assert written == 8
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 5
        assert temp_store.count_bars("GBPUSD", SupportedTimeframe.M1) == 3

    def test_write_multiple_timeframes(self, temp_store: ParquetStore) -> None:
        """Writing bars for multiple timeframes should create separate partitions."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m1_bars = make_bars(start, count=5, timeframe=SupportedTimeframe.M1)
        m5_bars = make_bars(start, count=3, timeframe=SupportedTimeframe.M5, interval_minutes=5)

        all_bars = m1_bars + m5_bars
        written, _ = temp_store.write_bars(all_bars)

        assert written == 8
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 5
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M5) == 3


# =============================================================================
# Read Tests
# =============================================================================


class TestParquetStoreRead:
    """Tests for ParquetStore read operations."""

    def test_read_all_bars(self, temp_store: ParquetStore) -> None:
        """Reading without filters should return all bars."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=50)
        temp_store.write_bars(bars)

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1)

        assert len(read_bars) == 50

    def test_read_with_start_filter(self, temp_store: ParquetStore) -> None:
        """Reading with start filter should exclude earlier bars."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        # Read from 10:30 onwards (skip first 30 bars)
        filter_start = start + timedelta(minutes=30)
        read_bars = temp_store.read_bars(
            "EURUSD",
            SupportedTimeframe.M1,
            start=filter_start,
        )

        assert len(read_bars) == 70
        assert read_bars[0].timestamp_utc == filter_start

    def test_read_with_end_filter(self, temp_store: ParquetStore) -> None:
        """Reading with end filter should exclude later bars."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        # Read up to 10:30 (first 30 bars, end is exclusive)
        filter_end = start + timedelta(minutes=30)
        read_bars = temp_store.read_bars(
            "EURUSD",
            SupportedTimeframe.M1,
            end=filter_end,
        )

        assert len(read_bars) == 30
        assert read_bars[-1].timestamp_utc == start + timedelta(minutes=29)

    def test_read_with_start_and_end_filter(self, temp_store: ParquetStore) -> None:
        """Reading with both filters should return windowed data."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        # Read 10:20 to 10:40 (20 bars)
        filter_start = start + timedelta(minutes=20)
        filter_end = start + timedelta(minutes=40)
        read_bars = temp_store.read_bars(
            "EURUSD",
            SupportedTimeframe.M1,
            start=filter_start,
            end=filter_end,
        )

        assert len(read_bars) == 20
        assert read_bars[0].timestamp_utc == filter_start
        assert read_bars[-1].timestamp_utc == filter_end - timedelta(minutes=1)

    def test_read_with_limit(self, temp_store: ParquetStore) -> None:
        """Reading with limit should cap results and return latest by default."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1, limit=25)

        assert len(read_bars) == 25
        # Should be LAST 25 bars (sorted by timestamp)
        assert read_bars[0].timestamp_utc == start + timedelta(minutes=75)
        assert read_bars[-1].timestamp_utc == start + timedelta(minutes=99)

    def test_read_returns_sorted_by_timestamp(self, temp_store: ParquetStore) -> None:
        """Read bars should always be sorted by timestamp."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=50)
        temp_store.write_bars(bars)

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1)

        # Verify sorted
        timestamps = [b.timestamp_utc for b in read_bars]
        assert timestamps == sorted(timestamps)

    def test_read_nonexistent_symbol(self, temp_store: ParquetStore) -> None:
        """Reading nonexistent symbol should return empty list."""
        read_bars = temp_store.read_bars("NONEXISTENT", SupportedTimeframe.M1)

        assert read_bars == []

    def test_read_preserves_ohlcv_values(self, temp_store: ParquetStore) -> None:
        """Read bars should have correct OHLCV values."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bar = make_bar(
            timestamp=start,
            open_=1.2345,
            high=1.2400,
            low=1.2300,
            close=1.2380,
            volume=5000.0,
        )
        temp_store.write_bars([bar])

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1)

        assert len(read_bars) == 1
        assert read_bars[0].open == 1.2345
        assert read_bars[0].high == 1.2400
        assert read_bars[0].low == 1.2300
        assert read_bars[0].close == 1.2380
        assert read_bars[0].volume == 5000.0


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestParquetStoreDeduplication:
    """Tests for ParquetStore deduplication."""

    def test_dedupe_exact_duplicates(self, temp_store: ParquetStore) -> None:
        """Exact duplicate bars should be deduplicated."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bar1 = make_bar(start, close=1.1000)
        bar2 = make_bar(start, close=1.1000)  # Same timestamp

        written, deduped = temp_store.write_bars([bar1, bar2])

        assert written == 2  # Both were written
        assert deduped == 1  # One was deduped
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 1

    def test_dedupe_keeps_latest(self, temp_store: ParquetStore) -> None:
        """Deduplication should keep the latest ingested bar."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # First write
        bar1 = make_bar(start, close=1.1000)
        temp_store.write_bars([bar1])

        # Second write with same timestamp but different price
        bar2 = make_bar(start, close=1.2000)
        temp_store.write_bars([bar2])

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1)

        assert len(read_bars) == 1
        assert read_bars[0].close == 1.2000  # Latest value kept

    def test_dedupe_with_append(self, temp_store: ParquetStore) -> None:
        """Appending new bars with some overlapping timestamps should dedupe."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # First batch: 0-9 minutes
        batch1 = make_bars(start, count=10)
        temp_store.write_bars(batch1)

        # Second batch: 5-14 minutes (overlaps 5-9)
        batch2 = make_bars(start + timedelta(minutes=5), count=10)
        written, deduped = temp_store.write_bars(batch2)

        assert written == 10
        assert deduped == 5  # 5 overlapping bars
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 15

    def test_dedupe_preserves_sort_order(self, temp_store: ParquetStore) -> None:
        """After deduplication, bars should remain sorted."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Write in reverse order
        bars_reverse = list(reversed(make_bars(start, count=20)))
        temp_store.write_bars(bars_reverse)

        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1)
        timestamps = [b.timestamp_utc for b in read_bars]

        assert timestamps == sorted(timestamps)


# =============================================================================
# Summary and Manifest Tests
# =============================================================================


class TestParquetStoreSummary:
    """Tests for ParquetStore summary operations."""

    def test_get_summary_all(self, temp_store: ParquetStore) -> None:
        """Get summary should return all stored data info."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Create data for multiple symbols/timeframes
        temp_store.write_bars(make_bars(start, count=10, symbol="EURUSD"))
        temp_store.write_bars(make_bars(start, count=5, symbol="GBPUSD"))
        temp_store.write_bars(
            make_bars(start, count=3, symbol="EURUSD", timeframe=SupportedTimeframe.M5)
        )

        summaries = temp_store.get_summary()

        assert len(summaries) == 3

    def test_get_summary_filter_symbol(self, temp_store: ParquetStore) -> None:
        """Get summary with symbol filter should return only that symbol."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        temp_store.write_bars(make_bars(start, count=10, symbol="EURUSD"))
        temp_store.write_bars(make_bars(start, count=5, symbol="GBPUSD"))

        summaries = temp_store.get_summary(symbol="EURUSD")

        assert len(summaries) == 1
        assert summaries[0]["symbol"] == "EURUSD"

    def test_get_summary_filter_timeframe(self, temp_store: ParquetStore) -> None:
        """Get summary with timeframe filter should return only that timeframe."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        temp_store.write_bars(
            make_bars(start, count=10, timeframe=SupportedTimeframe.M1)
        )
        temp_store.write_bars(
            make_bars(start, count=5, timeframe=SupportedTimeframe.M5, interval_minutes=5)
        )

        summaries = temp_store.get_summary(timeframe=SupportedTimeframe.M1)

        assert len(summaries) == 1
        assert summaries[0]["timeframe"] == "1m"

    def test_count_bars(self, temp_store: ParquetStore) -> None:
        """Count bars should return correct count."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        temp_store.write_bars(make_bars(start, count=42))

        count = temp_store.count_bars("EURUSD", SupportedTimeframe.M1)

        assert count == 42

    def test_count_bars_nonexistent(self, temp_store: ParquetStore) -> None:
        """Count bars for nonexistent symbol should return 0."""
        count = temp_store.count_bars("NONEXISTENT", SupportedTimeframe.M1)

        assert count == 0


# =============================================================================
# Clear/Delete Tests
# =============================================================================


class TestParquetStoreClear:
    """Tests for ParquetStore clear operations."""

    def test_clear_partition(self, temp_store: ParquetStore) -> None:
        """Clear partition should remove all data for symbol/timeframe."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        temp_store.write_bars(make_bars(start, count=50))

        deleted = temp_store.clear_partition("EURUSD", SupportedTimeframe.M1)

        assert deleted is True
        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 0
        assert temp_store.get_manifest("EURUSD", SupportedTimeframe.M1) is None

    def test_clear_nonexistent_partition(self, temp_store: ParquetStore) -> None:
        """Clearing nonexistent partition should return False."""
        deleted = temp_store.clear_partition("NONEXISTENT", SupportedTimeframe.M1)

        assert deleted is False

    def test_clear_one_partition_preserves_others(self, temp_store: ParquetStore) -> None:
        """Clearing one partition should not affect others."""
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        temp_store.write_bars(make_bars(start, count=10, symbol="EURUSD"))
        temp_store.write_bars(make_bars(start, count=5, symbol="GBPUSD"))

        temp_store.clear_partition("EURUSD", SupportedTimeframe.M1)

        assert temp_store.count_bars("EURUSD", SupportedTimeframe.M1) == 0
        assert temp_store.count_bars("GBPUSD", SupportedTimeframe.M1) == 5
