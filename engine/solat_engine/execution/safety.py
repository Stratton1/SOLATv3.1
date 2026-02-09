"""
Execution safety hardening.

Provides:
- Idempotency key deduplication (reject duplicate intent_id within window)
- Execution circuit breaker (pause after N order errors in Y seconds)
- DEMO mode size caps
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SafetyConfig:
    """Safety configuration."""

    # Idempotency
    idempotency_window_s: float = 60.0  # 1 minute
    max_idempotency_keys: int = 1000  # Max keys to track

    # Circuit breaker
    error_threshold: int = 5  # Errors before tripping
    error_window_s: float = 60.0  # Window for error counting
    cooldown_s: float = 120.0  # Cooldown after tripping

    # DEMO mode caps
    demo_max_size: float = 1.0  # Max 1 lot in DEMO


@dataclass
class IdempotencyEntry:
    """Entry in idempotency cache."""

    intent_id: UUID
    timestamp: datetime
    result: Any = None


class IdempotencyGuard:
    """
    Guards against duplicate order submissions.

    Tracks intent IDs within a time window and rejects duplicates.
    """

    def __init__(self, config: SafetyConfig):
        """Initialize guard."""
        self._config = config
        self._cache: dict[UUID, IdempotencyEntry] = {}

    def check_and_register(self, intent_id: UUID) -> tuple[bool, str | None]:
        """
        Check if intent is a duplicate and register if not.

        Args:
            intent_id: Intent ID to check

        Returns:
            Tuple of (is_allowed, error_message)
            is_allowed is True if this is a new intent
        """
        self._cleanup_expired()

        # Check for duplicate
        if intent_id in self._cache:
            entry = self._cache[intent_id]
            age_s = (datetime.now(UTC) - entry.timestamp).total_seconds()
            logger.warning(
                "Duplicate intent_id rejected: %s (seen %.1fs ago)",
                intent_id,
                age_s,
            )
            return False, f"Duplicate intent_id (seen {age_s:.1f}s ago)"

        # Register new intent
        self._cache[intent_id] = IdempotencyEntry(
            intent_id=intent_id,
            timestamp=datetime.now(UTC),
        )

        # Enforce max keys
        if len(self._cache) > self._config.max_idempotency_keys:
            self._evict_oldest()

        return True, None

    def register_result(self, intent_id: UUID, result: Any) -> None:
        """Store result for an intent (for potential retry logic)."""
        if intent_id in self._cache:
            self._cache[intent_id].result = result

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = datetime.now(UTC)
        cutoff = now.timestamp() - self._config.idempotency_window_s
        expired = [
            k for k, v in self._cache.items() if v.timestamp.timestamp() < cutoff
        ]
        for key in expired:
            del self._cache[key]

    def _evict_oldest(self) -> None:
        """Evict oldest entries to stay under max."""
        if not self._cache:
            return

        # Sort by timestamp and remove oldest 10%
        sorted_entries = sorted(
            self._cache.items(), key=lambda x: x[1].timestamp
        )
        to_remove = max(1, len(sorted_entries) // 10)

        for key, _ in sorted_entries[:to_remove]:
            del self._cache[key]

    def get_stats(self) -> dict[str, Any]:
        """Get guard statistics."""
        return {
            "cached_intents": len(self._cache),
            "max_keys": self._config.max_idempotency_keys,
            "window_s": self._config.idempotency_window_s,
        }

    def reset(self) -> None:
        """Reset guard (for testing)."""
        self._cache.clear()


class CircuitBreaker:
    """
    Execution circuit breaker.

    Trips after N order errors in Y seconds, then enters cooldown.
    Must be manually reset or wait for cooldown.
    """

    def __init__(self, config: SafetyConfig):
        """Initialize circuit breaker."""
        self._config = config
        self._error_times: list[datetime] = []
        self._tripped_at: datetime | None = None
        self._total_errors = 0
        self._total_trips = 0

    @property
    def is_tripped(self) -> bool:
        """Check if circuit breaker is tripped."""
        if self._tripped_at is None:
            return False

        # Check if cooldown has elapsed
        elapsed = (datetime.now(UTC) - self._tripped_at).total_seconds()
        if elapsed >= self._config.cooldown_s:
            # Auto-reset after cooldown
            logger.info("Circuit breaker auto-reset after cooldown")
            self._tripped_at = None
            return False

        return True

    @property
    def remaining_cooldown_s(self) -> float:
        """Get remaining cooldown time."""
        if self._tripped_at is None:
            return 0.0

        elapsed = (datetime.now(UTC) - self._tripped_at).total_seconds()
        return max(0.0, self._config.cooldown_s - elapsed)

    def record_error(self, error: str) -> bool:
        """
        Record an order error.

        Args:
            error: Error message

        Returns:
            True if circuit breaker just tripped
        """
        now = datetime.now(UTC)
        self._error_times.append(now)
        self._total_errors += 1

        # Clean old errors outside window
        cutoff = now.timestamp() - self._config.error_window_s
        self._error_times = [
            t for t in self._error_times if t.timestamp() > cutoff
        ]

        # Check if we should trip
        if len(self._error_times) >= self._config.error_threshold and not self.is_tripped:
                self._trip(error)
                return True

        return False

    def record_success(self) -> None:
        """Record a successful order (doesn't affect error count, just for stats)."""
        pass

    def _trip(self, reason: str) -> None:
        """Trip the circuit breaker."""
        self._tripped_at = datetime.now(UTC)
        self._total_trips += 1
        logger.error(
            "Circuit breaker TRIPPED: %d errors in %.0fs (reason: %s)",
            len(self._error_times),
            self._config.error_window_s,
            reason,
        )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        if self._tripped_at is not None:
            logger.info("Circuit breaker manually reset")
            self._tripped_at = None
            self._error_times.clear()

    def check(self) -> tuple[bool, str | None]:
        """
        Check if orders can proceed.

        Returns:
            Tuple of (can_proceed, error_message)
        """
        if self.is_tripped:
            remaining = self.remaining_cooldown_s
            return False, f"Circuit breaker tripped. Cooldown: {remaining:.0f}s"
        return True, None

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "is_tripped": self.is_tripped,
            "tripped_at": self._tripped_at.isoformat() if self._tripped_at else None,
            "remaining_cooldown_s": self.remaining_cooldown_s,
            "errors_in_window": len(self._error_times),
            "error_threshold": self._config.error_threshold,
            "total_errors": self._total_errors,
            "total_trips": self._total_trips,
        }


