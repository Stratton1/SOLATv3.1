"""
Optimization module for SOLATv3.1.

Provides:
- Walk-forward backtesting
- Dynamic allowlist management
- Performance tracking
- Scheduled optimization jobs
"""

from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.optimization.models import (
    AllowlistConfig,
    AllowlistEntry,
    PerformanceSnapshot,
    WalkForwardConfig,
    WalkForwardResult,
    WalkForwardWindow,
)
from solat_engine.optimization.walk_forward import WalkForwardEngine

__all__ = [
    "WalkForwardConfig",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WalkForwardEngine",
    "AllowlistEntry",
    "AllowlistConfig",
    "AllowlistManager",
    "PerformanceSnapshot",
]
