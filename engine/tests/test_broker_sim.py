"""
Tests for broker simulation.

Verifies spread, slippage, and fee calculations.
"""

from datetime import UTC, datetime

import pytest

from solat_engine.backtest.broker_sim import BrokerSim
from solat_engine.backtest.models import (
    FeeConfig,
    OrderAction,
    OrderStatus,
    SlippageConfig,
    SpreadConfig,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_broker() -> BrokerSim:
    """Create a broker with default settings."""
    return BrokerSim()


@pytest.fixture
def configured_broker() -> BrokerSim:
    """Create a broker with specific spread/slippage settings."""
    return BrokerSim(
        spread_config=SpreadConfig(
            default_points=2.0,
            per_instrument={"EURUSD": 1.0, "GBPUSD": 2.5},
        ),
        slippage_config=SlippageConfig(
            default_points=0.5,
            per_instrument={"EURUSD": 0.2},
        ),
        fee_config=FeeConfig(
            per_trade_flat=2.0,
            per_lot=1.0,
            percentage=0.01,
        ),
    )


# =============================================================================
# Spread Tests
# =============================================================================


class TestSpread:
    """Tests for spread calculation."""

    def test_default_spread(self, default_broker: BrokerSim) -> None:
        """Should use default spread when no instrument-specific one."""
        spread = default_broker.get_spread("UNKNOWN")
        assert spread == 1.0  # Default

    def test_instrument_specific_spread(self, configured_broker: BrokerSim) -> None:
        """Should use instrument-specific spread when available."""
        eurusd_spread = configured_broker.get_spread("EURUSD")
        assert eurusd_spread == 1.0

        gbpusd_spread = configured_broker.get_spread("GBPUSD")
        assert gbpusd_spread == 2.5

        unknown_spread = configured_broker.get_spread("UNKNOWN")
        assert unknown_spread == 2.0  # Default

    def test_spread_applied_to_buy(self, configured_broker: BrokerSim) -> None:
        """Buy orders should pay the ask (mid + half spread)."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, spread_applied, _ = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.BUY,
            pip_size=pip_size,
        )

        # EURUSD spread is 1.0 points, half spread = 0.5 pips = 0.00005
        # Plus slippage of 0.2 pips = 0.00002
        expected_fill = bar_close + (0.5 * pip_size) + (0.2 * pip_size)
        assert abs(fill_price - expected_fill) < 0.000001

    def test_spread_applied_to_sell(self, configured_broker: BrokerSim) -> None:
        """Sell orders should get the bid (mid - half spread)."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, spread_applied, _ = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.SELL,
            pip_size=pip_size,
        )

        # EURUSD spread is 1.0 points, half spread = 0.5 pips = 0.00005
        # Plus slippage of 0.2 pips = 0.00002
        expected_fill = bar_close - (0.5 * pip_size) - (0.2 * pip_size)
        assert abs(fill_price - expected_fill) < 0.000001


# =============================================================================
# Slippage Tests
# =============================================================================


class TestSlippage:
    """Tests for slippage calculation."""

    def test_default_slippage(self, default_broker: BrokerSim) -> None:
        """Should use default slippage (0)."""
        slippage = default_broker.get_slippage("UNKNOWN")
        assert slippage == 0.0

    def test_instrument_specific_slippage(self, configured_broker: BrokerSim) -> None:
        """Should use instrument-specific slippage when available."""
        eurusd_slip = configured_broker.get_slippage("EURUSD")
        assert eurusd_slip == 0.2

        unknown_slip = configured_broker.get_slippage("UNKNOWN")
        assert unknown_slip == 0.5  # Default

    def test_slippage_increases_buy_price(self, configured_broker: BrokerSim) -> None:
        """Slippage should increase buy price."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, _, slippage_applied = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.BUY,
            pip_size=pip_size,
        )

        # Slippage should be positive (makes buy more expensive)
        assert slippage_applied > 0

    def test_slippage_decreases_sell_price(self, configured_broker: BrokerSim) -> None:
        """Slippage should decrease sell price."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, _, slippage_applied = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.SELL,
            pip_size=pip_size,
        )

        # Fill should be below bar_close
        assert fill_price < bar_close


# =============================================================================
# Fee Tests
# =============================================================================


