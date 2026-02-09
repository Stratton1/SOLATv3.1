"""
Interfaces (abstract base classes) for SOLAT trading engine.

These define the contracts that must be implemented by:
- BrokerAdapter: Broker connectivity (IG, etc.)
- DataProvider: Market data access
- Strategy: Trading strategy logic
- BacktestEngine: Backtesting framework
"""

from solat_engine.interfaces.backtest_engine import BacktestEngine, BacktestResult
from solat_engine.interfaces.broker_adapter import BrokerAdapter
from solat_engine.interfaces.data_provider import DataProvider
from solat_engine.interfaces.strategy import Strategy

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BrokerAdapter",
    "DataProvider",
    "Strategy",
]
