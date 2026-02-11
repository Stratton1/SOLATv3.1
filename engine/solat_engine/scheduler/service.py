"""
Scheduler Service — periodic optimization jobs and proposal management.

Jobs:
- nightly_data_check: Verify data freshness (every 24h)
- weekly_optimize: Run walk-forward + selector (every 168h)

Proposals:
- Never auto-applied. All proposals require explicit human POST.
- Persisted as JSON in data/proposals/
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from solat_engine.config import TradingMode, get_settings
from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JobStatus:
    """Status of a scheduled job."""

    name: str
    interval_hours: int
    last_run: datetime | None = None
    next_run: datetime | None = None
    running: bool = False
    run_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interval_hours": self.interval_hours,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "running": self.running,
            "run_count": self.run_count,
            "last_error": self.last_error,
        }


@dataclass
class Proposal:
    """A proposal to update the trading allowlist."""

    proposal_id: str
    created_at: datetime
    status: str = "pending"  # pending, applied, rejected, expired
    selected_combos: list[dict[str, Any]] = field(default_factory=list)
    wfo_run_id: str | None = None
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "selected_combos": self.selected_combos,
            "wfo_run_id": self.wfo_run_id,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Proposal":
        return cls(
            proposal_id=d["proposal_id"],
            created_at=datetime.fromisoformat(d["created_at"]),
            status=d.get("status", "pending"),
            selected_combos=d.get("selected_combos", []),
            wfo_run_id=d.get("wfo_run_id"),
            applied_at=(
                datetime.fromisoformat(d["applied_at"]) if d.get("applied_at") else None
            ),
            rejected_at=(
                datetime.fromisoformat(d["rejected_at"]) if d.get("rejected_at") else None
            ),
            message=d.get("message", ""),
        )


class SchedulerService:
    """
    Minimal scheduler for periodic optimization jobs.

    Runs a 60s check loop. Jobs are checked against their interval.
    Proposals are persisted as JSON files.
    """

    def __init__(self, data_dir: Path | None = None):
        settings = get_settings()
        self.data_dir = data_dir or settings.data_dir
        self.proposals_dir = self.data_dir / "proposals"
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

        self._task: asyncio.Task | None = None
        self._running = False

        # Job definitions
        self.jobs: dict[str, JobStatus] = {
            "nightly_data_check": JobStatus(
                name="nightly_data_check",
                interval_hours=24,
            ),
            "weekly_optimize": JobStatus(
                name="weekly_optimize",
                interval_hours=168,
            ),
        }

        # In-memory proposal cache
        self._proposals: dict[str, Proposal] = {}
        self._load_proposals()

    def _load_proposals(self) -> None:
        """Load proposals from disk."""
        for f in self.proposals_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                p = Proposal.from_dict(data)
                self._proposals[p.proposal_id] = p
            except Exception as e:
                logger.warning("Failed to load proposal %s: %s", f, e)

    def _save_proposal(self, proposal: Proposal) -> None:
        """Save a proposal to disk."""
        path = self.proposals_dir / f"{proposal.proposal_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(proposal.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save proposal %s: %s", proposal.proposal_id, e)

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduler loop — checks jobs every 60s."""
        # Initialize next_run times
        now = datetime.now(UTC)
        for job in self.jobs.values():
            if job.next_run is None:
                job.next_run = now + timedelta(hours=job.interval_hours)

        while self._running:
            try:
                await asyncio.sleep(60)
                now = datetime.now(UTC)

                for job in self.jobs.values():
                    if job.next_run and now >= job.next_run and not job.running:
                        await self._run_job(job)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)

    async def _run_job(self, job: JobStatus) -> None:
        """Run a scheduled job (stub — logs only)."""
        job.running = True
        job.last_run = datetime.now(UTC)
        job.run_count += 1
        logger.info("Running scheduled job: %s (run #%d)", job.name, job.run_count)

        try:
            if job.name == "nightly_data_check":
                await self._job_nightly_data_check()
            elif job.name == "weekly_optimize":
                await self._job_weekly_optimize()

            job.last_error = None
        except Exception as e:
            job.last_error = str(e)[:200]
            logger.error("Job %s failed: %s", job.name, e)
        finally:
            job.running = False
            job.next_run = datetime.now(UTC) + timedelta(hours=job.interval_hours)

    async def _job_nightly_data_check(self) -> None:
        """Check data freshness — stub for now."""
        logger.info("Nightly data check: checking data freshness...")
        # Future: verify parquet data is up to date, trigger sync if stale

    async def _job_weekly_optimize(self) -> None:
        """Run walk-forward + selector — stub for now."""
        logger.info("Weekly optimize: would run walk-forward + selector...")
        # Future: auto-run WFO, create proposal from results

    # =========================================================================
    # Proposal CRUD
    # =========================================================================

    def create_proposal(
        self,
        selected_combos: list[dict[str, Any]],
        wfo_run_id: str | None = None,
        message: str = "",
    ) -> Proposal:
        """Create a new proposal."""
        proposal = Proposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:8]}",
            created_at=datetime.now(UTC),
            selected_combos=selected_combos,
            wfo_run_id=wfo_run_id,
            message=message,
        )
        self._proposals[proposal.proposal_id] = proposal
        self._save_proposal(proposal)
        logger.info("Created proposal %s with %d combos", proposal.proposal_id, len(selected_combos))
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def list_proposals(self) -> list[Proposal]:
        """List all proposals, newest first."""
        return sorted(
            self._proposals.values(),
            key=lambda p: p.created_at,
            reverse=True,
        )

    def apply_proposal(self, proposal_id: str) -> Proposal | None:
        """
        Apply a proposal to the allowlist.

        Safety: Only allowed in DEMO mode. Blocked in LIVE.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return None

        if proposal.status != "pending":
            logger.warning("Cannot apply proposal %s (status: %s)", proposal_id, proposal.status)
            return proposal

        # Safety check: block in LIVE mode
        settings = get_settings()
        if settings.mode == TradingMode.LIVE:
            logger.error("Cannot apply proposals in LIVE mode")
            proposal.status = "rejected"
            proposal.rejected_at = datetime.now(UTC)
            proposal.message = "Blocked: LIVE mode"
            self._save_proposal(proposal)
            return proposal

        # Apply to allowlist
        from solat_engine.optimization.allowlist import AllowlistManager
        from solat_engine.optimization.models import AllowlistEntry

        manager = AllowlistManager()
        now = datetime.now(UTC)

        for combo in proposal.selected_combos:
            entry = AllowlistEntry(
                symbol=combo.get("symbol", ""),
                bot=combo.get("bot", ""),
                timeframe=combo.get("timeframe", ""),
                sharpe=combo.get("metrics", {}).get("avg_sharpe"),
                win_rate=combo.get("metrics", {}).get("avg_win_rate"),
                total_trades=combo.get("metrics", {}).get("total_trades", 0),
                source_run_id=proposal.wfo_run_id,
                validated_at=now,
                enabled=True,
            )
            manager.add_entry(entry)

        proposal.status = "applied"
        proposal.applied_at = now
        proposal.message = f"Applied {len(proposal.selected_combos)} combos to allowlist"
        self._save_proposal(proposal)

        logger.info(
            "Applied proposal %s: %d combos",
            proposal_id, len(proposal.selected_combos),
        )
        return proposal

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "jobs": {name: job.to_dict() for name, job in self.jobs.items()},
            "proposals_count": len(self._proposals),
            "pending_proposals": sum(
                1 for p in self._proposals.values() if p.status == "pending"
            ),
        }
