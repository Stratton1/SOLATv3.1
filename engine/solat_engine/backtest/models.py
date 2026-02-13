"""
Backtest data models.

Defines contracts for backtest requests, results, trades, and metrics.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, Field


class SizingMethod(str, Enum):
    """Position sizing methods."""

    FIXED_SIZE = "fixed_size"
    RISK_PER_TRADE = "risk_per_trade"


class OrderAction(str, Enum):
    """Order action types."""

    BUY = "BUY"
    SELL = "SELL"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


class OrderStatus(str, Enum):
    """Order status in simulation."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PositionSide(str, Enum):
    """Position side."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# =============================================================================
# Request Models
# =============================================================================


class SpreadConfig(BaseModel):
    """Spread configuration per instrument or global."""

    default_points: float = Field(default=1.0, description="Default spread in points")
    per_instrument: dict[str, float] = Field(
        default_factory=dict, description="Spread per instrument symbol"
    )


class SlippageConfig(BaseModel):
    """Slippage configuration."""

    default_points: float = Field(default=0.0, description="Default slippage in points")
    per_instrument: dict[str, float] = Field(
        default_factory=dict, description="Slippage per instrument symbol"
    )


class FeeConfig(BaseModel):
    """Fee/commission configuration."""

    per_trade_flat: float = Field(default=0.0, description="Flat fee per trade")
    per_lot: float = Field(default=0.0, description="Fee per lot traded")
    percentage: float = Field(default=0.0, description="Fee as percentage of notional")


class RiskConfig(BaseModel):
    """Risk management configuration."""

    sizing_method: SizingMethod = Field(default=SizingMethod.FIXED_SIZE)
    fixed_size: float = Field(default=1.0, description="Fixed lot size when using FIXED_SIZE")
    risk_per_trade_pct: float = Field(
        default=0.5, ge=0.01, le=10.0, description="Risk per trade as % of equity"
    )
    max_open_positions: int = Field(default=3, ge=1, le=100)
    max_exposure_per_symbol: float = Field(
        default=100000.0, description="Max notional per symbol"
    )
    max_total_exposure: float = Field(
        default=500000.0, description="Max total notional exposure"
    )


class BacktestRequest(BaseModel):
    """Request to run a backtest."""

    symbols: list[str] = Field(..., min_length=1, description="Symbols to backtest")
    timeframe: str = Field(default="1m", description="Primary timeframe")
    start: datetime = Field(
        ...,
        description="Backtest start time (UTC)",
        validation_alias=AliasChoices("start", "start_date"),
    )
    end: datetime = Field(
        ...,
        description="Backtest end time (UTC)",
        validation_alias=AliasChoices("end", "end_date"),
    )
    bots: list[str] = Field(..., min_length=1, description="Bot names to run")
    initial_cash: float = Field(
        default=100000.0,
        ge=100.0,
        description="Starting capital",
        validation_alias=AliasChoices("initial_cash", "initial_capital"),
    )
    spread: SpreadConfig = Field(default_factory=SpreadConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    fees: FeeConfig = Field(default_factory=FeeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    warmup_bars: int = Field(default=100, ge=10, le=1000, description="Warmup period")


# =============================================================================
# Result Models
# =============================================================================


class EquityPoint(BaseModel):
    """Single point on the equity curve."""

    timestamp: datetime
    equity: float
    cash: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown: float = Field(description="Drawdown from peak as decimal (0.1 = 10%)")
    drawdown_pct: float = Field(description="Drawdown percentage")
    high_water_mark: float


class TradeRecord(BaseModel):
    """Record of a completed trade (entry + exit)."""

    trade_id: UUID = Field(default_factory=uuid4)
    symbol: str
    bot: str
    side: PositionSide
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    mae: float = Field(default=0.0, description="Maximum Adverse Excursion")
    mfe: float = Field(default=0.0, description="Maximum Favorable Excursion")
    bars_held: int = 0
    exit_reason: str = Field(default="unknown", description="SL/TP/signal/timeout")


class OrderRecord(BaseModel):
    """Record of an order in the backtest."""

    order_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    symbol: str
    bot: str
    action: OrderAction
    size: float
    price_requested: float | None = None
    price_filled: float | None = None
    status: OrderStatus
    spread_applied: float = 0.0
    slippage_applied: float = 0.0
    fees_applied: float = 0.0
    rejection_reason: str | None = None


class MetricsSummary(BaseModel):
    """Performance metrics summary."""

    # Identification
    bot: str | None = None
    symbol: str | None = None

    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0
    cagr: float = 0.0

    # Risk
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    volatility: float = 0.0

    # Trading
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade_pnl: float = 0.0  # Average PnL per trade (total_pnl / total_trades)
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_bars_held: float = 0.0

    # Exposure
    avg_exposure: float = 0.0
    max_exposure: float = 0.0
    time_in_market_pct: float = 0.0


class BotResult(BaseModel):
    """Results for a single bot in the backtest."""

    bot: str
    symbols_traded: list[str]
    metrics: MetricsSummary
    trades_count: int
    orders_count: int
    warnings: list[str] = Field(default_factory=list)


class BacktestResult(BaseModel):
    """Complete backtest result."""

    run_id: str
    ok: bool = True
    started_at: datetime
    completed_at: datetime | None = None
    request: BacktestRequest
    per_bot_results: list[BotResult] = Field(default_factory=list)
    combined_metrics: MetricsSummary | None = None
    artefact_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    engine_version: str = "1.0.0"


# =============================================================================
# Sweep Models
# =============================================================================


class SweepRequest(BaseModel):
    """Request for Grand Sweep batch backtest."""

    bots: list[str] = Field(..., min_length=1)
    symbols: list[str] = Field(..., min_length=1)
    timeframes: list[str] = Field(default=["1m"])
    start: datetime
    end: datetime
    initial_cash: float = Field(default=100000.0)
    spread: SpreadConfig = Field(default_factory=SpreadConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    fees: FeeConfig = Field(default_factory=FeeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    force: bool = Field(default=False, description="Re-run even if results exist")
    max_concurrent: int = Field(default=1, ge=1, le=10)


class SweepComboResult(BaseModel):
    """Result for a single combo in the sweep."""

    bot: str
    symbol: str
    timeframe: str
    sharpe: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    pnl: float
    params_hash: str = ""


class SweepResult(BaseModel):
    """Grand Sweep batch result."""

    sweep_id: str
    ok: bool = True
    started_at: datetime
    completed_at: datetime | None = None
    total_combos: int
    completed_combos: int
    failed_combos: int
    results: list[SweepComboResult] = Field(default_factory=list)
    top_performers: list[SweepComboResult] = Field(default_factory=list)
    artefact_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# Internal Models
# =============================================================================


class SignalIntent(BaseModel):
    """Strategy output signal intent."""

    direction: str = Field(description="BUY/SELL/HOLD")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    stop_loss: float | None = None
    take_profit: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        return self.direction in ("BUY", "SELL")

    @property
    def is_buy(self) -> bool:
        return self.direction == "BUY"

    @property
    def is_sell(self) -> bool:
        return self.direction == "SELL"

    @property
    def is_hold(self) -> bool:
        return self.direction == "HOLD"
