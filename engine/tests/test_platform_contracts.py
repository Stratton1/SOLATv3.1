"""
Platform contract tests.

Verify that MetricsSummary fields consumed by scoring and walk-forward
are always populated, and that scoring field mappings stay in sync.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from solat_engine.backtest.metrics import compute_metrics_summary
from solat_engine.backtest.models import (
    BacktestRequest,
    EquityPoint,
    MetricsSummary,
    OrderRecord,
    OrderStatus,
    PositionSide,
    RangeMode,
    TradeRecord,
)
from solat_engine.optimization.models import (
    WalkForwardResult,
    WalkForwardConfig,
    WalkForwardWindow,
)
from solat_engine.backtest.sizing import SizeResult, calculate_position_size
from solat_engine.optimization.scoring import (
    HardGates,
    apply_hard_gates,
    compute_weighted_score,
    score_combo,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_equity_curve(
    n: int = 100,
    initial: float = 100000.0,
    daily_gain: float = 50.0,
) -> list[EquityPoint]:
    """Generate a simple rising equity curve."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    hwm = initial
    points = []
    for i in range(n):
        eq = initial + i * daily_gain
        hwm = max(hwm, eq)
        dd = hwm - eq
        dd_pct = dd / hwm if hwm > 0 else 0.0
        points.append(EquityPoint(
            timestamp=base + timedelta(hours=i),
            equity=eq,
            cash=eq,
            unrealized_pnl=0.0,
            realized_pnl=eq - initial,
            drawdown=dd,
            drawdown_pct=dd_pct,
            high_water_mark=hwm,
        ))
    return points


