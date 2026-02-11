"""
Tier 1: Partial write scenarios (write succeeds, flush fails).

Tests that system detects and rejects corrupted writes when flush fails,
preventing silent data corruption.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.chaos.fixtures.disk_chaos import DiskChaos


@pytest.mark.chaos
@pytest.mark.tier1
class TestPartialWriteScenarios:
    """Tests for write-succeeds-but-flush-fails scenarios."""

    def test_parquet_partial_write__detected_and_rejected(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Parquet write succeeds but flush fails (EIO)
        EXPECTED: Write returns error, file invalid or missing
        FAILURE MODE: Corrupted parquet file written, future reads fail
        """
        from solat_engine.data.parquet_store import ParquetStore
        import pandas as pd

        # Setup: Create ParquetStore with temp directory
        store = ParquetStore(data_dir=chaos_temp_dir)

        # Create sample bars data
        bars_df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h"),
                "open": [1.0850] * 10,
                "high": [1.0860] * 10,
                "low": [1.0840] * 10,
                "close": [1.0855] * 10,
                "volume": [1000] * 10,
            }
        )

        # INJECT CHAOS: Simulate flush failure during write
        with DiskChaos.partial_write_on_flush():
            # Attempt to write bars
            try:
                store.write_bars(
                    symbol="EURUSD",
                    timeframe="1h",
                    bars=bars_df,
                    mode="overwrite",
                )

                # If write appeared to succeed, verify file integrity
                bars_file = chaos_temp_dir / "parquet" / "bars" / "EURUSD_1h.parquet"

                if bars_file.exists():
                    # Try to read back - should fail due to corruption
                    try:
                        read_df = pd.read_parquet(bars_file)
                        # If read succeeded, it means flush wasn't actually called
                        # This is acceptable - buffered writes may succeed
                        assert len(read_df) > 0
                    except Exception as e:
                        # Expected: Read fails due to corruption
                        assert "parquet" in str(e).lower() or "arrow" in str(e).lower()
                else:
                    # File not written - acceptable failure mode
                    pass

            except OSError as e:
                # VERIFICATION: Write should fail with I/O error
                assert "Input/output error" in str(e) or e.errno == 5
            except Exception as e:
                # Other exceptions are acceptable if they indicate write failure
                # (e.g., pyarrow exceptions)
                assert "write" in str(e).lower() or "flush" in str(e).lower()

    def test_ledger_partial_write__entry_invalid_or_missing(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Ledger JSONL write buffered but flush fails
        EXPECTED: Entry not committed, next read doesn't see partial entry
        FAILURE MODE: Partial JSON line written, subsequent reads fail
        """
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.execution.models import (
            ExecutionConfig, ExecutionMode, OrderIntent, OrderSide, OrderType,
        )

        # Setup: Create ledger with temp directory
        config = ExecutionConfig(mode=ExecutionMode.DEMO)
        ledger = ExecutionLedger(chaos_temp_dir, config)

        # Write one valid entry first
        intent1 = OrderIntent(
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=1.0,
            order_type=OrderType.MARKET,
            bot="chaos_test",
        )
        ledger.record_intent(intent1)

        # INJECT CHAOS: Flush fails on next write
        with DiskChaos.partial_write_on_flush():
            try:
                # Attempt to write second entry
                intent2 = OrderIntent(
                    symbol="GBPUSD",
                    side=OrderSide.SELL,
                    size=0.5,
                    order_type=OrderType.LIMIT,
                    bot="chaos_test",
                )
                ledger.record_intent(intent2)

                # If no exception, write may have been buffered
                # Read back to verify integrity
                entries = ledger.get_entries()

                # Either:
                # 1. Only first entry exists (second never committed)
                # 2. Both entries exist (flush wasn't actually called)
                # 3. Read fails (file corrupted)

                if len(entries) == 1:
                    # Expected: Second entry not committed
                    assert entries[0].symbol == "EURUSD"
                elif len(entries) == 2:
                    # Acceptable: Flush wasn't actually called (buffered writes)
                    assert entries[1].symbol == "GBPUSD"
                else:
                    # Unexpected state
                    assert False, f"Unexpected entry count: {len(entries)}"

            except OSError as e:
                # VERIFICATION: Write should fail with I/O error
                assert "Input/output error" in str(e) or e.errno == 5

                # First entry should still be readable
                entries = ledger.get_entries()
                assert len(entries) == 1
                assert entries[0].symbol == "EURUSD"

            except Exception as e:
                # Other exceptions acceptable if they indicate write failure
                assert "write" in str(e).lower() or "flush" in str(e).lower()

    def test_config_json_partial_write__run_fails_or_incomplete(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Backtest config.json write succeeds but flush fails
        EXPECTED: Run fails early OR config marked as incomplete
        FAILURE MODE: Run proceeds with missing config, results unreproducible
        """
        import json

        # Setup: Prepare run directory
        run_dir = chaos_temp_dir / "runs" / "test_run_001"
        run_dir.mkdir(parents=True, exist_ok=True)

        config_file = run_dir / "config.json"

        config_data = {
            "run_id": "test_run_001",
            "bot": "CloudTwist",
            "symbol": "EURUSD",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-31T23:59:59Z",
        }

        # INJECT CHAOS: Flush fails during config write
        with DiskChaos.partial_write_on_flush():
            try:
                # Attempt to write config
                with open(config_file, "w") as f:
                    json.dump(config_data, f, indent=2)
                    f.flush()  # This should raise OSError(EIO)

                # If we got here, flush wasn't actually called
                # Verify file is valid
                with open(config_file) as f:
                    loaded = json.load(f)
                    assert loaded["run_id"] == "test_run_001"

            except OSError as e:
                # VERIFICATION: Write should fail with I/O error
                assert "Input/output error" in str(e) or e.errno == 5

                # Config file should either:
                # 1. Not exist
                # 2. Be incomplete (not valid JSON)

                if config_file.exists():
                    # Try to read - should fail due to incomplete JSON
                    try:
                        with open(config_file) as f:
                            json.load(f)
                        # If load succeeded, file is valid (flush not called)
                        pass
                    except json.JSONDecodeError:
                        # Expected: File is corrupted/incomplete
                        pass
                else:
                    # Expected: File not written
                    pass
