"""
Tests for execution safety features.

Tests:
- Idempotency guard (duplicate rejection)
- Circuit breaker logic
- DEMO size caps
"""

from uuid import uuid4

from solat_engine.execution.safety import (
    CircuitBreaker,
    ExecutionSafetyGuard,
    IdempotencyGuard,
    SafetyConfig,
    SizeValidator,
)


class TestIdempotencyGuard:
    """Tests for IdempotencyGuard."""

    def test_first_intent_allowed(self) -> None:
        """Test that first intent is allowed."""
        config = SafetyConfig(idempotency_window_s=60.0)
        guard = IdempotencyGuard(config)

        intent_id = uuid4()
        allowed, error = guard.check_and_register(intent_id)

        assert allowed is True
        assert error is None

    def test_duplicate_rejected(self) -> None:
        """Test that duplicate intent is rejected."""
        config = SafetyConfig(idempotency_window_s=60.0)
        guard = IdempotencyGuard(config)

        intent_id = uuid4()

        # First attempt
        allowed1, _ = guard.check_and_register(intent_id)
        assert allowed1 is True

        # Second attempt (duplicate)
        allowed2, error = guard.check_and_register(intent_id)
        assert allowed2 is False
        assert "Duplicate" in (error or "")

    def test_different_intents_allowed(self) -> None:
        """Test that different intents are allowed."""
        config = SafetyConfig(idempotency_window_s=60.0)
        guard = IdempotencyGuard(config)

        id1 = uuid4()
        id2 = uuid4()

        allowed1, _ = guard.check_and_register(id1)
        allowed2, _ = guard.check_and_register(id2)

        assert allowed1 is True
        assert allowed2 is True

    def test_expiry_after_window(self) -> None:
        """Test that intents expire after window."""
        config = SafetyConfig(idempotency_window_s=0.05)  # 50ms
        guard = IdempotencyGuard(config)

        intent_id = uuid4()

        # First attempt
        guard.check_and_register(intent_id)

        import time
        time.sleep(0.1)

        # Should be allowed again after expiry
        allowed, error = guard.check_and_register(intent_id)
        assert allowed is True
        assert error is None

    def test_max_keys_eviction(self) -> None:
        """Test that oldest keys are evicted at max capacity."""
        config = SafetyConfig(
            idempotency_window_s=60.0,
            max_idempotency_keys=5,
        )
        guard = IdempotencyGuard(config)

        # Add more than max
        for _ in range(10):
            guard.check_and_register(uuid4())

        # Should have evicted some
        stats = guard.get_stats()
        assert stats["cached_intents"] <= config.max_idempotency_keys


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_not_tripped_initially(self) -> None:
        """Test circuit breaker starts in non-tripped state."""
        config = SafetyConfig(error_threshold=5)
        breaker = CircuitBreaker(config)

        assert breaker.is_tripped is False
        ok, _ = breaker.check()
        assert ok is True

    def test_trips_after_threshold(self) -> None:
        """Test circuit breaker trips after error threshold."""
        config = SafetyConfig(
            error_threshold=3,
            error_window_s=60.0,
            cooldown_s=60.0,
        )
        breaker = CircuitBreaker(config)

        # Record errors up to threshold
        breaker.record_error("error1")
        breaker.record_error("error2")
        tripped = breaker.record_error("error3")

        assert tripped is True
        assert breaker.is_tripped is True

        ok, error = breaker.check()
        assert ok is False
        assert "tripped" in (error or "").lower()

    def test_auto_reset_after_cooldown(self) -> None:
        """Test circuit breaker auto-resets after cooldown."""
        config = SafetyConfig(
            error_threshold=2,
            error_window_s=60.0,
            cooldown_s=0.1,  # 100ms cooldown
        )
        breaker = CircuitBreaker(config)

        # Trip the breaker
        breaker.record_error("error1")
        breaker.record_error("error2")

        assert breaker.is_tripped is True

        # Wait for cooldown
        import time
        time.sleep(0.15)

        # Should auto-reset
        assert breaker.is_tripped is False

    def test_manual_reset(self) -> None:
        """Test manual circuit breaker reset."""
        config = SafetyConfig(
            error_threshold=2,
            error_window_s=60.0,
            cooldown_s=300.0,  # Long cooldown
        )
        breaker = CircuitBreaker(config)

        # Trip the breaker
        breaker.record_error("error1")
        breaker.record_error("error2")

        assert breaker.is_tripped is True

        # Manual reset
        breaker.reset()

        assert breaker.is_tripped is False

    def test_errors_outside_window_not_counted(self) -> None:
        """Test that errors outside window are not counted."""
        config = SafetyConfig(
            error_threshold=3,
            error_window_s=0.05,  # 50ms window
        )
        breaker = CircuitBreaker(config)

        breaker.record_error("error1")

        import time
        time.sleep(0.1)

        # This error is in a new window
        breaker.record_error("error2")
        breaker.record_error("error3")

        # Shouldn't trip because error1 expired
        assert breaker.is_tripped is False


