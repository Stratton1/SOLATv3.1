"""
Broker simulation for backtesting.

Simulates order execution with configurable spread, slippage, and fees.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from solat_engine.backtest.models import (
    FeeConfig,
    OrderAction,
    OrderRecord,
    OrderStatus,
    SlippageConfig,
    SpreadConfig,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DealingRules:
    """Dealing rules for an instrument."""

    min_size: float = 0.01
    max_size: float = 1000.0
    size_step: float = 0.01
    min_stop_distance: float = 0.0
    max_stop_distance: float = 0.0


@dataclass
class FillResult:
    """Result of attempting to fill an order."""

    success: bool
    fill_price: float | None = None
    spread_applied: float = 0.0
    slippage_applied: float = 0.0
    fees_applied: float = 0.0
    rejection_reason: str | None = None


@dataclass
class BrokerSim:
    """
    Simulated broker for backtesting.

    Fill price model:
    - BUY: fill at (bar_close + half_spread + slippage)
    - SELL: fill at (bar_close - half_spread - slippage)

    Constraints:
    - min_size, max_size, size_step from dealing rules
    - Orders violating constraints are rejected with structured error
    """

    spread_config: SpreadConfig = field(default_factory=SpreadConfig)
    slippage_config: SlippageConfig = field(default_factory=SlippageConfig)
    fee_config: FeeConfig = field(default_factory=FeeConfig)
    dealing_rules: dict[str, DealingRules] = field(default_factory=dict)
    order_history: list[OrderRecord] = field(default_factory=list)
    _warnings: list[str] = field(default_factory=list)

    def get_spread(self, symbol: str) -> float:
        """Get spread in points for a symbol."""
        return self.spread_config.per_instrument.get(
            symbol, self.spread_config.default_points
        )

    def get_slippage(self, symbol: str) -> float:
        """Get slippage in points for a symbol."""
        return self.slippage_config.per_instrument.get(
            symbol, self.slippage_config.default_points
        )

    def get_dealing_rules(self, symbol: str) -> DealingRules:
        """Get dealing rules for a symbol."""
        return self.dealing_rules.get(symbol, DealingRules())

    def calculate_fees(self, size: float, price: float) -> float:
        """Calculate total fees for a trade."""
        notional = size * price
        fees = self.fee_config.per_trade_flat
        fees += self.fee_config.per_lot * size
        fees += self.fee_config.percentage / 100.0 * notional
        return fees

    def validate_order(
        self,
        symbol: str,
        size: float,
        _action: OrderAction,
    ) -> tuple[bool, str | None]:
        """
        Validate order against dealing rules.

        Returns (is_valid, rejection_reason).
        """
        rules = self.get_dealing_rules(symbol)

        if size < rules.min_size:
            return False, f"Size {size} below minimum {rules.min_size}"

        if size > rules.max_size:
            return False, f"Size {size} above maximum {rules.max_size}"

        # Check size step
        if rules.size_step > 0:
            # Allow small floating point tolerance
            remainder = size % rules.size_step
            if remainder > 0.0001 and (rules.size_step - remainder) > 0.0001:
                return False, f"Size {size} not a multiple of step {rules.size_step}"

        return True, None

    def calculate_fill_price(
        self,
        symbol: str,
        bar_close: float,
        action: OrderAction,
        pip_size: float = 0.0001,
    ) -> tuple[float, float, float]:
        """
        Calculate fill price with spread and slippage.

        Returns (fill_price, spread_applied, slippage_applied).
        """
        spread_points = self.get_spread(symbol)
        slippage_points = self.get_slippage(symbol)

        half_spread = (spread_points * pip_size) / 2
        slippage = slippage_points * pip_size

        if action in (OrderAction.BUY,):
            # Buying: pay the ask (above mid)
            fill_price = bar_close + half_spread + slippage
        elif action in (OrderAction.SELL,):
            # Selling: get the bid (below mid)
            fill_price = bar_close - half_spread - slippage
        elif action == OrderAction.CLOSE_LONG:
            # Closing long: selling at bid
            fill_price = bar_close - half_spread - slippage
        elif action == OrderAction.CLOSE_SHORT:
            # Closing short: buying at ask
            fill_price = bar_close + half_spread + slippage
        else:
            fill_price = bar_close

        return fill_price, spread_points * pip_size, slippage_points * pip_size

    def execute_order(
        self,
        symbol: str,
        bot: str,
        action: OrderAction,
        size: float,
        bar_close: float,
        timestamp: datetime,
        pip_size: float = 0.0001,
    ) -> OrderRecord:
        """
        Execute an order and return the order record.

        Orders are either fully filled or rejected (no partial fills in v1).
        """
        order_id = uuid4()

        # Validate order (action passed for future use, e.g., action-specific rules)
        is_valid, rejection_reason = self.validate_order(symbol, size, action)

        if not is_valid:
            order = OrderRecord(
                order_id=order_id,
                timestamp=timestamp,
                symbol=symbol,
                bot=bot,
                action=action,
                size=size,
                price_requested=bar_close,
                price_filled=None,
                status=OrderStatus.REJECTED,
                rejection_reason=rejection_reason,
            )
            self.order_history.append(order)
            self._warnings.append(
                f"Order rejected: {symbol} {action.value} {size} - {rejection_reason}"
            )
            logger.warning(
                "Order rejected: %s %s %.4f - %s",
                symbol,
                action.value,
                size,
                rejection_reason,
            )
            return order

        # Calculate fill price
        fill_price, spread_applied, slippage_applied = self.calculate_fill_price(
            symbol, bar_close, action, pip_size
        )

        # Calculate fees
        fees_applied = self.calculate_fees(size, fill_price)

        # Create filled order
        order = OrderRecord(
            order_id=order_id,
            timestamp=timestamp,
            symbol=symbol,
            bot=bot,
            action=action,
            size=size,
            price_requested=bar_close,
            price_filled=fill_price,
            status=OrderStatus.FILLED,
            spread_applied=spread_applied,
            slippage_applied=slippage_applied,
            fees_applied=fees_applied,
        )

        self.order_history.append(order)

        logger.debug(
            "Order filled: %s %s %.4f @ %.5f (spread=%.5f, slip=%.5f, fees=%.2f)",
            symbol,
            action.value,
            size,
            fill_price,
            spread_applied,
            slippage_applied,
            fees_applied,
        )

        return order

    def set_dealing_rules(
        self,
        symbol: str,
        min_size: float = 0.01,
        max_size: float = 1000.0,
        size_step: float = 0.01,
        min_stop_distance: float = 0.0,
        max_stop_distance: float = 0.0,
    ) -> None:
        """Set dealing rules for a symbol."""
        self.dealing_rules[symbol] = DealingRules(
            min_size=min_size,
            max_size=max_size,
            size_step=size_step,
            min_stop_distance=min_stop_distance,
            max_stop_distance=max_stop_distance,
        )

    def get_warnings(self) -> list[str]:
        """Get accumulated warnings."""
        return self._warnings.copy()

    def clear_warnings(self) -> None:
        """Clear accumulated warnings."""
        self._warnings.clear()

    def reset(self) -> None:
        """Reset broker state."""
        self.order_history.clear()
        self._warnings.clear()

    def get_fill_summary(self) -> dict[str, Any]:
        """Get summary of fills and rejections."""
        filled = [o for o in self.order_history if o.status == OrderStatus.FILLED]
        rejected = [o for o in self.order_history if o.status == OrderStatus.REJECTED]

        total_spread = sum(o.spread_applied * o.size for o in filled)
        total_slippage = sum(o.slippage_applied * o.size for o in filled)
        total_fees = sum(o.fees_applied for o in filled)

        return {
            "total_orders": len(self.order_history),
            "filled_orders": len(filled),
            "rejected_orders": len(rejected),
            "total_spread_cost": total_spread,
            "total_slippage_cost": total_slippage,
            "total_fees": total_fees,
            "total_transaction_costs": total_spread + total_slippage + total_fees,
        }
