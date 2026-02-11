"""
Data models for the optimization module.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WindowType(str, Enum):
    """Walk-forward window type."""

    ROLLING = "rolling"  # Fixed-size rolling window
    ANCHORED = "anchored"  # Expanding window from anchor date


class OptimizationMode(str, Enum):
    """How to select top performers."""

    SHARPE = "sharpe"  # Highest Sharpe ratio
    SORTINO = "sortino"  # Highest Sortino ratio
    CALMAR = "calmar"  # Highest Calmar ratio (return/max DD)
    WIN_RATE = "win_rate"  # Highest win rate
    PROFIT_FACTOR = "profit_factor"  # Highest profit factor
    COMPOSITE = "composite"  # Weighted composite score


# =============================================================================
# Walk-Forward Models
# =============================================================================


class WalkForwardConfig(BaseModel):
    """Configuration for walk-forward optimization."""

    # Symbols and strategies to test
    symbols: list[str] = Field(..., min_length=1)
    bots: list[str] = Field(..., min_length=1)
    timeframes: list[str] = Field(default=["1h"])

    # Date range
    start_date: datetime = Field(..., description="Overall start date")
    end_date: datetime = Field(..., description="Overall end date")

    # Window configuration
    window_type: WindowType = Field(default=WindowType.ROLLING)
    in_sample_days: int = Field(default=180, ge=30, description="In-sample training period")
    out_of_sample_days: int = Field(default=45, ge=7, description="Out-of-sample testing period")
    step_days: int = Field(default=45, ge=1, description="Days to step forward each iteration")

    # Selection
    optimization_mode: OptimizationMode = Field(default=OptimizationMode.SHARPE)
    top_n: int = Field(default=10, ge=1, le=50, description="Number of top combos to select")
    min_trades: int = Field(default=10, ge=1, description="Minimum trades to qualify")

    # Risk filters
    max_drawdown_pct: float = Field(default=20.0, ge=1.0, le=100.0)
    min_sharpe: float = Field(default=0.0, description="Minimum Sharpe to qualify")


class WalkForwardWindow(BaseModel):
    """Results for a single walk-forward window."""

    window_id: int

    # Period dates
    in_sample_start: datetime
    in_sample_end: datetime
    out_of_sample_start: datetime
    out_of_sample_end: datetime

    # In-sample best combos (training)
    in_sample_top: list[dict[str, Any]] = Field(default_factory=list)

    # Out-of-sample performance (validation)
    out_of_sample_results: list[dict[str, Any]] = Field(default_factory=list)

    # Aggregate metrics
    oos_sharpe: float | None = None
    oos_return_pct: float | None = None
    oos_win_rate: float | None = None
    oos_trades: int = 0


class WalkForwardResult(BaseModel):
    """Complete walk-forward optimization result."""

    run_id: str
    config: WalkForwardConfig

    # Overall status
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0  # 0-100
    message: str = ""

    # Window results
    windows: list[WalkForwardWindow] = Field(default_factory=list)
    total_windows: int = 0
    completed_windows: int = 0

    # Aggregate metrics across all OOS periods
    aggregate_sharpe: float | None = None
    aggregate_return_pct: float | None = None
    aggregate_win_rate: float | None = None
    aggregate_trades: int = 0

    # Final recommended allowlist
    recommended_combos: list[dict[str, Any]] = Field(default_factory=list)

    # Timestamps
    started_at: datetime | None = None
    completed_at: datetime | None = None


# =============================================================================
# Allowlist Models
# =============================================================================


class AllowlistEntry(BaseModel):
    """A single entry in the trading allowlist."""

    symbol: str
    bot: str
    timeframe: str

    # Performance metrics from walk-forward
    sharpe: float | None = None
    sortino: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    total_trades: int = 0

    # Source info
    source_run_id: str | None = None
    validated_at: datetime | None = None

    # Execution state
    enabled: bool = True
    reason: str | None = None

    @property
    def combo_id(self) -> str:
        """Unique identifier for this combo."""
        return f"{self.symbol}:{self.bot}:{self.timeframe}"


class AllowlistConfig(BaseModel):
    """Configuration for the allowlist manager."""

    # Auto-update settings
    auto_update_enabled: bool = Field(default=True)
    update_frequency_hours: int = Field(default=24, ge=1)

    # Selection criteria
    max_combos: int = Field(default=20, ge=1, le=100)
    min_sharpe: float = Field(default=0.5)
    min_trades: int = Field(default=20)
    max_drawdown_pct: float = Field(default=15.0)

    # Diversification
    max_per_symbol: int = Field(default=3, ge=1)
    max_per_bot: int = Field(default=5, ge=1)

    # Staleness
    max_validation_age_days: int = Field(default=7)


# =============================================================================
# Performance Tracking Models
# =============================================================================


class PerformanceSnapshot(BaseModel):
    """Snapshot of live vs backtest performance for a combo."""

    symbol: str
    bot: str
    timeframe: str

    # Backtest baseline (expected)
    bt_sharpe: float | None = None
    bt_win_rate: float | None = None
    bt_avg_trade_pnl: float | None = None
    bt_trades_per_day: float | None = None

    # Live performance (actual)
    live_sharpe: float | None = None
    live_win_rate: float | None = None
    live_avg_trade_pnl: float | None = None
    live_trades: int = 0
    live_pnl: float = 0.0

    # Drift metrics
    sharpe_drift: float | None = None  # live - backtest
    win_rate_drift: float | None = None

    # Period
    period_start: datetime | None = None
    period_end: datetime | None = None
    snapshot_at: datetime | None = None


@dataclass
class ComboPerformance:
    """Performance stats for a bot/symbol/timeframe combo."""

    symbol: str
    bot: str
    timeframe: str

    # Core metrics
    sharpe: float = 0.0
    sortino: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0

    # Composite score (weighted combination)
    composite_score: float = 0.0

    # Metadata
    window_id: int | None = None
    is_in_sample: bool = True

    @property
    def combo_id(self) -> str:
        return f"{self.symbol}:{self.bot}:{self.timeframe}"

    def calculate_composite(
        self,
        sharpe_weight: float = 0.4,
        sortino_weight: float = 0.2,
        win_rate_weight: float = 0.2,
        profit_factor_weight: float = 0.2,
    ) -> float:
        """Calculate weighted composite score."""
        # Normalize each metric to 0-1 range (approximate)
        norm_sharpe = min(max(self.sharpe / 3.0, 0), 1)  # Sharpe 0-3 -> 0-1
        norm_sortino = min(max(self.sortino / 4.0, 0), 1)  # Sortino 0-4 -> 0-1
        norm_winrate = self.win_rate  # Already 0-1
        norm_pf = min(max((self.profit_factor - 1) / 2, 0), 1)  # PF 1-3 -> 0-1

        self.composite_score = (
            sharpe_weight * norm_sharpe +
            sortino_weight * norm_sortino +
            win_rate_weight * norm_winrate +
            profit_factor_weight * norm_pf
        )
        return self.composite_score
