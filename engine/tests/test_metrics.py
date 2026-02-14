"""
Tests for metrics calculations.

Verifies Sharpe, max drawdown, and other metrics.
"""

from datetime import UTC, datetime, timedelta

import pytest

from solat_engine.backtest.metrics import (
    calculate_avg_drawdown_metrics,
    calculate_consecutive_streaks,
    calculate_distribution_stats,
    calculate_downside_volatility,
    calculate_execution_metrics,
    calculate_max_drawdown,
    calculate_median_bars_held,
    calculate_median_return_pct,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_trade_metrics,
    calculate_volatility,
    compute_metrics_summary,
)
from solat_engine.backtest.models import (
    EquityPoint,
    OrderAction,
    OrderRecord,
    OrderStatus,
    PositionSide,
    TradeRecord,
)

# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def simple_equity_curve() -> list[EquityPoint]:
    """Create a simple equity curve for testing."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        EquityPoint(
            timestamp=base + timedelta(days=i),
            equity=100000 + i * 100,  # Linear growth
            cash=100000 + i * 100,
            unrealized_pnl=0,
            realized_pnl=i * 100,
            drawdown=0,
            drawdown_pct=0,
            high_water_mark=100000 + i * 100,
        )
        for i in range(100)
    ]


@pytest.fixture
def drawdown_equity_curve() -> list[EquityPoint]:
    """Create an equity curve with a drawdown."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    equities = [
        100000, 101000, 102000, 103000, 104000,  # Up
        103000, 102000, 100000, 98000, 96000,    # Down (drawdown)
        97000, 98000, 99000, 100000, 101000,     # Recovery
    ]
    hwm = 100000
    points = []
    for i, eq in enumerate(equities):
        hwm = max(hwm, eq)
        dd = hwm - eq
        dd_pct = dd / hwm if hwm > 0 else 0
        points.append(EquityPoint(
            timestamp=base + timedelta(days=i),
            equity=eq,
            cash=eq,
            unrealized_pnl=0,
            realized_pnl=eq - 100000,
            drawdown=dd,
            drawdown_pct=dd_pct,
            high_water_mark=hwm,
        ))
    return points


