"""
BacktestEngine interface.

Defines the contract for backtesting framework implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from solat_engine.domain import Bar, Fill, Order, Position, Signal, Timeframe
from solat_engine.interfaces.strategy import Strategy


@dataclass
class BacktestResult:
    """
    Results from a backtest run.

    Contains all metrics, trades, and equity curve data.
    """

    # Run identification
    run_id: str
    strategy_id: str
    symbol: str
    timeframe: Timeframe
    start_date: datetime
    end_date: datetime

    # Capital
    initial_capital: Decimal
    final_capital: Decimal

    # Performance metrics
    total_return: Decimal = Decimal("0")
    total_return_pct: Decimal = Decimal("0")
    annualized_return: Decimal = Decimal("0")
    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None

    # Drawdown metrics
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    max_drawdown_duration_days: int = 0
    average_drawdown: Decimal = Decimal("0")

    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0")
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")
    profit_factor: Decimal | None = None
    expectancy: Decimal = Decimal("0")

    # Risk metrics
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    average_trade_duration_bars: Decimal = Decimal("0")
    mae_average: Decimal = Decimal("0")  # Maximum Adverse Excursion
    mfe_average: Decimal = Decimal("0")  # Maximum Favorable Excursion

    # Cost metrics
    total_commission: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    total_spread_cost: Decimal = Decimal("0")

    # Data
    signals: list[Signal] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    drawdown_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)

    # Execution info
    bars_processed: int = 0
    execution_time_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BacktestEngine(ABC):
    """
    Abstract base class for backtesting engines.

    Implementations handle:
    - Event-driven or bar-driven simulation
    - Realistic fill modeling
    - Slippage and commission modeling
    - Order lifecycle matching broker semantics
    - Deterministic execution (no lookahead)
    """

    # =========================================================================
    # Configuration
    # =========================================================================

    @abstractmethod
    def configure(
        self,
        initial_capital: Decimal,
        commission_per_trade: Decimal = Decimal("0"),
        slippage_pct: Decimal = Decimal("0"),
        spread_pct: Decimal = Decimal("0"),
    ) -> None:
        """
        Configure backtest parameters.

        Args:
            initial_capital: Starting capital
            commission_per_trade: Fixed commission per trade
            slippage_pct: Slippage as percentage of price
            spread_pct: Spread as percentage of price
        """
        pass

    # =========================================================================
    # Execution
    # =========================================================================

    @abstractmethod
    async def run(
        self,
        strategy: Strategy,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        run_id: str | None = None,
    ) -> BacktestResult:
        """
        Run a backtest.

        Args:
            strategy: Strategy to test
            symbol: Instrument symbol
            timeframe: Primary timeframe
            start: Start date
            end: End date
            run_id: Optional run ID (generated if not provided)

        Returns:
            BacktestResult with all metrics and data.
        """
        pass

    @abstractmethod
    async def run_multi_symbol(
        self,
        strategy: Strategy,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        run_id: str | None = None,
    ) -> dict[str, BacktestResult]:
        """
        Run backtest across multiple symbols.

        Args:
            strategy: Strategy to test
            symbols: List of symbols
            timeframe: Primary timeframe
            start: Start date
            end: End date
            run_id: Optional run ID prefix

        Returns:
            Dict mapping symbol to BacktestResult.
        """
        pass

    # =========================================================================
    # Fill Simulation
    # =========================================================================

    @abstractmethod
    def simulate_fill(
        self,
        order: Order,
        bar: Bar,
    ) -> Fill | None:
        """
        Simulate order fill against a bar.

        Args:
            order: Order to fill
            bar: Current bar

        Returns:
            Fill if order would be executed, None otherwise.
        """
        pass

    # =========================================================================
    # State Access (for debugging/analysis)
    # =========================================================================

    @abstractmethod
    def get_current_positions(self) -> list[Position]:
        """Get current open positions in the simulation."""
        pass

    @abstractmethod
    def get_pending_orders(self) -> list[Order]:
        """Get pending orders in the simulation."""
        pass

    @abstractmethod
    def get_equity(self) -> Decimal:
        """Get current equity value."""
        pass

    # =========================================================================
    # Artefact Export
    # =========================================================================

    @abstractmethod
    async def export_results(
        self,
        result: BacktestResult,
        output_dir: str,
    ) -> dict[str, str]:
        """
        Export backtest results to files.

        Args:
            result: Backtest result to export
            output_dir: Output directory path

        Returns:
            Dict mapping artefact type to file path.
        """
        pass