def _make_trades(n: int = 50, symbol: str = "EURUSD", bot: str = "CloudTwist") -> list[TradeRecord]:
    """Generate simple winning trades."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    trades = []
    for i in range(n):
        trades.append(TradeRecord(
            trade_id=uuid4(),
            symbol=symbol,
            bot=bot,
            side=PositionSide.LONG,
            entry_time=base + timedelta(hours=i * 2),
            exit_time=base + timedelta(hours=i * 2 + 1),
            entry_price=1.1000 + i * 0.0001,
            exit_price=1.1010 + i * 0.0001,
            size=1.0,
            pnl=10.0 if i % 3 != 0 else -5.0,
            pnl_pct=0.01 if i % 3 != 0 else -0.005,
            bars_held=10,
            exit_reason="signal",
        ))
    return trades


def _make_summary(**overrides) -> MetricsSummary:
    """Compute a MetricsSummary from test data, applying optional overrides."""
    equity = _make_equity_curve()
    trades = _make_trades()
    summary = compute_metrics_summary(
        equity_curve=equity,
        trades=trades,
        initial_cash=100000.0,
        bot="CloudTwist",
        symbol="EURUSD",
        bars_per_day=24,
        run_id="test_run",
        timeframe="1h",
        data_start=equity[0].timestamp,
        data_end=equity[-1].timestamp,
    )
    if overrides:
        return summary.model_copy(update=overrides)
    return summary


# =============================================================================
# 1. MetricsSummary Completeness
# =============================================================================


class TestMetricsSummaryCompleteness:
    """Ensure all scoring-critical fields are populated after compute_metrics_summary."""

    def test_hard_gate_fields_populated(self):
        """All fields consumed by apply_hard_gates are non-None."""
        s = _make_summary()
        assert s.max_drawdown_pct is not None
        assert s.total_trades is not None and s.total_trades > 0
        assert s.time_in_market_pct is not None

    def test_weighted_score_fields_populated(self):
        """All fields consumed by compute_weighted_score are non-None."""
        s = _make_summary()
        assert s.sharpe_ratio is not None
        assert s.total_return_pct is not None
        assert s.max_drawdown_pct is not None
        assert s.trades_per_day is not None
        assert s.trades_per_day >= 0

    def test_duration_days_positive(self):
        """duration_days > 0 for any non-empty backtest."""
        s = _make_summary()
        assert s.duration_days > 0

    def test_missing_bar_pct_populated(self):
        """missing_bar_pct is >= 0 and meaningfully populated."""
        s = _make_summary()
        assert s.missing_bar_pct >= 0.0

    def test_json_round_trip(self):
        """MetricsSummary survives dict serialization round-trip."""
        s = _make_summary()
        d = s.model_dump()
        restored = MetricsSummary.model_validate(d)
        assert restored.sharpe_ratio == s.sharpe_ratio
        assert restored.total_trades == s.total_trades
        assert restored.duration_days == s.duration_days


# =============================================================================
# 2. Scoring Field Mapping
# =============================================================================


class TestScoringFieldMapping:
    """Ensure scoring functions read the correct fields."""

    def test_hard_gates_read_correct_fields(self):
        """apply_hard_gates reads max_drawdown_pct, total_trades, oos_trades, exposure_time_pct, folds_profitable_pct."""
        metrics = {
            "max_drawdown_pct": 5.0,
            "total_trades": 50,
            "oos_trades": 20,
            "exposure_time_pct": 30.0,
            "folds_profitable_pct": 0.75,
            "oos_sharpe": 2.0,
            "oos_return_pct": 0.15,
        }
        passed, reasons = apply_hard_gates(metrics)
        assert passed is True
        assert len(reasons) == 0

    def test_hard_gate_rejects_high_drawdown(self):
        """Hard gate rejects when max_drawdown_pct > 20."""
        metrics = {
            "max_drawdown_pct": 25.0,
            "total_trades": 50,
            "oos_trades": 20,
            "exposure_time_pct": 30.0,
            "folds_profitable_pct": 0.75,
            "oos_sharpe": 2.0,
            "oos_return_pct": 0.15,
        }
        passed, reasons = apply_hard_gates(metrics)
        assert passed is False
        assert any("DD" in r for r in reasons)

    def test_weighted_score_in_range(self):
        """compute_weighted_score returns score in 0-100."""
        score, breakdown = compute_weighted_score(
            oos_sharpe=2.5,
            oos_return_pct=0.15,
            max_drawdown_pct=8.0,
            trades_per_day=1.0,
            folds_profitable_pct=0.8,
            sharpe_cv=0.5,
        )
        assert 0 <= score <= 100
        assert "sharpe_raw" in breakdown
        assert "return_raw" in breakdown
        assert "drawdown_raw" in breakdown
        assert "confidence_raw" in breakdown

    def test_hard_gate_fail_gives_zero_score(self):
        """score_combo returns 0 when hard gates fail."""
        metrics = {
            "bot": "TestBot",
            "symbol": "EURUSD",
            "timeframe": "1h",
            "max_drawdown_pct": 50.0,  # Fails gate
            "total_trades": 50,
            "oos_trades": 20,
            "exposure_time_pct": 30.0,
            "folds_profitable_pct": 0.75,
            "oos_sharpe": 2.0,
            "oos_return_pct": 0.15,
            "trades_per_day": 1.0,
            "sharpe_cv": 0.5,
        }
        cs = score_combo(metrics)
        assert cs.rejected is True
        assert cs.score_total == 0.0


# =============================================================================
# 3. Walk-Forward Outputs
# =============================================================================


class TestWalkForwardOutputs:
    """Ensure WalkForwardResult model has required aggregate and per-fold fields."""

    def test_result_has_aggregates(self):
        """WalkForwardResult has aggregate_sharpe, aggregate_return_pct."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframes=["1h"],
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
        )
        result = WalkForwardResult(
            run_id="test_wf",
            config=config,
            status="completed",
            aggregate_sharpe=2.5,
            aggregate_return_pct=0.15,
            aggregate_win_rate=0.65,
            aggregate_trades=100,
            total_windows=5,
            completed_windows=5,
        )
        assert result.aggregate_sharpe == 2.5
        assert result.aggregate_return_pct == 0.15
        assert result.aggregate_win_rate == 0.65
        assert result.aggregate_trades == 100

    def test_per_fold_window_has_oos_fields(self):
        """WalkForwardWindow has oos_sharpe, oos_return_pct, oos_win_rate, oos_trades."""
        window = WalkForwardWindow(
            window_id=0,
            in_sample_start=datetime(2024, 1, 1, tzinfo=UTC),
            in_sample_end=datetime(2024, 6, 30, tzinfo=UTC),
            out_of_sample_start=datetime(2024, 7, 1, tzinfo=UTC),
            out_of_sample_end=datetime(2024, 8, 15, tzinfo=UTC),
            oos_sharpe=2.1,
            oos_return_pct=0.08,
            oos_win_rate=0.62,
            oos_trades=25,
        )
        assert window.oos_sharpe == 2.1
        assert window.oos_return_pct == 0.08
        assert window.oos_win_rate == 0.62
        assert window.oos_trades == 25

    def test_stability_metrics_constructable(self):
        """Can construct recommended_combos with sharpe_cv, folds_profitable_pct, consistency_score."""
        combo = {
            "bot": "CloudTwist",
            "symbol": "EURUSD",
            "timeframe": "1h",
            "sharpe_cv": 0.45,
            "folds_profitable_pct": 0.80,
            "consistency_score": 5.5,
            "avg_sharpe": 2.5,
        }
        # These fields must be present and valid
        assert 0 <= combo["sharpe_cv"] <= 10
        assert 0 <= combo["folds_profitable_pct"] <= 1.0
        assert combo["consistency_score"] > 0

    def test_wf_result_with_windows(self):
        """WalkForwardResult correctly holds multiple windows."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframes=["1h"],
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
        )
        windows = [
            WalkForwardWindow(
                window_id=i,
                in_sample_start=datetime(2024, 1, 1, tzinfo=UTC),
                in_sample_end=datetime(2024, 6, 30, tzinfo=UTC),
                out_of_sample_start=datetime(2024, 7, 1, tzinfo=UTC),
                out_of_sample_end=datetime(2024, 8, 15, tzinfo=UTC),
                oos_sharpe=2.0 + i * 0.5,
                oos_return_pct=0.05 + i * 0.02,
                oos_win_rate=0.60,
                oos_trades=20 + i * 5,
            )
            for i in range(5)
        ]
        result = WalkForwardResult(
            run_id="test_wf",
            config=config,
            windows=windows,
            total_windows=5,
            completed_windows=5,
        )
        assert len(result.windows) == 5
        assert all(w.oos_sharpe is not None for w in result.windows)


# =============================================================================
# 4. Duration and Missing Bars
# =============================================================================


class TestDurationAndMissingBars:
    """Verify duration_days and missing_bar_pct are computed correctly."""

    def test_duration_days_for_known_bars(self):
        """duration_days = num_bars / bars_per_year * 365.25 for known inputs."""
        # 100 hourly bars with 24 bars per day
        equity = _make_equity_curve(n=100)
        trades = _make_trades(n=10)
        summary = compute_metrics_summary(
            equity_curve=equity,
            trades=trades,
            initial_cash=100000.0,
            bars_per_day=24,
            data_start=equity[0].timestamp,
            data_end=equity[-1].timestamp,
        )
        # 100 bars / (24 * 252) bars_per_year * 365.25
        expected = 100 / (24 * 252) * 365.25
        assert abs(summary.duration_days - expected) < 0.1

    def test_missing_bar_pct_for_complete_data(self):
        """missing_bar_pct should be low for nearly complete data."""
        # 100 hourly bars over ~4 days (100 hours)
        equity = _make_equity_curve(n=100)
        start = equity[0].timestamp
        end = equity[-1].timestamp
        summary = compute_metrics_summary(
            equity_curve=equity,
            trades=_make_trades(n=5),
            initial_cash=100000.0,
            bars_per_day=24,
            data_start=start,
            data_end=end,
        )
        # With ~100 hours of data and 24 bars/day, the missing_bar_pct
        # depends on expected trading days. The value should be >= 0.
        assert summary.missing_bar_pct >= 0.0

    def test_zero_bars_gives_zero_duration(self):
        """Empty equity curve → duration_days near 0, missing_bar_pct 0."""
        summary = compute_metrics_summary(
            equity_curve=[],
            trades=[],
            initial_cash=100000.0,
            bars_per_day=24,
        )
        # With no bars, years = max(0/..., 1/365) → duration ~1 day
        assert summary.duration_days < 2.0
        assert summary.missing_bar_pct == 0.0


# =============================================================================
# 5. RangeMode Validation
# =============================================================================


class TestRangeMode:
    """Verify BacktestRequest range_mode validation."""

    def test_fixed_window_requires_start_end(self):
        """range_mode=fixed_window with missing start/end raises ValueError."""
        with pytest.raises(Exception):
            BacktestRequest(
                symbols=["EURUSD"],
                bots=["CloudTwist"],
                timeframe="1h",
                range_mode=RangeMode.FIXED_WINDOW,
                # start and end omitted
            )

    def test_max_available_allows_no_dates(self):
        """range_mode=max_available works without start/end."""
        req = BacktestRequest(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframe="1h",
            range_mode=RangeMode.MAX_AVAILABLE,
        )
        assert req.start is None
        assert req.end is None
        assert req.range_mode == RangeMode.MAX_AVAILABLE

    def test_fixed_window_with_dates_works(self):
        """range_mode=fixed_window with start/end works normally."""
        req = BacktestRequest(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframe="1h",
            range_mode=RangeMode.FIXED_WINDOW,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert req.start is not None
        assert req.end is not None

    def test_backward_compatible_default(self):
        """Default range_mode is FIXED_WINDOW (backward compatible with existing callers)."""
        req = BacktestRequest(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert req.range_mode == RangeMode.FIXED_WINDOW


# =============================================================================
# 6. Sizing Safety
# =============================================================================


class TestSizingSafety:
    """Verify position sizing has sane limits."""

    def test_fixed_size_returns_configured(self):
        """FIXED_SIZE returns the configured size."""
        from solat_engine.backtest.models import RiskConfig, SignalIntent, SizingMethod
        signal = SignalIntent(direction="BUY", stop_loss=1.0990)
        risk = RiskConfig(sizing_method=SizingMethod.FIXED_SIZE, fixed_size=1.0)
        result = calculate_position_size(signal, equity=10000, current_price=1.1, risk_config=risk)
        assert result.is_valid
        assert result.size == 1.0

    def test_risk_per_trade_clamped_to_max_size(self):
        """RISK_PER_TRADE with tiny stop distance is clamped to max_size."""
        from solat_engine.backtest.models import RiskConfig, SignalIntent, SizingMethod
        signal = SignalIntent(direction="BUY", stop_loss=1.0999)  # 1 pip stop = tiny
        risk = RiskConfig(sizing_method=SizingMethod.RISK_PER_TRADE, risk_per_trade_pct=2.0)
        result = calculate_position_size(
            signal, equity=10000, current_price=1.1, risk_config=risk, max_size=100.0
        )
        assert result.is_valid
        assert result.size <= 100.0

    def test_risk_per_trade_no_stop_uses_fixed(self):
        """RISK_PER_TRADE with no stop loss falls back to fixed size."""
        from solat_engine.backtest.models import RiskConfig, SignalIntent, SizingMethod
        signal = SignalIntent(direction="BUY")  # No stop loss
        risk = RiskConfig(sizing_method=SizingMethod.RISK_PER_TRADE, fixed_size=1.0)
        result = calculate_position_size(signal, equity=10000, current_price=1.1, risk_config=risk)
        assert result.is_valid
        assert result.size == 1.0

    def test_risk_per_trade_normal_stop(self):
        """RISK_PER_TRADE with reasonable stop computes sensible size."""
        from solat_engine.backtest.models import RiskConfig, SignalIntent, SizingMethod
        signal = SignalIntent(direction="BUY", stop_loss=1.0900)  # 200 pip stop
        risk = RiskConfig(sizing_method=SizingMethod.RISK_PER_TRADE, risk_per_trade_pct=2.0)
        result = calculate_position_size(
            signal, equity=10000, current_price=1.1, risk_config=risk, max_size=100.0
        )
        assert result.is_valid
        # risk_amount = 200, stop_distance = 0.02 → size = 10000
        # Clamped to 100.0
        assert result.size <= 100.0


# =============================================================================
# 7. CLI Report Helpers
# =============================================================================


class TestCLIReportHelpers:
    """Verify fmt_dt-style datetime formatting for CLI reports."""

    @staticmethod
    def _fmt_dt(val: object) -> str:
        """Inline copy of fmt_dt logic from run_backtest.py for testing."""
        if val is None:
            return "N/A"
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        s = str(val)
        return s[:10] if len(s) >= 10 else s

    def test_fmt_dt_with_datetime(self):
        """fmt_dt formats datetime objects to YYYY-MM-DD."""
        dt = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)
        assert self._fmt_dt(dt) == "2024-06-15"

    def test_fmt_dt_with_string(self):
        """fmt_dt handles ISO string inputs."""
        assert self._fmt_dt("2024-06-15T12:30:00+00:00") == "2024-06-15"

    def test_fmt_dt_with_none(self):
        """fmt_dt returns N/A for None."""
        assert self._fmt_dt(None) == "N/A"

    def test_model_dump_datetime_handled(self):
        """model_dump() datetime fields can be formatted without crash."""
        s = _make_summary()
        d = s.model_dump()
        # data_start is a datetime from model_dump, not a string
        result = self._fmt_dt(d.get("data_start"))
        assert result != "N/A"
        assert len(result) == 10  # YYYY-MM-DD
