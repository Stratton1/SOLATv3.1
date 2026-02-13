"""
Strategy interface.

Defines the contract for trading strategies (the "Elite 8" and beyond).
"""

from abc import ABC, abstractmethod
from typing import Any

from solat_engine.domain import Bar, Position, Signal, Timeframe


class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    Strategies are stateless and deterministic - they receive data
    and produce signals without side effects. This ensures reproducible
    backtests and live/backtest parity.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """
        Unique identifier for this strategy.

        Used for signal attribution, logging, and configuration.
        Example: "elite8_momentum", "elite8_mean_reversion"
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of the strategy logic."""
        pass

    @property
    @abstractmethod
    def timeframes(self) -> list[Timeframe]:
        """
        Timeframes this strategy operates on.

        The first timeframe is the primary trading timeframe.
        Additional timeframes are for higher-timeframe context.
        """
        pass

    @property
    @abstractmethod
    def symbols(self) -> list[str]:
        """
        Symbols this strategy is designed to trade.

        Can be a specific list or ['*'] for any symbol.
        """
        pass

    @property
    def warmup_bars(self) -> int:
        """
        Number of bars needed for indicator warmup.

        Override this based on the longest indicator lookback.
        """
        return 100

    @property
    def parameters(self) -> dict[str, Any]:
        """
        Strategy parameters (for optimization).

        Returns a dict of parameter names to current values.
        Override to expose tunable parameters.
        """
        return {}

    # =========================================================================
    # Core Signal Generation
    # =========================================================================

    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        bars: dict[Timeframe, list[Bar]],
        current_position: Position | None = None,
    ) -> Signal | None:
        """
        Generate a trading signal based on current market data.

        This is the core strategy logic. MUST be:
        - Deterministic: Same inputs always produce same output
        - Pure: No side effects, no external state
        - No lookahead: Only uses data up to current bar

        Args:
            symbol: Instrument symbol being evaluated
            bars: Dict mapping timeframes to bar lists (oldest first)
            current_position: Current position in this symbol (if any)

        Returns:
            Signal if conditions met, None otherwise.
        """
        pass

    # =========================================================================
    # Risk Management Hints
    # =========================================================================

    def calculate_position_size(
        self,
        signal: Signal,
        account_balance: float,
        risk_per_trade: float = 0.01,
    ) -> float:
        """
        Calculate suggested position size based on risk parameters.

        Default implementation uses fixed fractional sizing.
        Override for strategy-specific sizing logic.

        Args:
            signal: The signal being sized
            account_balance: Current account balance
            risk_per_trade: Fraction of account to risk per trade

        Returns:
            Suggested position size.
        """
        if signal.stop_loss is None:
            # No stop loss defined, use conservative sizing
            return account_balance * risk_per_trade * 0.1

        # Calculate based on stop distance
        entry = float(signal.entry_price or 0)
        stop = float(signal.stop_loss)
        if entry == 0 or stop == 0:
            return account_balance * risk_per_trade * 0.1

        risk_amount = account_balance * risk_per_trade
        stop_distance = abs(entry - stop)
        if stop_distance == 0:
            return 0

        return risk_amount / stop_distance

    # =========================================================================
    # Lifecycle Hooks
    # =========================================================================

    def on_start(self) -> None:
        """
        Called when strategy is started.

        Override to perform initialization that doesn't affect signal logic.
        """
        pass

    def on_stop(self) -> None:
        """
        Called when strategy is stopped.

        Override to perform cleanup.
        """
        pass

    def on_bar(self, symbol: str, bar: Bar) -> None:
        """
        Called on each new bar (for logging/metrics only).

        IMPORTANT: Do NOT put signal logic here - use generate_signal.
        """
        pass

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_bars(
        self,
        bars: dict[Timeframe, list[Bar]],
    ) -> bool:
        """
        Validate that sufficient bars are available.

        Args:
            bars: Dict mapping timeframes to bar lists

        Returns:
            True if enough data for signal generation.
        """
        for tf in self.timeframes:
            if tf not in bars or len(bars[tf]) < self.warmup_bars:
                return False
        return True
