"""
API rate limiting and response caching.

Provides:
- Per-endpoint rate limiting with 429 responses
- Response caching with TTL
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitState:
    """State for a rate limited client/endpoint."""

    last_request_time: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))
    request_count: int = 0


class APIRateLimiter:
    """
    API rate limiter with per-client limiting.

    Returns 429 Too Many Requests when limit exceeded.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        name: str = "api",
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Max requests per second
            name: Name for logging
        """
        self._rps = requests_per_second
        self._min_interval = 1.0 / requests_per_second
        self._name = name

        # Per-client state (using client IP)
        self._clients: dict[str, RateLimitState] = defaultdict(RateLimitState)

        # Stats
        self._total_requests = 0
        self._rejected_requests = 0

    def check(self, client_id: str) -> None:
        """
        Check if request is allowed, raise 429 if not.

        Args:
            client_id: Client identifier (e.g., IP address)

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        self._total_requests += 1
        now = datetime.now(UTC)
        state = self._clients[client_id]

        elapsed = (now - state.last_request_time).total_seconds()

        if elapsed < self._min_interval:
            self._rejected_requests += 1
            retry_after = self._min_interval - elapsed
            logger.warning(
                "%s rate limit exceeded for %s (retry after %.2fs)",
                self._name,
                client_id,
                retry_after,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self._rps} requests/sec. Retry after {retry_after:.2f}s",
                headers={"Retry-After": str(int(retry_after + 1))},
            )

        # Update state
        state.last_request_time = now
        state.request_count += 1

    def get_client_id(self, request: Request) -> str:
        """Get client ID from request (IP-based)."""
        # Use X-Forwarded-For if behind proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "name": self._name,
            "requests_per_second": self._rps,
            "total_requests": self._total_requests,
            "rejected_requests": self._rejected_requests,
            "rejection_rate": (
                self._rejected_requests / self._total_requests * 100
                if self._total_requests > 0
                else 0
            ),
            "active_clients": len(self._clients),
        }


@dataclass
class CacheEntry:
    """Cached response entry."""

    response: Any
    created_at: datetime
    hits: int = 0


class ResponseCache:
    """
    Response cache with TTL.

    Caches expensive computations to reduce load.
    """

    def __init__(
        self,
        ttl_seconds: float = 5.0,
        max_entries: int = 100,
        name: str = "cache",
    ):
        """
        Initialize response cache.

        Args:
            ttl_seconds: Time-to-live for cache entries
            max_entries: Maximum cache entries
            name: Name for logging
        """
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._name = name

        self._cache: dict[str, CacheEntry] = {}

        # Stats
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, *args: Any, **kwargs: Any) -> Any | None:
        """
        Get cached response.

        Args:
            *args, **kwargs: Cache key components

        Returns:
            Cached response or None if not found/expired
        """
        key = self._make_key(*args, **kwargs)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        # Check TTL
        age = (datetime.now(UTC) - entry.created_at).total_seconds()
        if age > self._ttl_seconds:
            self._cache.pop(key, None)
            self._misses += 1
            return None

        self._hits += 1
        entry.hits += 1
        return entry.response

    def set(self, response: Any, *args: Any, **kwargs: Any) -> None:
        """
        Cache a response.

        Args:
            response: Response to cache
            *args, **kwargs: Cache key components
        """
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_entries:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at,
            )
            self._cache.pop(oldest_key)

        key = self._make_key(*args, **kwargs)
        self._cache[key] = CacheEntry(
            response=response,
            created_at=datetime.now(UTC),
        )

    def clear(self) -> None:
        """Clear cache."""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "name": self._name,
            "ttl_seconds": self._ttl_seconds,
            "max_entries": self._max_entries,
            "current_entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total * 100 if total > 0 else 0,
        }


# Global instances for chart endpoints
_overlay_rate_limiter: APIRateLimiter | None = None
_signals_rate_limiter: APIRateLimiter | None = None
_overlay_cache: ResponseCache | None = None
_signals_cache: ResponseCache | None = None


def get_overlay_rate_limiter() -> APIRateLimiter:
    """Get overlay rate limiter (1 req/sec)."""
    global _overlay_rate_limiter
    if _overlay_rate_limiter is None:
        _overlay_rate_limiter = APIRateLimiter(
            requests_per_second=1.0,
            name="overlay",
        )
    return _overlay_rate_limiter


def get_signals_rate_limiter() -> APIRateLimiter:
    """Get signals rate limiter (1 req/sec)."""
    global _signals_rate_limiter
    if _signals_rate_limiter is None:
        _signals_rate_limiter = APIRateLimiter(
            requests_per_second=1.0,
            name="signals",
        )
    return _signals_rate_limiter


def get_overlay_cache() -> ResponseCache:
    """Get overlay cache (5s TTL)."""
    global _overlay_cache
    if _overlay_cache is None:
        _overlay_cache = ResponseCache(
            ttl_seconds=5.0,
            max_entries=100,
            name="overlay",
        )
    return _overlay_cache


def get_signals_cache() -> ResponseCache:
    """Get signals cache (10s TTL)."""
    global _signals_cache
    if _signals_cache is None:
        _signals_cache = ResponseCache(
            ttl_seconds=10.0,
            max_entries=100,
            name="signals",
        )
    return _signals_cache


def reset_rate_limiters() -> None:
    """Reset all rate limiters (for testing)."""
    global _overlay_rate_limiter, _signals_rate_limiter
    global _overlay_cache, _signals_cache
    _overlay_rate_limiter = None
    _signals_rate_limiter = None
    _overlay_cache = None
    _signals_cache = None
