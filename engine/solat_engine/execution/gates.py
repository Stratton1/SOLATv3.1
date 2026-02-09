"""
Trading gates for LIVE mode safety.

Provides multi-layer gating to prevent accidental LIVE trading:
1. Config gate: LIVE_TRADING_ENABLED must be true
2. Token gate: LIVE_ENABLE_TOKEN must match
3. UI gate: User must confirm via modal with typed phrase
4. Prelive gate: Pre-live check must have passed recently
5. Account gate: Account must be verified and locked
6. Risk gate: All mandatory risk settings must be configured

INVARIANT: Any uncertainty or missing gate MUST fail CLOSED (no trading).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from solat_engine.config import TradingMode, get_settings
from solat_engine.logging import get_logger

logger = get_logger(__name__)


class GateMode(str, Enum):
    """Trading mode after gate evaluation."""

    DEMO = "DEMO"
    LIVE = "LIVE"


@dataclass
class GateStatus:
    """
    Result of trading gate evaluation.

    If allowed is False, trading is blocked.
    If mode is LIVE, all LIVE gates have passed.
    """

    allowed: bool
    mode: GateMode
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response dict."""
        return {
            "allowed": self.allowed,
            "mode": self.mode.value,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "details": self.details,
        }


@dataclass
class LiveConfirmation:
    """
    UI confirmation for LIVE trading.

    Short-lived (TTL-based) confirmation from UI modal flow.
    """

    confirmed_at: datetime
    account_id: str
    phrase_matched: bool
    token_matched: bool
    prelive_passed: bool
    ttl_seconds: int

    @property
    def is_expired(self) -> bool:
        """Check if confirmation has expired."""
        age = (datetime.now(UTC) - self.confirmed_at).total_seconds()
        return age > self.ttl_seconds

    @property
    def is_valid(self) -> bool:
        """Check if confirmation is valid (not expired and all checks passed)."""
        return (
            not self.is_expired
            and self.phrase_matched
            and self.token_matched
            and self.prelive_passed
        )


@dataclass
class AccountVerification:
    """
    Verified broker account details.

    Captured during account lock to ensure LIVE trades go to correct account.
    """

    account_id: str
    account_type: str  # "CFD", "SPREADBET", etc.
    currency: str
    balance: float
    available: float
    is_live: bool
    verified_at: datetime

    @property
    def age_seconds(self) -> float:
        """Get age of verification in seconds."""
        return (datetime.now(UTC) - self.verified_at).total_seconds()


