"""
SOLAT v3.1 Trading Engine

A production-grade algorithmic trading engine supporting:
- IG broker connectivity (demo/live)
- Multi-strategy backtesting with deterministic execution
- Real-time trading with risk management
- Desktop terminal integration via FastAPI + WebSocket
"""

__version__ = "3.1.0"
__author__ = "SOLAT Development Team"

from solat_engine.config import Settings, get_settings

__all__ = ["__version__", "Settings", "get_settings"]
