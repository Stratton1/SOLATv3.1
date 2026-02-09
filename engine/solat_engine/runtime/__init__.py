"""
Runtime utilities for SOLAT trading engine.

Provides:
- Event bus for internal pub/sub
- Run ID management for tracking backtest/live runs
- Artefact directory conventions
- Bounded caches with memory limits
- WebSocket event throttling
"""

from solat_engine.runtime.artefacts import ArtefactManager
from solat_engine.runtime.cache import (
    BoundedLRUCache,
    CacheStats,
    MemoryBoundedBuffer,
    WindowedCounter,
    get_cache_config,
)
from solat_engine.runtime.event_bus import Event, EventBus, EventType
from solat_engine.runtime.run_context import RunContext, generate_run_id
from solat_engine.runtime.ws_throttle import (
    ExecutionEventCompressor,
    WSEventThrottler,
    get_ws_throttler,
)

__all__ = [
    # Artefacts
    "ArtefactManager",
    # Event bus
    "Event",
    "EventBus",
    "EventType",
    # Run context
    "RunContext",
    "generate_run_id",
    # Cache utilities
    "BoundedLRUCache",
    "CacheStats",
    "MemoryBoundedBuffer",
    "WindowedCounter",
    "get_cache_config",
    # WS throttling
    "ExecutionEventCompressor",
    "WSEventThrottler",
    "get_ws_throttler",
]
