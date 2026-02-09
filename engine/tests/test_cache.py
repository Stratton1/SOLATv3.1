"""
Tests for bounded cache implementations.

Tests:
- LRU eviction when at capacity
- TTL expiry
- WindowedCounter behavior
"""



from solat_engine.runtime.cache import (
    BoundedLRUCache,
    MemoryBoundedBuffer,
    WindowedCounter,
)


class TestBoundedLRUCache:
    """Tests for BoundedLRUCache."""

    def test_basic_get_set(self) -> None:
        """Test basic get/set operations."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(max_size=10)

        cache.set("a", 1)
        cache.set("b", 2)

        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("c") is None

    def test_lru_eviction(self) -> None:
        """Test LRU eviction when at capacity."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(max_size=3)

        # Fill cache
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        assert len(cache) == 3

        # Access "a" to make it most recently used
        _ = cache.get("a")

        # Add new item - should evict "b" (LRU)
        cache.set("d", 4)

        assert len(cache) == 3
        assert cache.get("a") == 1  # Still present (was accessed)
        assert cache.get("b") is None  # Evicted
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_update_existing_key(self) -> None:
        """Test updating an existing key."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(max_size=3)

        cache.set("a", 1)
        cache.set("a", 10)

        assert cache.get("a") == 10
        assert len(cache) == 1

    def test_ttl_expiry(self) -> None:
        """Test TTL-based expiry."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(
            max_size=10,
            ttl_seconds=0.1,  # 100ms TTL
        )

        cache.set("a", 1)
        assert cache.get("a") == 1

        # Wait for TTL to expire
        import time
        time.sleep(0.15)

        # Should be expired
        assert cache.get("a") is None

    def test_stats_tracking(self) -> None:
        """Test cache statistics tracking."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(max_size=2)

        # Misses
        _ = cache.get("a")
        _ = cache.get("b")

        assert cache.stats.misses == 2

        # Hits
        cache.set("a", 1)
        _ = cache.get("a")
        _ = cache.get("a")

        assert cache.stats.hits == 2

        # Evictions
        cache.set("b", 2)
        cache.set("c", 3)  # Should evict

        assert cache.stats.evictions == 1

    def test_cleanup_expired(self) -> None:
        """Test explicit cleanup of expired entries."""
        cache: BoundedLRUCache[str, int] = BoundedLRUCache(
            max_size=10,
            ttl_seconds=0.05,
        )

        cache.set("a", 1)
        cache.set("b", 2)

        import time
        time.sleep(0.1)

        removed = cache.cleanup_expired()
        assert removed == 2
        assert len(cache) == 0


class TestWindowedCounter:
    """Tests for WindowedCounter."""

    def test_count_in_window(self) -> None:
        """Test counting events within window."""
        counter = WindowedCounter(window_seconds=10.0)

        counter.record()
        counter.record()
        counter.record()

        assert counter.count() == 3

    def test_expiry_outside_window(self) -> None:
        """Test that events outside window are not counted."""
        counter = WindowedCounter(window_seconds=0.1)

        counter.record()

        import time
        time.sleep(0.15)

        # Record should have expired
        assert counter.count() == 0

    def test_max_events_limit(self) -> None:
        """Test max events limit is enforced."""
        counter = WindowedCounter(window_seconds=60.0, max_events=5)

        for _ in range(10):
            counter.record()

        # Should be capped at max_events
        assert len(counter._events) <= 5


class TestMemoryBoundedBuffer:
    """Tests for MemoryBoundedBuffer."""

    def test_append_within_capacity(self) -> None:
        """Test appending within capacity."""
        buffer: MemoryBoundedBuffer[str] = MemoryBoundedBuffer(
            max_bytes=1000,
            entry_size_estimate=100,
        )

        buffer.append("a")
        buffer.append("b")

        assert len(buffer) == 2
        assert buffer.get_all() == ["a", "b"]

    def test_eviction_at_capacity(self) -> None:
        """Test oldest entries are evicted at capacity."""
        buffer: MemoryBoundedBuffer[str] = MemoryBoundedBuffer(
            max_bytes=300,
            entry_size_estimate=100,  # Max 3 entries
        )

        buffer.append("a")
        buffer.append("b")
        buffer.append("c")
        buffer.append("d")  # Should evict "a"

        assert len(buffer) == 3
        assert buffer.get_all() == ["b", "c", "d"]

    def test_get_latest(self) -> None:
        """Test getting latest N entries."""
        buffer: MemoryBoundedBuffer[int] = MemoryBoundedBuffer(
            max_bytes=10000,
            entry_size_estimate=100,
        )

        for i in range(10):
            buffer.append(i)

        latest = buffer.get_latest(3)
        assert latest == [7, 8, 9]

    def test_estimated_bytes(self) -> None:
        """Test estimated memory usage."""
        buffer: MemoryBoundedBuffer[str] = MemoryBoundedBuffer(
            max_bytes=1000,
            entry_size_estimate=100,
        )

        buffer.append("a")
        buffer.append("b")

        assert buffer.estimated_bytes == 200
