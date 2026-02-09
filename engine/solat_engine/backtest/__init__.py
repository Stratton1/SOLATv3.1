"""
Backtest engine module for SOLAT v3.1.

Provides deterministic, bar-driven backtesting with:
- BrokerSim for order execution simulation
- Portfolio for position/PnL tracking
- Metrics calculation (Sharpe, drawdown, etc.)
- Grand Sweep batch runner
"""

from solat_engine.backtest.models import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    MetricsSummary,
    OrderRecord,
    TradeRecord,
)

__all__ = [
    "BacktestRequest",
    "BacktestResult",
    "EquityPoint",
    "MetricsSummary",
    "OrderRecord",
    "TradeRecord",
]
