"""
Tests for symbol resolution and read_bars latest default.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore


@pytest.fixture
def temp_store():
    """Create a temporary ParquetStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ParquetStore(Path(tmpdir))

def make_bars(start, count, symbol="EURUSD"):
    bars = []
    for i in range(count):
        ts = start + timedelta(minutes=i)
        bar = HistoricalBar(
            timestamp_utc=ts,
            instrument_symbol=symbol,
            timeframe=SupportedTimeframe.M1,
            open=1.1000 + i * 0.0001,
            high=1.1010 + i * 0.0001,
            low=1.0990 + i * 0.0001,
            close=1.1005 + i * 0.0001,
            volume=100.0 + i,
        )
        bars.append(bar)
    return bars

class TestSymbolResolution:
    def test_resolve_storage_symbol(self):
        assert resolve_storage_symbol("XAUUSD") == "GOLD"
        assert resolve_storage_symbol("GER40") == "DAX"
        assert resolve_storage_symbol("EURUSD") == "EURUSD"
        assert resolve_storage_symbol("unknown") == "UNKNOWN"

    def test_read_bars_latest_default(self, temp_store):
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        # Create 100 bars
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        # Read latest 10 bars
        read_bars = temp_store.read_bars("EURUSD", SupportedTimeframe.M1, limit=10)

        assert len(read_bars) == 10
        # Should be bars 90 to 99
        assert read_bars[0].timestamp_utc == start + timedelta(minutes=90)
        assert read_bars[-1].timestamp_utc == start + timedelta(minutes=99)

    def test_read_bars_with_range(self, temp_store):
        start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        bars = make_bars(start, count=100)
        temp_store.write_bars(bars)

        # Read range 10:20 to 10:40 (20 bars), limit 10
        filter_start = start + timedelta(minutes=20)
        filter_end = start + timedelta(minutes=40)
        read_bars = temp_store.read_bars(
            "EURUSD",
            SupportedTimeframe.M1,
            start=filter_start,
            end=filter_end,
            limit=10
        )

        assert len(read_bars) == 10
        # Should be bars 20 to 29 (head of range)
        assert read_bars[0].timestamp_utc == start + timedelta(minutes=20)
        assert read_bars[-1].timestamp_utc == start + timedelta(minutes=29)
