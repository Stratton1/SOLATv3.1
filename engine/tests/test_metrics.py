"""
Tests for metrics calculations.

Verifies Sharpe, max drawdown, and other metrics.
"""

from datetime import UTC, datetime, timedelta

import pytest

from solat_engine.backtest.metrics import (
    calculate_max_drawdown,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_trade_metrics,
    calculate_volatility,
    compute_metrics_summary,
)
from solat_engine.backtest.models import EquityPoint, PositionSide, TradeRecord

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
