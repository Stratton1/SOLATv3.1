"""
Bounded cache implementations with memory limits.

Provides LRU and time-based caches that won't grow unbounded.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from solat_engine.logging import get_logger

logger = get_logger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    current_size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate as percentage."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100


class BoundedLRUCache(Generic[K, V]):
    """
    Bounded LRU (Least Recently Used) cache.

    Features:
    - Fixed maximum size
    - LRU eviction when at capacity
    - Optional TTL per entry
    - Statistics tracking
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float | None = None,
        name: str = "cache",
    ):
        """
        Initialize bounded cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Optional TTL for entries (None = no expiry)
            name: Name for logging purposes
        """
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._name = name

        # OrderedDict for LRU ordering
        self._cache: OrderedDict[K, tuple[V, datetime]] = OrderedDict()
        self._stats = CacheStats(max_size=max_size)

    def get(self, key: K) -> V | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Value if found and not expired, None otherwise
        """
        entry = self._cache.get(key)
        if entry is None:
            self._stats.misses += 1
            return None

        value, created_at = entry

        # Check TTL
        if self._ttl_seconds is not None:
            age = (datetime.now(UTC) - created_at).total_seconds()
            if age > self._ttl_seconds:
                # Expired - remove and return None
                self._cache.pop(key, None)
                self._stats.misses += 1
                self._stats.current_size = len(self._cache)
                return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._stats.hits += 1
        return value

    def set(self, key: K, value: V) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        now = datetime.now(UTC)

        # Check if key exists
        if key in self._cache:
            # Update existing entry
            self._cache[key] = (value, now)
            self._cache.move_to_end(key)
        else:
            # New entry - check capacity
            while len(self._cache) >= self._max_size:
                # Evict oldest (first item)
                evicted_key = next(iter(self._cache))
                self._cache.pop(evicted_key)
                self._stats.evictions += 1

            self._cache[key] = (value, now)

        self._stats.current_size = len(self._cache)

    def delete(self, key: K) -> bool:
        """
        Delete entry from cache.

        Args:
            key: Cache key

        Returns:
            True if entry was deleted
        """
        if key in self._cache:
            self._cache.pop(key)
            self._stats.current_size = len(self._cache)
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()
        self._stats.current_size = 0

    def contains(self, key: K) -> bool:
        """Check if key exists (doesn't update LRU order)."""
        return key in self._cache

    def keys(self) -> list[K]:
        """Get all keys (most recent last)."""
        return list(self._cache.keys())

    def values(self) -> list[V]:
        """Get all values (most recent last)."""
        return [v for v, _ in self._cache.values()]

    def items(self) -> list[tuple[K, V]]:
        """Get all key-value pairs (most recent last)."""
        return [(k, v) for k, (v, _) in self._cache.items()]

    def __len__(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def __contains__(self, key: K) -> bool:
        """Check if key exists."""
        return self.contains(key)

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def cleanup_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        if self._ttl_seconds is None:
            return 0

        now = datetime.now(UTC)
        expired = []

        for key, (_, created_at) in self._cache.items():
            age = (now - created_at).total_seconds()
            if age > self._ttl_seconds:
                expired.append(key)

        for key in expired:
            self._cache.pop(key)

        self._stats.current_size = len(self._cache)
        return len(expired)


@dataclass
class WindowedCounter:
    """
    Counts events within a sliding time window.

    Useful for rate limiting and failure tracking.
    """

    window_seconds: float
    max_events: int = 10000  # Bounded to prevent memory growth

    _events: list[datetime] = field(default_factory=list)

    def record(self, ts: datetime | None = None) -> None:
        """Record an event."""
        ts = ts or datetime.now(UTC)
        self._events.append(ts)

        # Enforce max events
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]

    def count(self) -> int:
        """Get count of events in window."""
        self._cleanup()
        return len(self._events)

    def _cleanup(self) -> None:
        """Remove expired events."""
        now = datetime.now(UTC)
        cutoff = now.timestamp() - self.window_seconds
        self._events = [ts for ts in self._events if ts.timestamp() > cutoff]

    def reset(self) -> None:
        """Reset counter."""
        self._events.clear()


class MemoryBoundedBuffer(Generic[V]):
    """
    Buffer with memory-based size limit.

    Estimates memory usage and evicts when limit is reached.
    """

    def __init__(
        self,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB default
        entry_size_estimate: int = 1000,  # Estimated bytes per entry
    ):
        """
        Initialize bounded buffer.

        Args:
            max_bytes: Maximum memory in bytes
            entry_size_estimate: Estimated size per entry
        """
        self._max_bytes = max_bytes
        self._entry_size_estimate = entry_size_estimate
        self._max_entries = max_bytes // entry_size_estimate

        self._buffer: list[V] = []

    def append(self, value: V) -> None:
        """Append value, evicting oldest if at capacity."""
        self._buffer.append(value)
        while len(self._buffer) > self._max_entries:
            self._buffer.pop(0)

    def extend(self, values: list[V]) -> None:
        """Extend with values."""
        self._buffer.extend(values)
        while len(self._buffer) > self._max_entries:
            self._buffer.pop(0)

    def get_all(self) -> list[V]:
        """Get all values."""
        return self._buffer.copy()

    def get_latest(self, n: int) -> list[V]:
        """Get latest N values."""
        return self._buffer[-n:]

    def clear(self) -> None:
        """Clear buffer."""
        self._buffer.clear()

    def __len__(self) -> int:
        """Get current size."""
        return len(self._buffer)

    @property
    def max_entries(self) -> int:
        """Get max entries based on memory limit."""
        return self._max_entries

    @property
    def estimated_bytes(self) -> int:
        """Get estimated memory usage."""
        return len(self._buffer) * self._entry_size_estimate


# Memory caps configuration
DEFAULT_CACHE_SIZES = {
    "quote_cache": 100,  # Max symbols to track
    "bar_buffer": 500,  # Max bars per symbol/timeframe
    "event_log": 10000,  # Max events in memory
    "failure_window": 100,  # Max failures to track per window
}

DEFAULT_MEMORY_CAPS = {
    "quote_cache_mb": 1,  # 1MB for quote cache
    "bar_buffer_mb": 50,  # 50MB for bar buffers
    "event_buffer_mb": 10,  # 10MB for event logs
}


def get_cache_config() -> dict[str, Any]:
    """Get default cache configuration."""
    return {
        "sizes": DEFAULT_CACHE_SIZES.copy(),
        "memory_caps_mb": DEFAULT_MEMORY_CAPS.copy(),
    }
