"""
Execution Ledger for audit logging.

Append-only log of all execution events:
- Intents created
- Orders submitted
- Acknowledgments received
- Errors
- Reconciliation events
- Kill switch events
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd

from solat_engine.execution.models import (
    ExecutionConfig,
    LedgerEntry,
    OrderAck,
    OrderIntent,
    OrderStatus,
    PositionSnapshot,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that handles UUIDs and datetimes."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class ExecutionLedger:
    """
    Append-only execution ledger.

    Writes to:
    - {run_dir}/ledger.jsonl (JSON lines format)
    - {run_dir}/positions_snapshots.parquet (periodic snapshots)
    """

    def __init__(
        self,
        base_dir: Path,
        config: ExecutionConfig,
        run_id: str | None = None,
    ):
        """
        Initialize execution ledger.

        Args:
            base_dir: Base directory for runs (e.g., data/runs)
            config: Execution configuration
            run_id: Optional run ID (generated if not provided)
        """
        self._base_dir = base_dir
        self._config = config

        # Generate run ID if not provided
        if run_id is None:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            run_id = f"live_{ts}_{config.mode.value.lower()}"
        self._run_id = run_id

        # Create run directory
        self._run_dir = base_dir / "runs" / run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)

        # Ledger file
        self._ledger_path = self._run_dir / "ledger.jsonl"

        # Position snapshots
        self._snapshots: list[PositionSnapshot] = []
        self._snapshots_path = self._run_dir / "positions_snapshots.parquet"

        # Write manifest
        self._write_manifest(config)

        logger.info("Execution ledger initialized: %s", self._run_dir)

    @property
    def run_id(self) -> str:
        """Get run ID."""
        return self._run_id

    @property
    def run_dir(self) -> Path:
        """Get run directory."""
        return self._run_dir

    def _write_manifest(self, config: ExecutionConfig) -> None:
        """Write manifest.json with run configuration."""
        manifest = {
            "run_id": self._run_id,
            "mode": config.mode.value,
            "started_at": datetime.now(UTC).isoformat(),
            "config": {
                "max_position_size": config.max_position_size,
                "max_concurrent_positions": config.max_concurrent_positions,
                "max_daily_loss_pct": config.max_daily_loss_pct,
                "max_trades_per_hour": config.max_trades_per_hour,
                "per_symbol_exposure_cap": config.per_symbol_exposure_cap,
                "require_sl": config.require_sl,
                "close_on_kill_switch": config.close_on_kill_switch,
            },
        }

        manifest_path = self._run_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def _append_entry(self, entry: LedgerEntry) -> None:
        """Append entry to ledger file."""
        with open(self._ledger_path, "a") as f:
            f.write(entry.model_dump_json() + "\n")

    def record_intent(self, intent: OrderIntent) -> None:
        """Record an order intent creation."""
        entry = LedgerEntry(
            entry_type="intent",
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            side=intent.side,
            size=intent.size,
            reason_codes=intent.reason_codes,
            metadata={
                "bot": intent.bot,
                "order_type": intent.order_type.value,
                "stop_loss": intent.stop_loss,
                "take_profit": intent.take_profit,
                "confidence": intent.confidence,
            },
        )
        self._append_entry(entry)
        logger.debug("Ledger: intent %s for %s", intent.intent_id, intent.symbol)

    def record_submission(
        self,
        intent: OrderIntent,
        deal_reference: str,
    ) -> None:
        """Record order submission to broker."""
        entry = LedgerEntry(
            entry_type="submission",
            intent_id=intent.intent_id,
            deal_reference=deal_reference,
            symbol=intent.symbol,
            side=intent.side,
            size=intent.size,
            status=OrderStatus.SUBMITTED,
        )
        self._append_entry(entry)
        logger.debug("Ledger: submitted %s ref=%s", intent.intent_id, deal_reference)

    def record_ack(self, ack: OrderAck) -> None:
        """Record broker acknowledgment."""
        entry = LedgerEntry(
            entry_type="ack",
            intent_id=ack.intent_id,
            deal_reference=ack.deal_reference,
            deal_id=ack.deal_id,
            status=ack.status,
            metadata={
                "filled_size": ack.filled_size,
                "filled_price": ack.filled_price,
            },
        )
        self._append_entry(entry)
        logger.debug(
            "Ledger: ack %s status=%s deal=%s",
            ack.intent_id,
            ack.status.value,
            ack.deal_id,
        )

    def record_rejection(
        self,
        intent: OrderIntent,
        reason: str,
        reason_codes: list[str],
    ) -> None:
        """Record order rejection (by risk engine or broker)."""
        entry = LedgerEntry(
            entry_type="rejection",
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            side=intent.side,
            size=intent.size,
            status=OrderStatus.REJECTED,
            reason_codes=reason_codes,
            error=reason,
        )
        self._append_entry(entry)
        logger.debug("Ledger: rejected %s: %s", intent.intent_id, reason)

    def record_error(
        self,
        error: str,
        intent_id: UUID | None = None,
        deal_reference: str | None = None,
    ) -> None:
        """Record an error."""
        entry = LedgerEntry(
            entry_type="error",
            intent_id=intent_id,
            deal_reference=deal_reference,
            error=error,
        )
        self._append_entry(entry)
        logger.error("Ledger: error %s", error)

    def record_reconciliation(
        self,
        broker_count: int,
        local_count: int,
        drift_detected: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record reconciliation result."""
        entry = LedgerEntry(
            entry_type="reconciliation",
            metadata={
                "broker_count": broker_count,
                "local_count": local_count,
                "drift_detected": drift_detected,
                **(details or {}),
            },
        )
        self._append_entry(entry)

    def record_kill_switch(
        self,
        activated: bool,
        reason: str | None = None,
        by: str | None = None,
    ) -> None:
        """Record kill switch event."""
        entry = LedgerEntry(
            entry_type="kill_switch",
            metadata={
                "activated": activated,
                "reason": reason,
                "by": by,
            },
        )
        self._append_entry(entry)
        logger.warning(
            "Ledger: kill_switch %s by %s: %s",
            "activated" if activated else "reset",
            by,
            reason,
        )

    def record_position_snapshot(self, snapshot: PositionSnapshot) -> None:
        """Record position snapshot."""
        self._snapshots.append(snapshot)

        # Write to parquet periodically (every 10 snapshots)
        if len(self._snapshots) % 10 == 0:
            self._flush_snapshots()

    def _flush_snapshots(self) -> None:
        """Write accumulated snapshots to parquet."""
        if not self._snapshots:
            return

        records = []
        for snap in self._snapshots:
            for pos in snap.positions:
                records.append({
                    "snapshot_ts": snap.timestamp,
                    "deal_id": pos.deal_id,
                    "epic": pos.epic,
                    "symbol": pos.symbol,
                    "direction": pos.direction.value,
                    "size": pos.size,
                    "open_level": pos.open_level,
                    "current_level": pos.current_level,
                    "unrealized_pnl": pos.unrealized_pnl,
                })

        if records:
            df = pd.DataFrame(records)
            df.to_parquet(self._snapshots_path, index=False)

    def finalize(self) -> None:
        """Finalize ledger (flush pending data)."""
        self._flush_snapshots()

        # Update manifest with end time
        manifest_path = self._run_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            manifest["ended_at"] = datetime.now(UTC).isoformat()
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

        logger.info("Execution ledger finalized: %s", self._run_dir)

    def get_entries(self, entry_type: str | None = None) -> list[LedgerEntry]:
        """Read ledger entries (for testing/debugging)."""
        if not self._ledger_path.exists():
            return []

        entries = []
        with open(self._ledger_path) as f:
            for line in f:
                if line.strip():
                    entry = LedgerEntry.model_validate_json(line)
                    if entry_type is None or entry.entry_type == entry_type:
                        entries.append(entry)
        return entries