@pytest.fixture
def sample_trades() -> list[TradeRecord]:
    """Create sample trades for testing."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        TradeRecord(
            symbol="EURUSD",
            bot="TestBot",
            side=PositionSide.LONG,
            entry_time=base,
            exit_time=base + timedelta(hours=1),
            entry_price=1.10000,
            exit_price=1.10100,
            size=1.0,
            pnl=100.0,
            pnl_pct=0.0909,
            bars_held=60,
            exit_reason="take_profit",
        ),
        TradeRecord(
            symbol="EURUSD",
            bot="TestBot",
            side=PositionSide.LONG,
            entry_time=base + timedelta(days=1),
            exit_time=base + timedelta(days=1, hours=1),
            entry_price=1.10000,
            exit_price=1.09900,
            size=1.0,
            pnl=-100.0,
            pnl_pct=-0.0909,
            bars_held=60,
            exit_reason="stop_loss",
        ),
        TradeRecord(
            symbol="EURUSD",
            bot="TestBot",
            side=PositionSide.SHORT,
            entry_time=base + timedelta(days=2),
            exit_time=base + timedelta(days=2, hours=2),
            entry_price=1.10000,
            exit_price=1.09800,
            size=1.0,
            pnl=200.0,
            pnl_pct=0.1818,
            bars_held=120,
            exit_reason="take_profit",
        ),
    ]


# =============================================================================
# Return Calculation Tests
# =============================================================================


class TestReturns:
    """Tests for return calculations."""

    def test_calculate_returns_simple(self, simple_equity_curve: list[EquityPoint]) -> None:
        """Returns should be calculated correctly."""
        returns = calculate_returns(simple_equity_curve)

        # Should have n-1 returns
        assert len(returns) == len(simple_equity_curve) - 1

        # All returns should be positive (linear growth)
        assert all(r > 0 for r in returns)

    def test_calculate_returns_empty(self) -> None:
        """Empty curve should return empty returns."""
        returns = calculate_returns([])
        assert returns == []

    def test_calculate_returns_single_point(
        self, simple_equity_curve: list[EquityPoint]
    ) -> None:
        """Single point should return empty returns."""
        returns = calculate_returns(simple_equity_curve[:1])
        assert returns == []


# =============================================================================
# Sharpe Ratio Tests
# =============================================================================


class TestSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_sharpe_positive_returns(self) -> None:
        """Positive consistent returns should have positive Sharpe."""
        returns = [0.001] * 100  # Constant positive returns
        sharpe = calculate_sharpe_ratio(returns, periods_per_year=252)

        # Very high Sharpe due to zero volatility in consistent returns
        # (In practice this would be infinite, but small float differences create some std)
        assert sharpe > 0

    def test_sharpe_negative_returns(self) -> None:
        """Negative consistent returns should have negative Sharpe."""
        returns = [-0.001] * 100  # Constant negative returns
        sharpe = calculate_sharpe_ratio(returns, periods_per_year=252)

        assert sharpe < 0

    def test_sharpe_empty_returns(self) -> None:
        """Empty returns should return 0."""
        sharpe = calculate_sharpe_ratio([])
        assert sharpe == 0.0

    def test_sharpe_single_return(self) -> None:
        """Single return should return 0."""
        sharpe = calculate_sharpe_ratio([0.01])
        assert sharpe == 0.0


# =============================================================================
# Sortino Ratio Tests
# =============================================================================


class TestSortinoRatio:
    """Tests for Sortino ratio calculation."""

    def test_sortino_all_positive(self) -> None:
        """All positive returns should have high Sortino."""
        returns = [0.001, 0.002, 0.0015, 0.0018, 0.001] * 20
        sortino = calculate_sortino_ratio(returns, periods_per_year=252)

        # Should be infinity or very high (no downside)
        assert sortino > 0

    def test_sortino_with_negative(self) -> None:
        """Mixed returns should have finite Sortino."""
        returns = [0.01, -0.005, 0.008, -0.003, 0.012] * 20
        sortino = calculate_sortino_ratio(returns, periods_per_year=252)

        # Should be positive but finite
        assert sortino > 0


# =============================================================================
# Max Drawdown Tests
# =============================================================================


class TestMaxDrawdown:
    """Tests for maximum drawdown calculation."""

    def test_max_drawdown_with_drawdown(
        self, drawdown_equity_curve: list[EquityPoint]
    ) -> None:
        """Should correctly identify max drawdown."""
        max_dd, max_dd_pct, max_duration = calculate_max_drawdown(drawdown_equity_curve)

        # Peak was 104000, trough was 96000
        # Drawdown = 104000 - 96000 = 8000
        assert abs(max_dd - 8000) < 1.0

        # Percentage: 8000/104000 ≈ 7.69%
        assert abs(max_dd_pct - (8000 / 104000)) < 0.01

    def test_max_drawdown_no_drawdown(
        self, simple_equity_curve: list[EquityPoint]
    ) -> None:
        """No drawdown should return 0."""
        max_dd, max_dd_pct, max_duration = calculate_max_drawdown(simple_equity_curve)

        assert max_dd == 0.0
        assert max_dd_pct == 0.0

    def test_max_drawdown_empty(self) -> None:
        """Empty curve should return 0."""
        max_dd, max_dd_pct, max_duration = calculate_max_drawdown([])

        assert max_dd == 0.0
        assert max_dd_pct == 0.0
        assert max_duration == 0


# =============================================================================
# Volatility Tests
# =============================================================================


class TestVolatility:
    """Tests for volatility calculation."""

    def test_volatility_constant_returns(self) -> None:
        """Constant returns should have near-zero volatility."""
        returns = [0.001] * 100
        vol = calculate_volatility(returns, periods_per_year=252)

        # Should be very small (only float precision differences)
        assert vol < 0.01

    def test_volatility_varying_returns(self) -> None:
        """Varying returns should have positive volatility."""
        returns = [0.01, -0.02, 0.015, -0.005, 0.008] * 20
        vol = calculate_volatility(returns, periods_per_year=252)

        assert vol > 0


# =============================================================================
# Trade Metrics Tests
# =============================================================================


class TestTradeMetrics:
    """Tests for trade-level metrics."""

    def test_trade_metrics_calculation(self, sample_trades: list[TradeRecord]) -> None:
        """Trade metrics should be calculated correctly."""
        metrics = calculate_trade_metrics(sample_trades)

        # Total trades
        assert metrics["total_trades"] == 3

        # Win rate: 2 wins out of 3
        assert abs(metrics["win_rate"] - (2 / 3)) < 0.01

        # Winning/losing trades
        assert metrics["winning_trades"] == 2
        assert metrics["losing_trades"] == 1

    def test_trade_metrics_profit_factor(self, sample_trades: list[TradeRecord]) -> None:
        """Profit factor should be calculated correctly."""
        metrics = calculate_trade_metrics(sample_trades)

        # Gross profit: 100 + 200 = 300
        # Gross loss: 100
        # Profit factor: 300/100 = 3.0
        assert abs(metrics["profit_factor"] - 3.0) < 0.01

    def test_trade_metrics_expectancy(self, sample_trades: list[TradeRecord]) -> None:
        """Expectancy should be calculated correctly."""
        metrics = calculate_trade_metrics(sample_trades)

        # Win rate: 2/3
        # Avg win: (100 + 200) / 2 = 150
        # Loss rate: 1/3
        # Avg loss: 100
        # Expectancy = (2/3 * 150) - (1/3 * 100) = 100 - 33.33 = 66.67
        assert abs(metrics["expectancy"] - 66.67) < 1.0

    def test_trade_metrics_empty(self) -> None:
        """Empty trades should return zero metrics."""
        metrics = calculate_trade_metrics([])

        assert metrics["total_trades"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["profit_factor"] == 0.0


# =============================================================================
# Summary Computation Tests
# =============================================================================


class TestMetricsSummary:
    """Tests for complete metrics summary computation."""

    def test_compute_metrics_summary(
        self,
        simple_equity_curve: list[EquityPoint],
        sample_trades: list[TradeRecord],
    ) -> None:
        """Should compute complete metrics summary."""
        summary = compute_metrics_summary(
            equity_curve=simple_equity_curve,
            trades=sample_trades,
            initial_cash=100000.0,
        )

        # Should have all metrics
        assert summary.total_trades == 3
        assert summary.total_return > 0
        assert summary.sharpe_ratio is not None
        assert summary.max_drawdown >= 0

    def test_compute_metrics_summary_with_filters(
        self,
        simple_equity_curve: list[EquityPoint],
        sample_trades: list[TradeRecord],
    ) -> None:
        """Should filter by bot/symbol."""
        summary = compute_metrics_summary(
            equity_curve=simple_equity_curve,
            trades=sample_trades,
            initial_cash=100000.0,
            bot="TestBot",
            symbol="EURUSD",
        )

        assert summary.bot == "TestBot"
        assert summary.symbol == "EURUSD"
        assert summary.total_trades == 3


# =============================================================================
# Consecutive Streaks Tests
# =============================================================================


class TestConsecutiveStreaks:
    """Tests for consecutive win/loss streak calculation."""

    def test_empty_trades(self) -> None:
        assert calculate_consecutive_streaks([]) == (0, 0)

    def test_all_winners(self, sample_trades: list[TradeRecord]) -> None:
        """3 winners in a row."""
        base = datetime(2024, 1, 1, tzinfo=UTC)
        winners = [
            TradeRecord(
                symbol="EURUSD", bot="TestBot", side=PositionSide.LONG,
                entry_time=base + timedelta(days=i),
                exit_time=base + timedelta(days=i, hours=1),
                entry_price=1.1, exit_price=1.102, size=1.0,
                pnl=200.0, pnl_pct=0.18, bars_held=60,
            )
            for i in range(3)
        ]
        max_w, max_l = calculate_consecutive_streaks(winners)
        assert max_w == 3
        assert max_l == 0

    def test_all_losers(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=UTC)
        losers = [
            TradeRecord(
                symbol="EURUSD", bot="TestBot", side=PositionSide.LONG,
                entry_time=base + timedelta(days=i),
                exit_time=base + timedelta(days=i, hours=1),
                entry_price=1.1, exit_price=1.098, size=1.0,
                pnl=-200.0, pnl_pct=-0.18, bars_held=60,
            )
            for i in range(4)
        ]
        max_w, max_l = calculate_consecutive_streaks(losers)
        assert max_w == 0
        assert max_l == 4

    def test_mixed_sample_trades(self, sample_trades: list[TradeRecord]) -> None:
        """sample_trades: win, loss, win => max_wins=1, max_losses=1."""
        max_w, max_l = calculate_consecutive_streaks(sample_trades)
        assert max_w == 1
        assert max_l == 1

    def test_alternating_streak(self) -> None:
        """W W W L L W => max_wins=3, max_losses=2."""
        base = datetime(2024, 1, 1, tzinfo=UTC)
        pnls = [100, 50, 200, -100, -50, 150]
        trades = [
            TradeRecord(
                symbol="EURUSD", bot="TestBot", side=PositionSide.LONG,
                entry_time=base + timedelta(days=i),
                exit_time=base + timedelta(days=i, hours=1),
                entry_price=1.1, exit_price=1.1, size=1.0,
                pnl=float(p), pnl_pct=float(p) / 10000, bars_held=60,
            )
            for i, p in enumerate(pnls)
        ]
        max_w, max_l = calculate_consecutive_streaks(trades)
        assert max_w == 3
        assert max_l == 2

    def test_breakeven_trade_resets_streaks(self) -> None:
        """pnl=0 is a streak-breaker — resets both counters."""
        base = datetime(2024, 1, 1, tzinfo=UTC)
        pnls = [100, 100, 0, 100]  # W W break W => max_wins=2 (not 3)
        trades = [
            TradeRecord(
                symbol="EURUSD", bot="TestBot", side=PositionSide.LONG,
                entry_time=base + timedelta(days=i),
                exit_time=base + timedelta(days=i, hours=1),
                entry_price=1.1, exit_price=1.1, size=1.0,
                pnl=float(p), pnl_pct=float(p) / 10000, bars_held=60,
            )
            for i, p in enumerate(pnls)
        ]
        max_w, max_l = calculate_consecutive_streaks(trades)
        assert max_w == 2
        assert max_l == 0


# =============================================================================
# Median Metrics Tests
# =============================================================================


class TestMedianMetrics:
    """Tests for median return and bars held."""

    def test_median_return_empty(self) -> None:
        assert calculate_median_return_pct([]) == 0.0

    def test_median_return_sample(self, sample_trades: list[TradeRecord]) -> None:
        """sample_trades pnl_pcts: [0.0909, -0.0909, 0.1818] => median=0.0909."""
        result = calculate_median_return_pct(sample_trades)
        assert abs(result - 0.0909) < 0.001

    def test_median_bars_empty(self) -> None:
        assert calculate_median_bars_held([]) == 0.0

    def test_median_bars_sample(self, sample_trades: list[TradeRecord]) -> None:
        """sample_trades bars_held: [60, 60, 120] => median=60."""
        result = calculate_median_bars_held(sample_trades)
        assert result == 60.0

    def test_median_bars_even_count(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=UTC)
        trades = [
            TradeRecord(
                symbol="EURUSD", bot="TestBot", side=PositionSide.LONG,
                entry_time=base + timedelta(days=i),
                exit_time=base + timedelta(days=i, hours=1),
                entry_price=1.1, exit_price=1.102, size=1.0,
                pnl=100.0, pnl_pct=0.01, bars_held=bh,
            )
            for i, bh in enumerate([10, 20, 30, 40])
        ]
        # median of [10,20,30,40] = 25
        assert calculate_median_bars_held(trades) == 25.0


# =============================================================================
# Distribution Stats Tests
# =============================================================================


class TestDistributionStats:
    """Tests for skewness and kurtosis calculation."""

    def test_empty_returns(self) -> None:
        assert calculate_distribution_stats([]) == (0.0, 0.0)

    def test_two_returns(self) -> None:
        """Fewer than 3 returns should give (0,0)."""
        assert calculate_distribution_stats([0.01, -0.01]) == (0.0, 0.0)

    def test_symmetric_returns(self) -> None:
        """Perfectly symmetric distribution has skewness ~0."""
        returns = [0.01, -0.01, 0.02, -0.02, 0.03, -0.03] * 10
        skew, kurt = calculate_distribution_stats(returns)
        assert abs(skew) < 0.01  # Near zero for symmetric

    def test_positive_skew(self) -> None:
        """Right-skewed distribution (many small losses, few large wins)."""
        returns = [-0.001] * 80 + [0.01] * 20
        skew, kurt = calculate_distribution_stats(returns)
        assert skew > 0  # Positive (right) skew

    def test_negative_skew(self) -> None:
        """Left-skewed distribution (many small wins, few large losses)."""
        returns = [0.001] * 80 + [-0.01] * 20
        skew, kurt = calculate_distribution_stats(returns)
        assert skew < 0  # Negative (left) skew

    def test_uniform_returns_excess_kurtosis(self) -> None:
        """Uniform distribution has excess kurtosis < 0 (platykurtic)."""
        import random
        rng = random.Random(42)
        returns = [rng.uniform(-0.01, 0.01) for _ in range(1000)]
        _, kurt = calculate_distribution_stats(returns)
        assert kurt < 0  # Uniform is platykurtic

    def test_constant_returns(self) -> None:
        """Constant returns => zero variance => (0, 0)."""
        returns = [0.001] * 100
        skew, kurt = calculate_distribution_stats(returns)
        assert skew == 0.0
        assert kurt == 0.0


# =============================================================================
# Downside Volatility Tests
# =============================================================================


class TestDownsideVolatility:
    """Tests for downside volatility calculation."""

    def test_empty(self) -> None:
        assert calculate_downside_volatility([]) == 0.0

    def test_single_return(self) -> None:
        assert calculate_downside_volatility([0.01]) == 0.0

    def test_all_positive(self) -> None:
        """All positive returns => zero downside vol."""
        returns = [0.001, 0.002, 0.0015, 0.0018] * 25
        assert calculate_downside_volatility(returns) == 0.0

    def test_all_negative(self) -> None:
        """All negative returns => positive downside vol."""
        returns = [-0.001, -0.002, -0.0015, -0.0018] * 25
        dvol = calculate_downside_volatility(returns, periods_per_year=252)
        assert dvol > 0

    def test_mixed_returns(self) -> None:
        """Mixed returns => downside vol driven only by negative."""
        returns = [0.01, -0.005, 0.008, -0.003, 0.012, -0.001] * 20
        dvol = calculate_downside_volatility(returns, periods_per_year=252)
        assert dvol > 0

    def test_downside_less_than_total_vol(self) -> None:
        """Downside vol should be <= total vol for mixed returns."""
        returns = [0.01, -0.005, 0.008, -0.003, 0.012, -0.001] * 20
        dvol = calculate_downside_volatility(returns, periods_per_year=252)
        tvol = calculate_volatility(returns, periods_per_year=252)
        assert dvol <= tvol


# =============================================================================
# Average Drawdown Metrics Tests
# =============================================================================


class TestAvgDrawdownMetrics:
    """Tests for average drawdown percentage and duration."""

    def test_empty_curve(self) -> None:
        assert calculate_avg_drawdown_metrics([]) == (0.0, 0.0)

    def test_no_drawdown(self, simple_equity_curve: list[EquityPoint]) -> None:
        """Linear growth => no drawdown."""
        avg_dd, avg_dur = calculate_avg_drawdown_metrics(simple_equity_curve)
        assert avg_dd == 0.0
        assert avg_dur == 0.0

    def test_single_drawdown(self, drawdown_equity_curve: list[EquityPoint]) -> None:
        """Should detect the drawdown in sample curve."""
        avg_dd, avg_dur = calculate_avg_drawdown_metrics(drawdown_equity_curve)
        assert avg_dd > 0
        assert avg_dur > 0

    def test_two_drawdowns(self) -> None:
        """Two separate drawdowns should be averaged."""
        base = datetime(2024, 1, 1, tzinfo=UTC)
        # Up, down, recover, down again, recover
        equities = [
            100000, 102000,  # Up
            100000, 98000,   # DD1: peak 102k, trough 98k => 3.92%
            102000, 104000,  # Recover + new high
            102000, 100000,  # DD2: peak 104k, trough 100k => 3.85%
            104000, 106000,  # Recover
        ]
        hwm = equities[0]
        points = []
        for i, eq in enumerate(equities):
            hwm = max(hwm, eq)
            dd = hwm - eq
            dd_pct = dd / hwm if hwm > 0 else 0
            points.append(EquityPoint(
                timestamp=base + timedelta(days=i),
                equity=eq, cash=eq, unrealized_pnl=0,
                realized_pnl=eq - 100000,
                drawdown=dd, drawdown_pct=dd_pct,
                high_water_mark=hwm,
            ))
        avg_dd, avg_dur = calculate_avg_drawdown_metrics(points)
        # Two drawdowns: ~3.92% and ~3.85% → average ~3.88%
        assert 0.03 < avg_dd < 0.05
        assert avg_dur == 2.0  # Each drawdown lasts 2 bars


# =============================================================================
# Execution Metrics Tests
# =============================================================================


class TestExecutionMetrics:
    """Tests for execution realism metrics."""

    def test_none_inputs(self) -> None:
        result = calculate_execution_metrics(None, None)
        assert result["total_orders"] == 0
        assert result["avg_spread_paid"] == 0.0

    def test_fill_summary_only(self) -> None:
        summary = {
            "total_orders": 100,
            "filled_orders": 95,
            "rejected_orders": 5,
            "total_spread_cost": 50.0,
            "total_slippage_cost": 10.0,
            "total_fees": 25.0,
            "total_transaction_costs": 85.0,
        }
        result = calculate_execution_metrics(fill_summary=summary)
        assert result["total_orders"] == 100
        assert result["filled_orders"] == 95
        assert result["rejected_orders"] == 5
        assert result["total_spread_cost"] == 50.0
        assert result["total_transaction_costs"] == 85.0
        # No orders passed, so avg_spread and avg_slippage remain 0
        assert result["avg_spread_paid"] == 0.0
        assert result["avg_slippage"] == 0.0

    def test_orders_with_spread_and_slippage(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=UTC)
        orders = [
            OrderRecord(
                timestamp=base, symbol="EURUSD", bot="TestBot",
                action=OrderAction.BUY, size=1.0,
                price_requested=1.1, price_filled=1.10012,
                status=OrderStatus.FILLED,
                spread_applied=0.0001, slippage_applied=0.00002,
                fees_applied=2.0,
            ),
            OrderRecord(
                timestamp=base + timedelta(hours=1), symbol="EURUSD", bot="TestBot",
                action=OrderAction.SELL, size=1.0,
                price_requested=1.102, price_filled=1.10188,
                status=OrderStatus.FILLED,
                spread_applied=0.0001, slippage_applied=0.00004,
                fees_applied=2.0,
            ),
            # Rejected order (no price_filled)
            OrderRecord(
                timestamp=base + timedelta(hours=2), symbol="EURUSD", bot="TestBot",
                action=OrderAction.BUY, size=1.0,
                price_requested=1.103, price_filled=None,
                status=OrderStatus.REJECTED,
                spread_applied=0.0, slippage_applied=0.0,
                fees_applied=0.0, rejection_reason="max_positions",
            ),
        ]
        result = calculate_execution_metrics(orders=orders)
        # Only 2 filled orders
        assert abs(result["avg_spread_paid"] - 0.0001) < 1e-8
        assert abs(result["avg_slippage"] - 0.00003) < 1e-8

    def test_combined_orders_and_summary(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=UTC)
        orders = [
            OrderRecord(
                timestamp=base, symbol="EURUSD", bot="TestBot",
                action=OrderAction.BUY, size=1.0,
                price_requested=1.1, price_filled=1.10012,
                status=OrderStatus.FILLED,
                spread_applied=0.0002, slippage_applied=0.0001,
                fees_applied=2.0,
            ),
        ]
        summary = {
            "total_orders": 10,
            "filled_orders": 9,
            "rejected_orders": 1,
            "total_spread_cost": 20.0,
            "total_slippage_cost": 5.0,
            "total_fees": 18.0,
            "total_transaction_costs": 43.0,
        }
        result = calculate_execution_metrics(orders=orders, fill_summary=summary)
        # fill_summary provides counts/totals
        assert result["total_orders"] == 10
        # orders provide per-fill averages
        assert abs(result["avg_spread_paid"] - 0.0002) < 1e-8


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Verify compute_metrics_summary still works without new optional params."""

    def test_old_call_signature(
        self,
        simple_equity_curve: list[EquityPoint],
        sample_trades: list[TradeRecord],
    ) -> None:
        """Original 3-arg call should still work and produce valid metrics."""
        summary = compute_metrics_summary(
            equity_curve=simple_equity_curve,
            trades=sample_trades,
            initial_cash=100000.0,
        )
        assert summary.total_trades == 3
        assert summary.sharpe_ratio is not None
        # New fields should have their defaults
        assert summary.skewness is not None  # Will be computed from returns
        assert summary.data_gaps_detected == 0
        assert summary.nan_inf_checks_passed is True

    def test_new_optional_params(
        self,
        simple_equity_curve: list[EquityPoint],
        sample_trades: list[TradeRecord],
    ) -> None:
        """Passing new optional params should populate extended fields."""
        summary = compute_metrics_summary(
            equity_curve=simple_equity_curve,
            trades=sample_trades,
            initial_cash=100000.0,
            run_id="test-run-123",
            timeframe="1h",
            data_start=datetime(2024, 1, 1, tzinfo=UTC),
            data_end=datetime(2024, 12, 31, tzinfo=UTC),
            warnings_count=3,
            data_gaps_detected=2,
        )
        assert summary.run_id == "test-run-123"
        assert summary.timeframe == "1h"
        assert summary.warnings_count == 3
        assert summary.data_gaps_detected == 2
        # Distribution stats should be computed
        assert isinstance(summary.skewness, float)
        assert isinstance(summary.kurtosis, float)

    def test_execution_metrics_in_summary(
        self,
        simple_equity_curve: list[EquityPoint],
        sample_trades: list[TradeRecord],
    ) -> None:
        """Passing fill_summary should populate execution fields."""
        fill_summary = {
            "total_orders": 50,
            "filled_orders": 48,
            "rejected_orders": 2,
            "total_spread_cost": 25.0,
            "total_slippage_cost": 5.0,
            "total_fees": 10.0,
            "total_transaction_costs": 40.0,
        }
        summary = compute_metrics_summary(
            equity_curve=simple_equity_curve,
            trades=sample_trades,
            initial_cash=100000.0,
            fill_summary=fill_summary,
        )
        assert summary.total_orders == 50
        assert summary.filled_orders == 48
        assert summary.rejected_orders == 2
        assert summary.total_transaction_costs == 40.0