class TradingGates:
    """
    Multi-layer trading gate evaluator.

    Evaluates all gates and returns a GateStatus indicating if trading is allowed.
    LIVE mode requires ALL gates to pass. DEMO mode is always allowed.
    """

    def __init__(self) -> None:
        """Initialize trading gates."""
        self._settings = get_settings()
        self._ui_confirmation: LiveConfirmation | None = None
        self._account_verification: AccountVerification | None = None
        self._last_prelive_pass: datetime | None = None
        self._locked_account_id: str | None = None

    def evaluate(self, requested_mode: GateMode | None = None) -> GateStatus:
        """
        Evaluate all trading gates.

        Args:
            requested_mode: Mode requested (LIVE or DEMO). If None, uses config.

        Returns:
            GateStatus with allowed/blocked status and reasons.
        """
        blockers: list[str] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}

        # Determine requested mode
        if requested_mode is None:
            config_mode = self._settings.mode
            requested_mode = GateMode.LIVE if config_mode == TradingMode.LIVE else GateMode.DEMO

        details["requested_mode"] = requested_mode.value

        # DEMO mode is always allowed
        if requested_mode == GateMode.DEMO:
            return GateStatus(
                allowed=True,
                mode=GateMode.DEMO,
                blockers=[],
                warnings=[],
                details=details,
            )

        # LIVE mode - evaluate all gates
        details["live_trading_enabled"] = self._settings.live_trading_enabled
        details["has_live_token"] = self._settings.has_live_token
        details["has_live_account_lock"] = self._settings.has_live_account_lock
        details["has_live_risk_config"] = self._settings.has_live_risk_config

        # Gate 1: Config gate
        if not self._settings.live_trading_enabled:
            blockers.append("LIVE_TRADING_ENABLED is not set to true")

        # Gate 2: Token gate
        if not self._settings.has_live_token:
            blockers.append("LIVE_ENABLE_TOKEN is not configured")

        # Gate 3: Risk config gate
        risk_blockers = self._settings.get_live_risk_blockers()
        if risk_blockers:
            blockers.extend(risk_blockers)

        # Gate 4: Account lock gate
        if not self._settings.has_live_account_lock:
            blockers.append("LIVE_ACCOUNT_ID is not configured")

        # Gate 5: Account verification gate
        if self._account_verification is None:
            blockers.append("Account not verified with broker")
        elif not self._account_verification.is_live:
            blockers.append("Verified account is not a LIVE account")
        elif self._account_verification.account_id != self._settings.live_account_id:
            blockers.append("Verified account ID does not match LIVE_ACCOUNT_ID")
        else:
            details["verified_account_id"] = self._account_verification.account_id
            details["account_balance"] = self._account_verification.balance
            details["account_available"] = self._account_verification.available

            # Check available funds
            if self._account_verification.available <= 0:
                blockers.append("No available funds in verified account")

        # Gate 6: UI confirmation gate
        if self._ui_confirmation is None:
            blockers.append("UI LIVE confirmation not completed")
        elif self._ui_confirmation.is_expired:
            blockers.append(
                f"UI LIVE confirmation expired (TTL: {self._ui_confirmation.ttl_seconds}s)"
            )
        elif not self._ui_confirmation.is_valid:
            if not self._ui_confirmation.phrase_matched:
                blockers.append("UI confirmation phrase not matched")
            if not self._ui_confirmation.token_matched:
                blockers.append("UI confirmation token not matched")
            if not self._ui_confirmation.prelive_passed:
                blockers.append("Prelive check not passed during UI confirmation")
        else:
            details["ui_confirmation_age_s"] = (
                datetime.now(UTC) - self._ui_confirmation.confirmed_at
            ).total_seconds()

        # Gate 7: Prelive check gate
        if self._last_prelive_pass is None:
            blockers.append("Pre-live check has never passed")
        else:
            prelive_age = (datetime.now(UTC) - self._last_prelive_pass).total_seconds()
            details["prelive_age_s"] = prelive_age
            if prelive_age > self._settings.live_prelive_max_age_s:
                blockers.append(
                    f"Pre-live check too old ({prelive_age:.0f}s > {self._settings.live_prelive_max_age_s}s)"
                )

        # Warnings (non-blocking)
        if self._account_verification and self._account_verification.age_seconds > 300:
                warnings.append(
                    f"Account verification is {self._account_verification.age_seconds:.0f}s old"
                )

        # Final decision
        allowed = len(blockers) == 0
        mode = GateMode.LIVE if allowed else GateMode.DEMO

        if not allowed:
            logger.warning(
                "LIVE trading blocked: %d blockers: %s",
                len(blockers),
                ", ".join(blockers[:3]),
            )

        return GateStatus(
            allowed=allowed,
            mode=mode,
            blockers=blockers,
            warnings=warnings,
            details=details,
        )

    def set_ui_confirmation(
        self,
        account_id: str,
        phrase_matched: bool,
        token_matched: bool,
        prelive_passed: bool,
    ) -> LiveConfirmation:
        """
        Set UI LIVE confirmation.

        Called after user completes the GoLive modal flow.

        Returns:
            The created confirmation object.
        """
        self._ui_confirmation = LiveConfirmation(
            confirmed_at=datetime.now(UTC),
            account_id=account_id,
            phrase_matched=phrase_matched,
            token_matched=token_matched,
            prelive_passed=prelive_passed,
            ttl_seconds=self._settings.live_confirmation_ttl_s,
        )

        logger.info(
            "LIVE UI confirmation set for account %s (TTL: %ds)",
            account_id,
            self._settings.live_confirmation_ttl_s,
        )

        return self._ui_confirmation

    def revoke_ui_confirmation(self) -> None:
        """Revoke UI LIVE confirmation (e.g., on disarm or explicit revoke)."""
        if self._ui_confirmation is not None:
            logger.info("LIVE UI confirmation revoked")
            self._ui_confirmation = None

    def set_account_verification(
        self,
        account_id: str,
        account_type: str,
        currency: str,
        balance: float,
        available: float,
        is_live: bool,
    ) -> AccountVerification:
        """
        Set verified account details.

        Called after fetching and verifying account from broker.
        """
        self._account_verification = AccountVerification(
            account_id=account_id,
            account_type=account_type,
            currency=currency,
            balance=balance,
            available=available,
            is_live=is_live,
            verified_at=datetime.now(UTC),
        )

        logger.info(
            "Account verified: %s (%s, %s %.2f, LIVE=%s)",
            account_id,
            account_type,
            currency,
            balance,
            is_live,
        )

        return self._account_verification

    def record_prelive_pass(self) -> None:
        """Record that prelive check has passed."""
        self._last_prelive_pass = datetime.now(UTC)
        logger.info("Pre-live check passed at %s", self._last_prelive_pass.isoformat())

    def verify_token(self, provided_token: str) -> bool:
        """
        Verify provided token matches configured LIVE_ENABLE_TOKEN.

        SECURITY: Token comparison is constant-time to prevent timing attacks.
        """
        if not self._settings.has_live_token:
            return False

        expected = self._settings.live_enable_token
        if expected is None:
            return False

        expected_value = expected.get_secret_value()

        # Constant-time comparison
        import hmac

        return hmac.compare_digest(expected_value, provided_token)

    def get_confirmation_status(self) -> dict[str, Any]:
        """Get current confirmation status for API response."""
        if self._ui_confirmation is None:
            return {"confirmed": False, "expired": True}

        return {
            "confirmed": True,
            "expired": self._ui_confirmation.is_expired,
            "valid": self._ui_confirmation.is_valid,
            "account_id": self._ui_confirmation.account_id,
            "confirmed_at": self._ui_confirmation.confirmed_at.isoformat(),
            "ttl_seconds": self._ui_confirmation.ttl_seconds,
            "remaining_seconds": max(
                0,
                self._ui_confirmation.ttl_seconds
                - (datetime.now(UTC) - self._ui_confirmation.confirmed_at).total_seconds(),
            ),
        }

    def get_account_status(self) -> dict[str, Any]:
        """Get current account verification status."""
        if self._account_verification is None:
            return {"verified": False}

        return {
            "verified": True,
            "account_id": self._account_verification.account_id,
            "account_type": self._account_verification.account_type,
            "currency": self._account_verification.currency,
            "balance": self._account_verification.balance,
            "available": self._account_verification.available,
            "is_live": self._account_verification.is_live,
            "verified_at": self._account_verification.verified_at.isoformat(),
            "age_seconds": self._account_verification.age_seconds,
        }

    def reset(self) -> None:
        """Reset all gate state (for testing)."""
        self._ui_confirmation = None
        self._account_verification = None
        self._last_prelive_pass = None
        self._locked_account_id = None


# Global instance
_trading_gates: TradingGates | None = None


def get_trading_gates() -> TradingGates:
    """Get global TradingGates instance."""
    global _trading_gates
    if _trading_gates is None:
        _trading_gates = TradingGates()
    return _trading_gates


def reset_trading_gates() -> None:
    """Reset global TradingGates instance (for testing)."""
    global _trading_gates
    if _trading_gates is not None:
        _trading_gates.reset()
    _trading_gates = None
