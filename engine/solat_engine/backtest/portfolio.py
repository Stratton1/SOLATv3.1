"""
Portfolio management for backtesting.

Tracks positions, cash, equity, and PnL with proper accounting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from solat_engine.backtest.models import (
    EquityPoint,
    PositionSide,
    TradeRecord,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OpenPosition:
    """An open position in the portfolio."""

    position_id: UUID
    symbol: str
    bot: str
    side: PositionSide
    size: float
    entry_price: float
    entry_time: datetime
    stop_loss: float | None = None
    take_profit: float | None = None
    unrealized_pnl: float = 0.0
    mae: float = 0.0  # Maximum Adverse Excursion
    mfe: float = 0.0  # Maximum Favorable Excursion
    bars_held: int = 0

    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        return self.side == PositionSide.SHORT

    def update_unrealized_pnl(self, current_price: float) -> float:
        """Update unrealized PnL and track MAE/MFE."""
        if self.is_long:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size

        # Track MAE (worst drawdown during trade)
        if self.unrealized_pnl < self.mae:
            self.mae = self.unrealized_pnl

        # Track MFE (best profit during trade)
        if self.unrealized_pnl > self.mfe:
            self.mfe = self.unrealized_pnl

        return self.unrealized_pnl

    def should_stop_loss(self, current_price: float) -> bool:
        """Check if stop loss should trigger."""
        if self.stop_loss is None:
            return False
        if self.is_long:
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        """Check if take profit should trigger."""
        if self.take_profit is None:
            return False
        if self.is_long:
            return current_price >= self.take_profit
        else:
            return current_price <= self.take_profit


@dataclass
class Portfolio:
    """
    Portfolio state manager.

    Tracks cash, positions, equity, and generates equity curve points.
    Invariants:
    - equity = cash + sum(unrealized_pnl)
    - closing position realizes PnL correctly
    """

    initial_cash: float
    cash: float = field(init=False)
    positions: dict[str, OpenPosition] = field(default_factory=dict)
    closed_trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    realized_pnl: float = 0.0
    high_water_mark: float = field(init=False)
    _current_prices: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash
        self.high_water_mark = self.initial_cash

    @property
    def unrealized_pnl(self) -> float:
        """Total unrealized PnL across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def equity(self) -> float:
        """Current equity = cash + unrealized PnL."""
        return self.cash + self.unrealized_pnl

    @property
    def total_pnl(self) -> float:
        """Total PnL = realized + unrealized."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def drawdown(self) -> float:
        """Current drawdown from high water mark (absolute)."""
        return max(0.0, self.high_water_mark - self.equity)

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown as percentage."""
        if self.high_water_mark <= 0:
            return 0.0
        return self.drawdown / self.high_water_mark

    @property
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self.positions)

    @property
    def total_exposure(self) -> float:
        """Total notional exposure across all positions."""
        return sum(
            pos.size * self._current_prices.get(pos.symbol, pos.entry_price)
            for pos in self.positions.values()
        )

    def get_position(self, symbol: str, bot: str | None = None) -> OpenPosition | None:
        """Get open position for symbol (optionally filtered by bot)."""
        key = f"{symbol}:{bot}" if bot else symbol
        # Try exact key first
        if key in self.positions:
            return self.positions[key]
        # For backwards compat, try symbol-only
        for _pos_key, pos in self.positions.items():
            if pos.symbol == symbol and (bot is None or pos.bot == bot):
                return pos
        return None

    def has_position(self, symbol: str, bot: str | None = None) -> bool:
        """Check if position exists."""
        return self.get_position(symbol, bot) is not None

    def get_symbol_exposure(self, symbol: str) -> float:
        """Get total exposure for a symbol."""
        return sum(
            pos.size * self._current_prices.get(pos.symbol, pos.entry_price)
            for pos in self.positions.values()
            if pos.symbol == symbol
        )

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices and recalculate unrealized PnL."""
        self._current_prices.update(prices)
        for pos in self.positions.values():
            if pos.symbol in prices:
                pos.update_unrealized_pnl(prices[pos.symbol])
        # Update high water mark
        if self.equity > self.high_water_mark:
            self.high_water_mark = self.equity

    def open_position(
        self,
        symbol: str,
        bot: str,
        side: PositionSide,
        size: float,
        entry_price: float,
        entry_time: datetime,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OpenPosition:
        """Open a new position."""
        position_id = uuid4()
        key = f"{symbol}:{bot}"

        position = OpenPosition(
            position_id=position_id,
            symbol=symbol,
            bot=bot,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_time=entry_time,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        # Initialize unrealized PnL
        current_price = self._current_prices.get(symbol, entry_price)
        position.update_unrealized_pnl(current_price)

        self.positions[key] = position

        logger.debug(
            "Opened %s position for %s (%s): %.4f @ %.5f",
            side.value,
            symbol,
            bot,
            size,
            entry_price,
        )

        return position

    def close_position(
        self,
        symbol: str,
        bot: str,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str = "signal",
        fees: float = 0.0,
    ) -> TradeRecord | None:
        """Close a position and return trade record."""
        key = f"{symbol}:{bot}"
        position = self.positions.get(key)

        if position is None:
            # Try symbol-only lookup
            for pos_key, pos in list(self.positions.items()):
                if pos.symbol == symbol and pos.bot == bot:
                    position = pos
                    key = pos_key
                    break

        if position is None:
            logger.warning("No position to close for %s (%s)", symbol, bot)
            return None

        # Calculate realized PnL
        if position.is_long:
            pnl = (exit_price - position.entry_price) * position.size - fees
        else:
            pnl = (position.entry_price - exit_price) * position.size - fees

        pnl_pct = pnl / (position.entry_price * position.size) if position.size > 0 else 0.0

        # Create trade record
        trade = TradeRecord(
            symbol=symbol,
            bot=bot,
            side=position.side,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            mae=position.mae,
            mfe=position.mfe,
            bars_held=position.bars_held,
            exit_reason=exit_reason,
        )

        # Update portfolio state
        self.cash += pnl
        self.realized_pnl += pnl
        self.closed_trades.append(trade)

        # Remove position
        del self.positions[key]

        logger.debug(
            "Closed %s position for %s (%s): PnL=%.2f (%.2f%%)",
            position.side.value,
            symbol,
            bot,
            pnl,
            pnl_pct * 100,
        )

        return trade

    def record_equity_point(self, timestamp: datetime) -> EquityPoint:
        """Record current equity state."""
        point = EquityPoint(
            timestamp=timestamp,
            equity=self.equity,
            cash=self.cash,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            drawdown=self.drawdown,
            drawdown_pct=self.drawdown_pct,
            high_water_mark=self.high_water_mark,
        )
        self.equity_curve.append(point)
        return point

    def increment_bars_held(self) -> None:
        """Increment bars held for all open positions."""
        for pos in self.positions.values():
            pos.bars_held += 1

    def check_exits(
        self,
        timestamp: datetime,
        prices: dict[str, float],
        fees_per_trade: float = 0.0,
    ) -> list[TradeRecord]:
        """Check and execute SL/TP exits for all positions."""
        trades: list[TradeRecord] = []

        for _key, position in list(self.positions.items()):
            symbol = position.symbol
            current_price = prices.get(symbol)
            if current_price is None:
                continue

            exit_reason: str | None = None
            exit_price = current_price

            if position.should_stop_loss(current_price):
                exit_reason = "stop_loss"
                exit_price = position.stop_loss or current_price
            elif position.should_take_profit(current_price):
                exit_reason = "take_profit"
                exit_price = position.take_profit or current_price

            if exit_reason:
                trade = self.close_position(
                    symbol=symbol,
                    bot=position.bot,
                    exit_price=exit_price,
                    exit_time=timestamp,
                    exit_reason=exit_reason,
                    fees=fees_per_trade,
                )
                if trade:
                    trades.append(trade)

        return trades

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.cash = self.initial_cash
        self.positions.clear()
        self.closed_trades.clear()
        self.equity_curve.clear()
        self.realized_pnl = 0.0
        self.high_water_mark = self.initial_cash
        self._current_prices.clear()

    def to_summary(self) -> dict[str, Any]:
        """Get portfolio summary."""
        return {
            "cash": self.cash,
            "equity": self.equity,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "total_pnl": self.total_pnl,
            "drawdown": self.drawdown,
            "drawdown_pct": self.drawdown_pct,
            "position_count": self.position_count,
            "total_exposure": self.total_exposure,
            "high_water_mark": self.high_water_mark,
            "trade_count": len(self.closed_trades),
        }
