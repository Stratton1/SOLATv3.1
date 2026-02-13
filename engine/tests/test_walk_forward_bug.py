"""
Regression test for Walk-Forward combined_metrics bug (Phase 5.1).
Ensures WFO engine handles empty windows or missing metrics without crashing.
"""

import pytest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from solat_engine.optimization.walk_forward import WalkForwardEngine
from solat_engine.optimization.models import WalkForwardConfig, WindowType, OptimizationMode
from solat_engine.backtest.models import BacktestResult, MetricsSummary, BacktestRequest

@pytest.fixture
def mock_parquet_store():
    return MagicMock()

@pytest.fixture
def wf_engine(mock_parquet_store):
    from solat_engine.optimization.walk_forward import WalkForwardEngine
    return WalkForwardEngine(parquet_store=mock_parquet_store)

class TestWalkForwardBugFix:
    """Verify bug fix for combined_metrics extraction."""

    async def test_handle_missing_metrics_gracefully(self, wf_engine):
        """Should return None and log warning when metrics are missing, not crash."""
        with patch("solat_engine.backtest.engine.BacktestEngineV1.run") as mock_run:
            # Provide valid request object to satisfy Pydantic
            req = BacktestRequest(
                symbols=["EURUSD"],
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                bots=["TKCross"]
            )
            
            # Mock a result where combined_metrics is None (e.g. no data or trades)
            mock_run.return_value = BacktestResult(
                run_id="test-run",
                ok=True,
                started_at=datetime.now(UTC),
                request=req,
                combined_metrics=None,  # THE BUG: This being None used to cause a crash
                per_bot_results=[]
            )
            
            perf = wf_engine._run_single_backtest(
                symbol="EURUSD",
                bot="TKCross",
                timeframe="1h",
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                window_id="window_1",
                is_in_sample=True
            )
            
            assert perf is None  # Should return None instead of crashing
            
    async def test_full_window_skipping(self, wf_engine):
        """Verify WFO can complete even if some windows fail or return no trades."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            timeframes=["1h"],
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 3, 1, tzinfo=UTC),
            window_type=WindowType.ROLLING,
            in_sample_days=30,
            out_of_sample_days=10,
            step_days=10
        )
        
        with patch("solat_engine.backtest.engine.BacktestEngineV1.run") as mock_run:
            # Mock failing result
            mock_run.return_value = None 
            
            # This should complete without raising AttributeError
            result = await wf_engine.run(config, run_id="wf-test-crash-check")
            
            assert result is not None
            assert result.status == "completed"
            assert result.completed_windows >= 0
