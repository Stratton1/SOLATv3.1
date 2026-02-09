"""
Rate limiting for IG API requests.

Implements a token bucket algorithm to enforce rate limits.
"""

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """
    Token bucket rate limiter.

    Allows bursts up to `burst` tokens, refilling at `rate` tokens per second.
    """

    rate: float  # Tokens per second
    burst: int  # Maximum bucket size
    tokens: float = field(init=False)
    last_update: float = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize bucket with full tokens."""
        self.tokens = float(self.burst)
        self.last_update = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on time elapsed."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_update = now

    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time waited in seconds (0 if no wait needed)
        """
        async with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            # Calculate wait time
            needed = tokens - self.tokens
            wait_time = needed / self.rate

            # Wait and then acquire
            await asyncio.sleep(wait_time)
            self._refill()
            self.tokens -= tokens
            return wait_time

    def available(self) -> float:
        """
        Get current available tokens (without acquiring).

        Returns:
            Number of tokens currently available
        """
        self._refill()
        return self.tokens


class RateLimiter:
    """
    Rate limiter for IG API.

    Provides methods to acquire permission before making requests.
    """

    def __init__(self, requests_per_second: float, burst: int) -> None:
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Target rate limit
            burst: Maximum burst size
        """
        self._bucket = TokenBucket(rate=requests_per_second, burst=burst)
        self._total_requests: int = 0
        self._total_wait_time: float = 0.0

    async def acquire(self) -> float:
        """
        Acquire permission for one request.

        Returns:
            Time waited in seconds
        """
        wait_time = await self._bucket.acquire(1)
        self._total_requests += 1
        self._total_wait_time += wait_time
        return wait_time

    @property
    def stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "total_requests": self._total_requests,
            "total_wait_time_seconds": round(self._total_wait_time, 3),
            "available_tokens": round(self._bucket.available(), 2),
            "rate_limit_rps": self._bucket.rate,
            "burst_limit": self._bucket.burst,
        }
