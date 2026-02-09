"""
Tests for LIVE trading gates.

Tests gate logic, state machine validation, and order lifecycle
without making any network calls to the broker.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from solat_engine.execution.gates import (
    GateMode,
    GateStatus,
    LiveConfirmation,
    TradingGates,
    get_trading_gates,
    reset_trading_gates,
)
from solat_engine.execution.models import (
    OrderRegistry,
    OrderSide,
    OrderStatus,
    OrderTracker,
    validate_order_transition,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gates() -> TradingGates:
    """Create fresh TradingGates instance for testing."""
    reset_trading_gates()
    return get_trading_gates()


@pytest.fixture
def mock_settings():
    """Create mock settings for LIVE mode testing."""
    settings = MagicMock()
    settings.live_trading_enabled = True
    settings.has_live_token = True
    settings.has_live_account_lock = True
    settings.has_live_risk_config = True
    settings.live_account_id = "TEST-ACCOUNT-123"
    settings.live_confirmation_ttl_s = 600
    settings.live_prelive_max_age_s = 300
    settings.live_enable_token = MagicMock()
    settings.live_enable_token.get_secret_value.return_value = "test-secret-token"
    settings.get_live_risk_blockers.return_value = []
    settings.mode = MagicMock()
    settings.mode.value = "LIVE"
    return settings


# =============================================================================
# Gate Evaluation Tests
# =============================================================================


class TestGateEvaluation:
    """Tests for gate evaluation logic."""

    def test_demo_mode_always_allowed(self, gates: TradingGates) -> None:
        """DEMO mode should always be allowed regardless of gate state."""
        status = gates.evaluate(GateMode.DEMO)
        assert status.allowed is True
        assert status.mode == GateMode.DEMO
        assert len(status.blockers) == 0

    def test_live_mode_blocked_by_default(self, gates: TradingGates) -> None:
        """LIVE mode should be blocked when gates are not satisfied."""
        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert status.mode == GateMode.DEMO  # Falls back to DEMO
        assert len(status.blockers) > 0

    def test_live_blocked_without_live_trading_enabled(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked if LIVE_TRADING_ENABLED is false."""
        mock_settings.live_trading_enabled = False
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "LIVE_TRADING_ENABLED is not set to true" in status.blockers

    def test_live_blocked_without_token(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked if LIVE_ENABLE_TOKEN is not configured."""
        mock_settings.has_live_token = False
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "LIVE_ENABLE_TOKEN is not configured" in status.blockers

    def test_live_blocked_without_account_lock(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked if LIVE_ACCOUNT_ID is not configured."""
        mock_settings.has_live_account_lock = False
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "LIVE_ACCOUNT_ID is not configured" in status.blockers

    def test_live_blocked_without_ui_confirmation(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked without UI confirmation."""
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "UI LIVE confirmation not completed" in status.blockers

    def test_live_blocked_without_account_verification(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked without account verification."""
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "Account not verified with broker" in status.blockers

    def test_live_blocked_without_prelive_check(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked without pre-live check."""
        gates._settings = mock_settings

        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "Pre-live check has never passed" in status.blockers


# =============================================================================
# UI Confirmation Tests
# =============================================================================


class TestUIConfirmation:
    """Tests for UI confirmation flow."""

    def test_set_ui_confirmation(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Setting UI confirmation should create valid confirmation."""
        gates._settings = mock_settings

        confirmation = gates.set_ui_confirmation(
            account_id="TEST-ACCOUNT-123",
            phrase_matched=True,
            token_matched=True,
            prelive_passed=True,
        )

        assert confirmation.account_id == "TEST-ACCOUNT-123"
        assert confirmation.phrase_matched is True
        assert confirmation.token_matched is True
        assert confirmation.prelive_passed is True
        assert confirmation.is_valid is True
        assert confirmation.is_expired is False

    def test_confirmation_expires(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Confirmation should expire after TTL."""
        mock_settings.live_confirmation_ttl_s = 1  # 1 second TTL
        gates._settings = mock_settings

        confirmation = gates.set_ui_confirmation(
            account_id="TEST-ACCOUNT-123",
            phrase_matched=True,
            token_matched=True,
            prelive_passed=True,
        )

        # Manually set confirmed_at to past
        confirmation.confirmed_at = datetime.now(UTC) - timedelta(seconds=2)

        assert confirmation.is_expired is True
        assert confirmation.is_valid is False

    def test_revoke_confirmation(self, gates: TradingGates) -> None:
        """Revoking confirmation should clear it."""
        gates._ui_confirmation = LiveConfirmation(
            confirmed_at=datetime.now(UTC),
            account_id="TEST",
            phrase_matched=True,
            token_matched=True,
            prelive_passed=True,
            ttl_seconds=600,
        )

        gates.revoke_ui_confirmation()
        assert gates._ui_confirmation is None

    def test_confirmation_invalid_without_phrase(self, gates: TradingGates) -> None:
        """Confirmation should be invalid if phrase not matched."""
        confirmation = LiveConfirmation(
            confirmed_at=datetime.now(UTC),
            account_id="TEST",
            phrase_matched=False,  # Not matched
            token_matched=True,
            prelive_passed=True,
            ttl_seconds=600,
        )
        assert confirmation.is_valid is False

    def test_confirmation_invalid_without_token(self, gates: TradingGates) -> None:
        """Confirmation should be invalid if token not matched."""
        confirmation = LiveConfirmation(
            confirmed_at=datetime.now(UTC),
            account_id="TEST",
            phrase_matched=True,
            token_matched=False,  # Not matched
            prelive_passed=True,
            ttl_seconds=600,
        )
        assert confirmation.is_valid is False


# =============================================================================
# Account Verification Tests
# =============================================================================


class TestAccountVerification:
    """Tests for account verification."""

    def test_set_account_verification(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Setting account verification should store details."""
        gates._settings = mock_settings

        verification = gates.set_account_verification(
            account_id="TEST-ACCOUNT-123",
            account_type="CFD",
            currency="USD",
            balance=10000.0,
            available=8000.0,
            is_live=True,
        )

        assert verification.account_id == "TEST-ACCOUNT-123"
        assert verification.account_type == "CFD"
        assert verification.balance == 10000.0
        assert verification.is_live is True

    def test_live_blocked_if_account_not_live(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked if verified account is DEMO."""
        gates._settings = mock_settings

        gates.set_account_verification(
            account_id="TEST-ACCOUNT-123",
            account_type="CFD",
            currency="USD",
            balance=10000.0,
            available=8000.0,
            is_live=False,  # DEMO account
        )

        status = gates.evaluate(GateMode.LIVE)
        assert "Verified account is not a LIVE account" in status.blockers

    def test_live_blocked_if_account_id_mismatch(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """LIVE should be blocked if verified account doesn't match config."""
        gates._settings = mock_settings

        gates.set_account_verification(
            account_id="WRONG-ACCOUNT",  # Doesn't match LIVE_ACCOUNT_ID
            account_type="CFD",
            currency="USD",
            balance=10000.0,
            available=8000.0,
            is_live=True,
        )

        status = gates.evaluate(GateMode.LIVE)
        assert "Verified account ID does not match LIVE_ACCOUNT_ID" in status.blockers


# =============================================================================
# Token Verification Tests
# =============================================================================


class TestTokenVerification:
    """Tests for token verification."""

    def test_correct_token_matches(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Correct token should match."""
        gates._settings = mock_settings

        result = gates.verify_token("test-secret-token")
        assert result is True

    def test_wrong_token_does_not_match(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Wrong token should not match."""
        gates._settings = mock_settings

        result = gates.verify_token("wrong-token")
        assert result is False

    def test_empty_token_does_not_match(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Empty token should not match."""
        gates._settings = mock_settings

        result = gates.verify_token("")
        assert result is False


# =============================================================================
# Pre-live Check Tests
# =============================================================================


class TestPreliveCheck:
    """Tests for pre-live check recording."""

    def test_record_prelive_pass(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Recording prelive pass should update timestamp."""
        gates._settings = mock_settings

        assert gates._last_prelive_pass is None

        gates.record_prelive_pass()

        assert gates._last_prelive_pass is not None
        age = (datetime.now(UTC) - gates._last_prelive_pass).total_seconds()
        assert age < 1  # Should be very recent

    def test_stale_prelive_blocks_live(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Stale pre-live check should block LIVE mode."""
        mock_settings.live_prelive_max_age_s = 60
        gates._settings = mock_settings

        # Set prelive pass to be old
        gates._last_prelive_pass = datetime.now(UTC) - timedelta(seconds=120)

        status = gates.evaluate(GateMode.LIVE)
        assert any("Pre-live check too old" in b for b in status.blockers)


# =============================================================================
# Order State Machine Tests
# =============================================================================


class TestOrderStateMachine:
    """Tests for order state machine validation."""

    def test_valid_transition_pending_to_submitted(self) -> None:
        """PENDING -> SUBMITTED should be valid."""
        assert validate_order_transition(OrderStatus.PENDING, OrderStatus.SUBMITTED) is True

    def test_valid_transition_submitted_to_acknowledged(self) -> None:
        """SUBMITTED -> ACKNOWLEDGED should be valid."""
        assert validate_order_transition(OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED) is True

    def test_valid_transition_submitted_to_rejected(self) -> None:
        """SUBMITTED -> REJECTED should be valid."""
        assert validate_order_transition(OrderStatus.SUBMITTED, OrderStatus.REJECTED) is True

    def test_valid_transition_acknowledged_to_filled(self) -> None:
        """ACKNOWLEDGED -> FILLED should be valid."""
        assert validate_order_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.FILLED) is True

    def test_invalid_transition_pending_to_filled(self) -> None:
        """PENDING -> FILLED should be invalid (must go through SUBMITTED)."""
        assert validate_order_transition(OrderStatus.PENDING, OrderStatus.FILLED) is False

    def test_invalid_transition_from_terminal_state(self) -> None:
        """Transitions from terminal states should be invalid."""
        terminal_states = [
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        ]
        for state in terminal_states:
            assert validate_order_transition(state, OrderStatus.PENDING) is False
            assert validate_order_transition(state, OrderStatus.SUBMITTED) is False

    def test_terminal_state_detection(self) -> None:
        """Terminal states should be correctly identified."""
        assert OrderStatus.FILLED.is_terminal is True
        assert OrderStatus.REJECTED.is_terminal is True
        assert OrderStatus.CANCELLED.is_terminal is True
        assert OrderStatus.EXPIRED.is_terminal is True
        assert OrderStatus.PENDING.is_terminal is False
        assert OrderStatus.SUBMITTED.is_terminal is False
        assert OrderStatus.ACKNOWLEDGED.is_terminal is False

    def test_active_state_detection(self) -> None:
        """Active states should be correctly identified."""
        assert OrderStatus.PENDING.is_active is True
        assert OrderStatus.SUBMITTED.is_active is True
        assert OrderStatus.ACKNOWLEDGED.is_active is True
        assert OrderStatus.FILLED.is_active is False


# =============================================================================
# Order Tracker Tests
# =============================================================================


class TestOrderTracker:
    """Tests for order lifecycle tracking."""

    def test_create_tracker(self) -> None:
        """Should create tracker with initial state."""
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_123",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        assert tracker.status == OrderStatus.PENDING
        assert tracker.is_complete is False
        assert tracker.submitted_at is None
        assert len(tracker.status_history) == 0

    def test_valid_transition_updates_state(self) -> None:
        """Valid transition should update state and history."""
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_123",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        result = tracker.transition_to(OrderStatus.SUBMITTED)

        assert result is True
        assert tracker.status == OrderStatus.SUBMITTED
        assert tracker.submitted_at is not None
        assert len(tracker.status_history) == 1

    def test_invalid_transition_rejected(self) -> None:
        """Invalid transition should be rejected without state change."""
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_123",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        result = tracker.transition_to(OrderStatus.FILLED)  # Invalid from PENDING

        assert result is False
        assert tracker.status == OrderStatus.PENDING  # Unchanged
        assert len(tracker.status_history) == 0

    def test_same_state_transition_allowed(self) -> None:
        """Transitioning to same state should be allowed (idempotent)."""
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_123",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        result = tracker.transition_to(OrderStatus.PENDING)

        assert result is True
        assert tracker.status == OrderStatus.PENDING

    def test_complete_lifecycle(self) -> None:
        """Full order lifecycle should work correctly."""
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_123",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        # PENDING -> SUBMITTED
        assert tracker.transition_to(OrderStatus.SUBMITTED) is True
        assert tracker.submitted_at is not None

        # SUBMITTED -> ACKNOWLEDGED
        assert tracker.transition_to(OrderStatus.ACKNOWLEDGED) is True
        assert tracker.acked_at is not None

        # ACKNOWLEDGED -> FILLED
        assert tracker.transition_to(OrderStatus.FILLED) is True
        assert tracker.filled_at is not None
        assert tracker.terminal_at is not None
        assert tracker.is_complete is True


# =============================================================================
# Order Registry Tests
# =============================================================================


class TestOrderRegistry:
    """Tests for order registry (idempotency)."""

    def test_register_new_order(self) -> None:
        """Should register new orders successfully."""
        registry = OrderRegistry()
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_001",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        result = registry.register(tracker)

        assert result is True
        assert registry.has_reference("SOLAT_TEST_001") is True

    def test_reject_duplicate_reference(self) -> None:
        """Should reject duplicate deal references."""
        registry = OrderRegistry()
        tracker1 = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_001",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )
        tracker2 = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_001",  # Same reference
            symbol="GBPUSD",
            side=OrderSide.SELL,
            size=0.2,
        )

        registry.register(tracker1)
        result = registry.register(tracker2)

        assert result is False

    def test_lookup_by_intent(self) -> None:
        """Should find orders by intent ID."""
        registry = OrderRegistry()
        intent_id = uuid4()
        tracker = OrderTracker(
            intent_id=intent_id,
            deal_reference="SOLAT_TEST_001",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        registry.register(tracker)
        found = registry.get_by_intent(intent_id)

        assert found is not None
        assert found.deal_reference == "SOLAT_TEST_001"

    def test_lookup_by_deal_id(self) -> None:
        """Should find orders by broker deal ID after association."""
        registry = OrderRegistry()
        tracker = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_001",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )

        registry.register(tracker)
        registry.set_deal_id("SOLAT_TEST_001", "BROKER_DEAL_123")

        found = registry.get_by_deal_id("BROKER_DEAL_123")
        assert found is not None
        assert found.deal_id == "BROKER_DEAL_123"

    def test_pending_count(self) -> None:
        """Should track count of non-terminal orders."""
        registry = OrderRegistry()

        # Add two orders
        tracker1 = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_001",
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
        )
        tracker2 = OrderTracker(
            intent_id=uuid4(),
            deal_reference="SOLAT_TEST_002",
            symbol="GBPUSD",
            side=OrderSide.SELL,
            size=0.2,
        )

        registry.register(tracker1)
        registry.register(tracker2)

        assert registry.get_pending_count() == 2

        # Complete one
        tracker1.transition_to(OrderStatus.SUBMITTED)
        tracker1.transition_to(OrderStatus.ACKNOWLEDGED)
        tracker1.transition_to(OrderStatus.FILLED)

        assert registry.get_pending_count() == 1


# =============================================================================
# Gate Status Serialization Tests
# =============================================================================


class TestGateStatusSerialization:
    """Tests for GateStatus serialization."""

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict should include all fields."""
        status = GateStatus(
            allowed=True,
            mode=GateMode.LIVE,
            blockers=["blocker1"],
            warnings=["warning1"],
            details={"key": "value"},
        )

        result = status.to_dict()

        assert result["allowed"] is True
        assert result["mode"] == "LIVE"
        assert result["blockers"] == ["blocker1"]
        assert result["warnings"] == ["warning1"]
        assert result["details"] == {"key": "value"}


# =============================================================================
# Integration Tests (Mocked)
# =============================================================================


class TestFullLiveFlow:
    """Integration tests for full LIVE flow (all mocked)."""

    def test_full_live_enable_flow(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Full flow to enable LIVE trading should work when all gates pass."""
        gates._settings = mock_settings

        # Step 1: Initial status should be blocked
        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False

        # Step 2: Verify account
        gates.set_account_verification(
            account_id="TEST-ACCOUNT-123",
            account_type="CFD",
            currency="USD",
            balance=10000.0,
            available=8000.0,
            is_live=True,
        )

        # Step 3: Record prelive pass
        gates.record_prelive_pass()

        # Step 4: Set UI confirmation
        gates.set_ui_confirmation(
            account_id="TEST-ACCOUNT-123",
            phrase_matched=True,
            token_matched=True,
            prelive_passed=True,
        )

        # Step 5: Verify all gates pass
        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is True
        assert status.mode == GateMode.LIVE
        assert len(status.blockers) == 0

    def test_revoke_blocks_live(
        self, mock_settings, gates: TradingGates
    ) -> None:
        """Revoking confirmation should block LIVE mode."""
        gates._settings = mock_settings

        # Set up for LIVE
        gates.set_account_verification(
            account_id="TEST-ACCOUNT-123",
            account_type="CFD",
            currency="USD",
            balance=10000.0,
            available=8000.0,
            is_live=True,
        )
        gates.record_prelive_pass()
        gates.set_ui_confirmation(
            account_id="TEST-ACCOUNT-123",
            phrase_matched=True,
            token_matched=True,
            prelive_passed=True,
        )

        # Verify LIVE is enabled
        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is True

        # Revoke confirmation
        gates.revoke_ui_confirmation()

        # Verify LIVE is now blocked
        status = gates.evaluate(GateMode.LIVE)
        assert status.allowed is False
        assert "UI LIVE confirmation not completed" in status.blockers
