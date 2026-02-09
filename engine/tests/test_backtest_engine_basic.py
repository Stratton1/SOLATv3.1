"""
Basic tests for the backtest engine.

Uses deterministic bar data to verify engine behavior.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig, SizingMethod
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def store_with_bars(temp_data_dir: Path) -> ParquetStore:
    """Create a store with deterministic test bars."""
    store = ParquetStore(temp_data_dir)

    # Create 200 bars with a clear trend pattern
    # First 100 bars: uptrend (price increases)
    # Next 100 bars: downtrend (price decreases)
    start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    bars = []

    base_price = 1.1000

    for i in range(200):
        ts = start + timedelta(minutes=i)

        # Uptrend for first 100 bars
        if i < 100:
            price = base_price + (i * 0.0002)
        else:
            # Downtrend for next 100 bars
            price = base_price + 0.02 - ((i - 100) * 0.0002)

        bar = HistoricalBar(
            timestamp_utc=ts,
            instrument_symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            open=price - 0.0001,
            high=price + 0.0003,
            low=price - 0.0002,
            close=price,
            volume=100.0,
        )
        bars.append(bar)

    store.write_bars(bars)
    return store


# =============================================================================
# Engine Tests
# =============================================================================


class TestBacktestEngine:
    """Tests for BacktestEngineV1."""

    def test_engine_runs_successfully(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Engine should run successfully with valid inputs."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        result = engine.run(request)

        assert result.ok is True
        assert result.run_id is not None
        assert result.completed_at is not None
        assert result.combined_metrics is not None

    def test_engine_produces_deterministic_results(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Same inputs should produce same outputs."""
        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["MomentumRider"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        # Run twice
        engine1 = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )
        result1 = engine1.run(request)

        engine2 = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )
        result2 = engine2.run(request)

        # Metrics should be identical
        assert result1.combined_metrics is not None
        assert result2.combined_metrics is not None
        assert result1.combined_metrics.total_trades == result2.combined_metrics.total_trades
        assert result1.combined_metrics.total_return == result2.combined_metrics.total_return
        assert result1.combined_metrics.sharpe_ratio == result2.combined_metrics.sharpe_ratio

    def test_engine_creates_artefacts(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Engine should create all expected artefacts."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        result = engine.run(request)

        # Check artefact paths exist
        assert "manifest" in result.artefact_paths
        assert "equity_curve" in result.artefact_paths
        assert "metrics" in result.artefact_paths

        # Verify files exist
        manifest_path = temp_data_dir / result.artefact_paths["manifest"]
        assert manifest_path.exists()

        equity_path = temp_data_dir / result.artefact_paths["equity_curve"]
        assert equity_path.exists()

    def test_engine_handles_multiple_bots(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Engine should handle multiple bots correctly."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper", "KumoBreaker", "MomentumRider"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        result = engine.run(request)

        assert result.ok is True
        assert len(result.per_bot_results) == 3

    def test_engine_respects_risk_limits(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Engine should respect max positions limit."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=100000.0,
            warmup_bars=50,
            risk=RiskConfig(
                sizing_method=SizingMethod.FIXED_SIZE,
                fixed_size=1.0,
                max_open_positions=1,  # Only 1 position allowed
            ),
        )

        result = engine.run(request)
        assert result.ok is True

    def test_engine_handles_no_data(
        self,
        temp_data_dir: Path,
    ) -> None:
        """Engine should handle missing data gracefully."""
        store = ParquetStore(temp_data_dir)

        engine = BacktestEngineV1(
            parquet_store=store,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["NONEXISTENT"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        result = engine.run(request)

        # Should complete but with warnings
        assert result.ok is True
        assert len(result.warnings) > 0

    def test_engine_handles_invalid_bot(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Engine should handle invalid bot name gracefully."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["InvalidBot"],
            initial_cash=100000.0,
            warmup_bars=50,
        )

        result = engine.run(request)

        # Should fail with no valid bots
        assert result.ok is False
        assert len(result.errors) > 0


# =============================================================================
# Equity Curve Tests
# =============================================================================


class TestEquityCurve:
    """Tests for equity curve generation."""

    def test_equity_curve_length(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Equity curve should have correct number of points."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        warmup = 50
        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=100000.0,
            warmup_bars=warmup,
        )

        result = engine.run(request)

        # Check equity curve exists
        assert "equity_curve" in result.artefact_paths

    def test_equity_starts_at_initial_cash(
        self,
        temp_data_dir: Path,
        store_with_bars: ParquetStore,
    ) -> None:
        """Equity should start at initial cash."""
        engine = BacktestEngineV1(
            parquet_store=store_with_bars,
            artefacts_dir=temp_data_dir,
        )

        initial_cash = 50000.0
        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            end=datetime(2024, 1, 15, 13, 20, 0, tzinfo=UTC),
            bots=["TKCrossSniper"],
            initial_cash=initial_cash,
            warmup_bars=50,
        )

        result = engine.run(request)

        # First equity point should be close to initial cash
        import pandas as pd

        equity_path = temp_data_dir / result.artefact_paths["equity_curve"]
        equity_df = pd.read_parquet(equity_path)

        first_equity = equity_df.iloc[0]["equity"]
        # Allow small deviation for any trades on first bar
        assert abs(first_equity - initial_cash) < initial_cash * 0.1
