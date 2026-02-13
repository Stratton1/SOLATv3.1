"""
Kill Switch for emergency trading halt.

When activated:
- Disarms trading
- Blocks all new orders
- Optionally closes all open positions
"""

from datetime import UTC, datetime
from pathlib import Path

from solat_engine.execution.models import ExecutionConfig, PositionView
from solat_engine.logging import get_logger

logger = get_logger(__name__)


class KillSwitch:
    """
    Emergency kill switch for trading halt.

    Thread-safe activation/deactivation with optional position closing.
    """

    def __init__(self, config: ExecutionConfig):
        """
        Initialize kill switch.

        Args:
            config: Execution configuration
        """
        self._config = config
        self._active = False
        self._activated_at: datetime | None = None
        self._activated_by: str | None = None
        self._activation_reason: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._active

    @property
    def activated_at(self) -> datetime | None:
        """Get activation timestamp."""
        return self._activated_at

    @property
    def activation_reason(self) -> str | None:
        """Get activation reason."""
        return self._activation_reason

    def activate(
        self,
        reason: str = "manual",
        activated_by: str = "user",
    ) -> dict[str, str | bool | None]:
        """
        Activate kill switch.

        Args:
            reason: Reason for activation
            activated_by: Who/what activated it

        Returns:
            Activation result with timestamp
        """
        if self._active:
            logger.warning("Kill switch already active, ignoring duplicate activation")
            return {
                "ok": False,
                "message": "Kill switch already active",
                "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            }

        self._active = True
        self._activated_at = datetime.now(UTC)
        self._activated_by = activated_by
        self._activation_reason = reason

        logger.critical(
            "KILL SWITCH ACTIVATED by %s: %s",
            activated_by,
            reason,
        )

        return {
            "ok": True,
            "message": "Kill switch activated",
            "activated_at": self._activated_at.isoformat(),
            "reason": reason,
            "close_positions": self._config.close_on_kill_switch,
        }

    def reset(self, reset_by: str = "user") -> dict[str, str | bool | None]:
        """
        Reset (deactivate) kill switch.

        Args:
            reset_by: Who/what reset it

        Returns:
            Reset result
        """
        if not self._active:
            logger.info("Kill switch not active, nothing to reset")
            return {
                "ok": True,
                "message": "Kill switch was not active",
            }

        was_activated_at = self._activated_at
        was_reason = self._activation_reason

        self._active = False
        self._activated_at = None
        self._activated_by = None
        self._activation_reason = None

        logger.warning(
            "Kill switch RESET by %s (was activated at %s for: %s)",
            reset_by,
            was_activated_at.isoformat() if was_activated_at else "unknown",
            was_reason or "unknown",
        )

        return {
            "ok": True,
            "message": "Kill switch reset",
            "was_activated_at": was_activated_at.isoformat() if was_activated_at else None,
            "was_reason": was_reason,
        }

    def check_can_trade(self) -> tuple[bool, str | None]:
        """
        Check if trading is allowed (kill switch not active).

        Returns:
            Tuple of (can_trade, rejection_reason)
        """
        if self._active:
            return False, f"Kill switch active since {self._activated_at}: {self._activation_reason}"
        return True, None

    def get_positions_to_close(
        self,
        positions: list[PositionView],
    ) -> list[PositionView]:
        """
        Get positions that should be closed due to kill switch.

        Args:
            positions: Current open positions

        Returns:
            List of positions to close (empty if close_on_kill_switch is False)
        """
        if not self._config.close_on_kill_switch:
            return []
        return positions

    def get_state(self) -> dict[str, str | bool | None]:
        """Get current kill switch state."""
        return {
            "active": self._active,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "activated_by": self._activated_by,
            "reason": self._activation_reason,
            "close_on_kill_switch": self._config.close_on_kill_switch,
        }

    def update_config(self, config: ExecutionConfig) -> None:
        """Update configuration."""
        self._config = config

    def save_state(self, state_file: Path) -> None:
        """
        Persist kill switch state to disk.

        Args:
            state_file: Path to state file (JSON)
        """
        import json

        state_file.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "active": self._active,
            "reason": self._activation_reason,
            "activated_at": self._activated_at.isoformat() if self._activated_at else None,
            "activated_by": self._activated_by,
        }

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        logger.debug("Kill switch state saved to %s", state_file)

    def restore_state(self, state_file: Path) -> None:
        """
        Restore kill switch state from disk.

        Args:
            state_file: Path to state file (JSON)
        """
        if not state_file.exists():
            logger.debug("No kill switch state file found at %s", state_file)
            return

        import json

        try:
            with open(state_file) as f:
                state = json.load(f)

            if state.get("active"):
                self._active = True
                self._activation_reason = state.get("reason", "unknown")
                self._activated_by = state.get("activated_by", "unknown")

                activated_at_str = state.get("activated_at")
                if activated_at_str:
                    normalized = activated_at_str.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(normalized)
                    self._activated_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

                logger.warning(
                    "Restored active kill switch from %s: %s (activated at %s)",
                    state_file,
                    self._activation_reason,
                    self._activated_at.isoformat() if self._activated_at else "unknown",
                )
            else:
                logger.debug("Kill switch state restored (inactive)")

        except Exception as e:
            logger.error("Failed to restore kill switch state from %s: %s", state_file, e)