class TestFees:
    """Tests for fee calculation."""

    def test_flat_fee(self, configured_broker: BrokerSim) -> None:
        """Flat fee should be applied."""
        fees = configured_broker.calculate_fees(size=1.0, price=1.10000)
        # per_trade_flat=2.0, per_lot=1.0, percentage=0.01
        expected = 2.0 + 1.0 + (0.01 / 100 * 1.0 * 1.10000)
        assert abs(fees - expected) < 0.0001

    def test_lot_based_fee(self, configured_broker: BrokerSim) -> None:
        """Fee should scale with lot size."""
        fees_1lot = configured_broker.calculate_fees(size=1.0, price=1.10000)
        fees_2lots = configured_broker.calculate_fees(size=2.0, price=1.10000)

        # Per-lot fee should double
        # Fixed: 2.0 + (1.0 * 1) + pct for 1 lot
        # Fixed: 2.0 + (1.0 * 2) + pct for 2 lots
        lot_fee_diff = fees_2lots - fees_1lot
        assert abs(lot_fee_diff - 1.0 - 0.0001) < 0.01  # ~1 per extra lot + pct

    def test_percentage_fee(self) -> None:
        """Percentage fee should be based on notional."""
        broker = BrokerSim(
            fee_config=FeeConfig(
                per_trade_flat=0.0,
                per_lot=0.0,
                percentage=0.1,  # 0.1%
            ),
        )

        fees = broker.calculate_fees(size=1.0, price=100.0)
        expected = 0.1 / 100 * 100.0  # 0.1% of 100
        assert abs(fees - expected) < 0.0001


# =============================================================================
# Order Execution Tests
# =============================================================================


class TestOrderExecution:
    """Tests for order execution."""

    def test_valid_order_fills(self, configured_broker: BrokerSim) -> None:
        """Valid orders should be filled."""
        order = configured_broker.execute_order(
            symbol="EURUSD",
            bot="TestBot",
            action=OrderAction.BUY,
            size=1.0,
            bar_close=1.10000,
            timestamp=datetime.now(UTC),
        )

        assert order.status == OrderStatus.FILLED
        assert order.price_filled is not None
        assert order.rejection_reason is None

    def test_order_below_min_size_rejected(self, configured_broker: BrokerSim) -> None:
        """Orders below minimum size should be rejected."""
        configured_broker.set_dealing_rules(
            symbol="EURUSD",
            min_size=0.1,
        )

        order = configured_broker.execute_order(
            symbol="EURUSD",
            bot="TestBot",
            action=OrderAction.BUY,
            size=0.01,  # Below min
            bar_close=1.10000,
            timestamp=datetime.now(UTC),
        )

        assert order.status == OrderStatus.REJECTED
        assert "minimum" in order.rejection_reason.lower()

    def test_order_above_max_size_rejected(self, configured_broker: BrokerSim) -> None:
        """Orders above maximum size should be rejected."""
        configured_broker.set_dealing_rules(
            symbol="EURUSD",
            max_size=10.0,
        )

        order = configured_broker.execute_order(
            symbol="EURUSD",
            bot="TestBot",
            action=OrderAction.BUY,
            size=100.0,  # Above max
            bar_close=1.10000,
            timestamp=datetime.now(UTC),
        )

        assert order.status == OrderStatus.REJECTED
        assert "maximum" in order.rejection_reason.lower()

    def test_order_history_tracked(self, configured_broker: BrokerSim) -> None:
        """All orders should be tracked in history."""
        # Execute some orders
        configured_broker.execute_order(
            symbol="EURUSD",
            bot="TestBot",
            action=OrderAction.BUY,
            size=1.0,
            bar_close=1.10000,
            timestamp=datetime.now(UTC),
        )

        configured_broker.execute_order(
            symbol="GBPUSD",
            bot="TestBot",
            action=OrderAction.SELL,
            size=1.0,
            bar_close=1.25000,
            timestamp=datetime.now(UTC),
        )

        assert len(configured_broker.order_history) == 2

    def test_fill_summary(self, configured_broker: BrokerSim) -> None:
        """Fill summary should aggregate costs correctly."""
        configured_broker.execute_order(
            symbol="EURUSD",
            bot="TestBot",
            action=OrderAction.BUY,
            size=1.0,
            bar_close=1.10000,
            timestamp=datetime.now(UTC),
        )

        summary = configured_broker.get_fill_summary()

        assert summary["total_orders"] == 1
        assert summary["filled_orders"] == 1
        assert summary["rejected_orders"] == 0
        assert summary["total_transaction_costs"] > 0


# =============================================================================
# Close Position Tests
# =============================================================================


class TestClosePosition:
    """Tests for position closing."""

    def test_close_long_gets_bid(self, configured_broker: BrokerSim) -> None:
        """Closing a long position should get the bid price."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, _, _ = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.CLOSE_LONG,
            pip_size=pip_size,
        )

        # Should be below bar_close (selling at bid)
        assert fill_price < bar_close

    def test_close_short_gets_ask(self, configured_broker: BrokerSim) -> None:
        """Closing a short position should get the ask price."""
        bar_close = 1.10000
        pip_size = 0.0001

        fill_price, _, _ = configured_broker.calculate_fill_price(
            symbol="EURUSD",
            bar_close=bar_close,
            action=OrderAction.CLOSE_SHORT,
            pip_size=pip_size,
        )

        # Should be above bar_close (buying at ask)
        assert fill_price > bar_close
