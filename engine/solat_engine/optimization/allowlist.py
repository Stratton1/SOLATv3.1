"""
Dynamic Allowlist Manager.

Manages which bot/symbol/timeframe combinations are approved for live trading
based on walk-forward validation results.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from solat_engine.config import get_settings
from solat_engine.logging import get_logger
from solat_engine.optimization.models import (
    AllowlistConfig,
    AllowlistEntry,
    WalkForwardResult,
)

logger = get_logger(__name__)


class AllowlistManager:
    """
    Manages the trading allowlist.

    The allowlist determines which bot/symbol/timeframe combinations
    are approved for live trading. It is updated based on walk-forward
    optimization results.
    """

    def __init__(
        self,
        config: AllowlistConfig | None = None,
        data_dir: Path | None = None,
    ):
        self.config = config or AllowlistConfig()
        settings = get_settings()
        self.data_dir = data_dir or settings.data_dir
        self.allowlist_path = self.data_dir / "allowlist.json"

        # In-memory allowlist
        self._entries: dict[str, AllowlistEntry] = {}
        self._last_update: datetime | None = None

        # Load existing allowlist
        self._load()

    def _load(self) -> None:
        """Load allowlist from disk."""
        if not self.allowlist_path.exists():
            logger.info("No existing allowlist found, starting fresh")
            return

        try:
            with open(self.allowlist_path) as f:
                data = json.load(f)

            self._entries = {}
            for entry_data in data.get("entries", []):
                entry = AllowlistEntry(**entry_data)
                self._entries[entry.combo_id] = entry

            last_update = data.get("last_update")
            if last_update:
                self._last_update = datetime.fromisoformat(last_update)

            logger.info(
                "Loaded allowlist with %d entries, last updated %s",
                len(self._entries),
                self._last_update,
            )

        except Exception as e:
            logger.warning("Failed to load allowlist: %s", e)

    def _save(self) -> None:
        """Save allowlist to disk."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "last_update": self._last_update.isoformat() if self._last_update else None,
                "entries": [entry.model_dump() for entry in self._entries.values()],
            }

            with open(self.allowlist_path, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug("Saved allowlist with %d entries", len(self._entries))

        except Exception as e:
            logger.error("Failed to save allowlist: %s", e)

    def get_all(self) -> list[AllowlistEntry]:
        """Get all allowlist entries."""
        return list(self._entries.values())

    def get_enabled(self) -> list[AllowlistEntry]:
        """Get only enabled entries."""
        return [e for e in self._entries.values() if e.enabled]

    def get_entry(self, combo_id: str) -> AllowlistEntry | None:
        """Get a specific entry by combo_id."""
        return self._entries.get(combo_id)

    def is_allowed(self, symbol: str, bot: str, timeframe: str) -> bool:
        """Check if a combo is allowed for trading."""
        combo_id = f"{symbol}:{bot}:{timeframe}"
        entry = self._entries.get(combo_id)

        if entry is None:
            return False

        if not entry.enabled:
            return False

        # Check staleness
        if entry.validated_at:
            age = datetime.now(UTC) - entry.validated_at
            if age.days > self.config.max_validation_age_days:
                logger.warning(
                    "Combo %s validation is stale (%d days old)",
                    combo_id,
                    age.days,
                )
                return False

        return True

    def add_entry(self, entry: AllowlistEntry) -> None:
        """Add or update an entry."""
        self._entries[entry.combo_id] = entry
        self._last_update = datetime.now(UTC)
        self._save()

    def remove_entry(self, combo_id: str) -> bool:
        """Remove an entry."""
        if combo_id in self._entries:
            del self._entries[combo_id]
            self._last_update = datetime.now(UTC)
            self._save()
            return True
        return False

    def enable(self, combo_id: str) -> bool:
        """Enable an entry."""
        if combo_id in self._entries:
            self._entries[combo_id].enabled = True
            self._save()
            return True
        return False

    def disable(self, combo_id: str, reason: str | None = None) -> bool:
        """Disable an entry."""
        if combo_id in self._entries:
            self._entries[combo_id].enabled = False
            self._entries[combo_id].reason = reason
            self._save()
            return True
        return False

    def update_from_walk_forward(
        self,
        result: WalkForwardResult,
        replace: bool = True,
    ) -> int:
        """
        Update allowlist from walk-forward optimization results.

        Args:
            result: Walk-forward result with recommended combos
            replace: If True, replace existing entries. If False, merge.

        Returns:
            Number of entries added/updated
        """
        if result.status != "completed":
            logger.warning("Cannot update allowlist from incomplete walk-forward run")
            return 0

        if not result.recommended_combos:
            logger.warning("No recommended combos in walk-forward result")
            return 0

        if replace:
            self._entries = {}

        added = 0
        now = datetime.now(UTC)

        for combo in result.recommended_combos:
            # Check diversification limits
            symbol = combo.get("symbol", "")
            bot = combo.get("bot", "")
            timeframe = combo.get("timeframe", "")

            if not symbol or not bot or not timeframe:
                continue

            # Count existing entries per symbol/bot
            symbol_count = sum(
                1 for e in self._entries.values()
                if e.symbol == symbol and e.enabled
            )
            bot_count = sum(
                1 for e in self._entries.values()
                if e.bot == bot and e.enabled
            )

            if symbol_count >= self.config.max_per_symbol:
                logger.debug(
                    "Skipping %s - symbol %s at max limit",
                    combo.get("combo_id"),
                    symbol,
                )
                continue

            if bot_count >= self.config.max_per_bot:
                logger.debug(
                    "Skipping %s - bot %s at max limit",
                    combo.get("combo_id"),
                    bot,
                )
                continue

            # Check quality filters
            avg_sharpe = combo.get("avg_sharpe", 0)
            total_trades = combo.get("total_trades", 0)
            avg_drawdown = combo.get("avg_drawdown_pct", 100)

            if avg_sharpe < self.config.min_sharpe:
                continue
            if total_trades < self.config.min_trades:
                continue
            if avg_drawdown > self.config.max_drawdown_pct:
                continue

            # Create entry
            entry = AllowlistEntry(
                symbol=symbol,
                bot=bot,
                timeframe=timeframe,
                sharpe=avg_sharpe,
                win_rate=combo.get("avg_win_rate"),
                max_drawdown_pct=avg_drawdown,
                total_trades=total_trades,
                source_run_id=result.run_id,
                validated_at=now,
                enabled=True,
            )

            self._entries[entry.combo_id] = entry
            added += 1

            # Check max combos
            if len(self._entries) >= self.config.max_combos:
                logger.info("Reached max_combos limit (%d)", self.config.max_combos)
                break

        self._last_update = now
        self._save()

        logger.info(
            "Updated allowlist from walk-forward %s: %d entries added/updated",
            result.run_id,
            added,
        )

        return added

    def get_status(self) -> dict[str, Any]:
        """Get allowlist status summary."""
        enabled = [e for e in self._entries.values() if e.enabled]
        stale_threshold = datetime.now(UTC) - timedelta(
            days=self.config.max_validation_age_days
        )
        stale = [
            e for e in enabled
            if e.validated_at and e.validated_at < stale_threshold
        ]

        # Group by symbol and bot
        by_symbol: dict[str, int] = {}
        by_bot: dict[str, int] = {}
        for e in enabled:
            by_symbol[e.symbol] = by_symbol.get(e.symbol, 0) + 1
            by_bot[e.bot] = by_bot.get(e.bot, 0) + 1

        return {
            "total_entries": len(self._entries),
            "enabled_entries": len(enabled),
            "stale_entries": len(stale),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "by_symbol": by_symbol,
            "by_bot": by_bot,
            "config": self.config.model_dump(),
        }

    def clear(self) -> None:
        """Clear all entries."""
        self._entries = {}
        self._last_update = datetime.now(UTC)
        self._save()
        logger.info("Allowlist cleared")