class TestSizeValidator:
    """Tests for SizeValidator."""

    def test_valid_size_allowed(self) -> None:
        """Test valid size is allowed."""
        config = SafetyConfig(demo_max_size=1.0)
        validator = SizeValidator(config, is_demo=True)

        valid, error = validator.validate(0.5)
        assert valid is True
        assert error is None

    def test_oversized_rejected_in_demo(self) -> None:
        """Test oversized order rejected in DEMO mode."""
        config = SafetyConfig(demo_max_size=1.0)
        validator = SizeValidator(config, is_demo=True)

        valid, error = validator.validate(2.0)
        assert valid is False
        assert "cap" in (error or "").lower()

    def test_oversized_allowed_in_live(self) -> None:
        """Test oversized order allowed in LIVE mode (no cap)."""
        config = SafetyConfig(demo_max_size=1.0)
        validator = SizeValidator(config, is_demo=False)

        valid, error = validator.validate(2.0)
        assert valid is True
        assert error is None

    def test_zero_size_rejected(self) -> None:
        """Test zero size is rejected."""
        config = SafetyConfig()
        validator = SizeValidator(config, is_demo=True)

        valid, error = validator.validate(0.0)
        assert valid is False

    def test_cap_size(self) -> None:
        """Test size capping in DEMO mode."""
        config = SafetyConfig(demo_max_size=1.0)
        validator = SizeValidator(config, is_demo=True)

        capped = validator.cap_size(5.0)
        assert capped == 1.0


class TestExecutionSafetyGuard:
    """Tests for integrated ExecutionSafetyGuard."""

    def test_valid_order_allowed(self) -> None:
        """Test valid order passes all checks."""
        guard = ExecutionSafetyGuard(is_demo=True)

        intent_id = uuid4()
        allowed, error = guard.pre_order_check(intent_id, 0.5)

        assert allowed is True
        assert error is None

    def test_duplicate_rejected(self) -> None:
        """Test duplicate order rejected by guard."""
        guard = ExecutionSafetyGuard(is_demo=True)

        intent_id = uuid4()
        guard.pre_order_check(intent_id, 0.5)

        # Try same intent again
        allowed, error = guard.pre_order_check(intent_id, 0.5)

        assert allowed is False
        assert "Duplicate" in (error or "")

    def test_circuit_breaker_blocks_after_errors(self) -> None:
        """Test circuit breaker blocks orders after errors."""
        config = SafetyConfig(error_threshold=2)
        guard = ExecutionSafetyGuard(config=config, is_demo=True)

        # Record errors to trip breaker
        guard.record_order_error("error1")
        guard.record_order_error("error2")

        # New order should be blocked
        allowed, error = guard.pre_order_check(uuid4(), 0.5)

        assert allowed is False
        assert "Circuit breaker" in (error or "")

    def test_oversized_rejected_in_demo(self) -> None:
        """Test oversized order rejected in DEMO mode."""
        config = SafetyConfig(demo_max_size=1.0)
        guard = ExecutionSafetyGuard(config=config, is_demo=True)

        allowed, error = guard.pre_order_check(uuid4(), 5.0)

        assert allowed is False
        assert "cap" in (error or "").lower()

    def test_size_capping(self) -> None:
        """Test size capping function."""
        config = SafetyConfig(demo_max_size=1.0)
        guard = ExecutionSafetyGuard(config=config, is_demo=True)

        capped = guard.cap_size(5.0)
        assert capped == 1.0

    def test_stats_tracking(self) -> None:
        """Test statistics tracking."""
        guard = ExecutionSafetyGuard(is_demo=True)

        guard.pre_order_check(uuid4(), 0.5)
        guard.record_order_error("test error")

        stats = guard.get_stats()

        assert "idempotency" in stats.__dict__
        assert "circuit_breaker" in stats.__dict__
        assert stats.demo_mode is True