class SizeValidator:
    """
    Validates order sizes with DEMO mode caps.
    """

    def __init__(self, config: SafetyConfig, is_demo: bool = True):
        """Initialize validator."""
        self._config = config
        self._is_demo = is_demo

    def validate(self, size: float) -> tuple[bool, str | None]:
        """
        Validate order size.

        Args:
            size: Order size to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if size <= 0:
            return False, "Size must be positive"

        if self._is_demo and size > self._config.demo_max_size:
            logger.warning(
                "DEMO size cap exceeded: %.2f > %.2f",
                size,
                self._config.demo_max_size,
            )
            return False, f"DEMO mode size cap: max {self._config.demo_max_size} lots"

        return True, None

    def cap_size(self, size: float) -> float:
        """Cap size to DEMO limit if applicable."""
        if self._is_demo:
            return min(size, self._config.demo_max_size)
        return size


@dataclass
class SafetyStats:
    """Combined safety statistics."""

    idempotency: dict[str, Any] = field(default_factory=dict)
    circuit_breaker: dict[str, Any] = field(default_factory=dict)
    demo_mode: bool = True
    demo_max_size: float = 1.0


class ExecutionSafetyGuard:
    """
    Combined execution safety guard.

    Integrates idempotency, circuit breaker, and size validation.
    """

    def __init__(self, config: SafetyConfig | None = None, is_demo: bool = True):
        """Initialize safety guard."""
        self._config = config or SafetyConfig()
        self._is_demo = is_demo

        self._idempotency = IdempotencyGuard(self._config)
        self._circuit_breaker = CircuitBreaker(self._config)
        self._size_validator = SizeValidator(self._config, is_demo)

    def pre_order_check(
        self,
        intent_id: UUID,
        size: float,
    ) -> tuple[bool, str | None]:
        """
        Perform all pre-order safety checks.

        Args:
            intent_id: Order intent ID
            size: Order size

        Returns:
            Tuple of (is_allowed, error_message)
        """
        # Check circuit breaker first
        ok, err = self._circuit_breaker.check()
        if not ok:
            return False, err

        # Check idempotency
        ok, err = self._idempotency.check_and_register(intent_id)
        if not ok:
            return False, err

        # Check size
        ok, err = self._size_validator.validate(size)
        if not ok:
            return False, err

        return True, None

    def record_order_error(self, error: str) -> bool:
        """
        Record an order error.

        Returns True if circuit breaker just tripped.
        """
        return self._circuit_breaker.record_error(error)

    def record_order_success(self, intent_id: UUID, result: Any) -> None:
        """Record successful order."""
        self._idempotency.register_result(intent_id, result)
        self._circuit_breaker.record_success()

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker."""
        self._circuit_breaker.reset()

    def cap_size(self, size: float) -> float:
        """Cap size if in DEMO mode."""
        return self._size_validator.cap_size(size)

    def get_stats(self) -> SafetyStats:
        """Get combined safety statistics."""
        return SafetyStats(
            idempotency=self._idempotency.get_stats(),
            circuit_breaker=self._circuit_breaker.get_stats(),
            demo_mode=self._is_demo,
            demo_max_size=self._config.demo_max_size,
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get circuit breaker."""
        return self._circuit_breaker

    @property
    def is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is tripped."""
        return self._circuit_breaker.is_tripped

    @property
    def circuit_breaker_tripped(self) -> bool:
        """Alias for is_circuit_breaker_tripped (API compatibility)."""
        return self._circuit_breaker.is_tripped
