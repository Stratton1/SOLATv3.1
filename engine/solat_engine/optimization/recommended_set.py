"""
RecommendedSet — persisted recommendation from WFO selector.

Stores selected combos with criteria, supports apply-to-demo workflow
that writes entries to the AllowlistManager.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from solat_engine.config import TradingMode, get_settings
from solat_engine.logging import get_logger
from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.optimization.models import WalkForwardResult
from solat_engine.optimization.selector import (
    ComboSelector,
    SelectedCombo,
    SelectionConstraints,
    SelectorResult,
)
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus

logger = get_logger(__name__)


class RecommendedSet(BaseModel):
    """A persisted recommendation set from WFO selector."""

    id: str = Field(default_factory=lambda: f"recset-{uuid.uuid4().hex[:8]}")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    criteria: dict[str, Any] = Field(default_factory=dict)
    combos: list[dict[str, Any]] = Field(default_factory=list)
    rejected_count: int = 0
    source_run_ids: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending | applied | superseded
    applied_at: datetime | None = None


class RecommendedSetManager:
    """
    Manages recommended sets — generate, persist, list, and apply to demo.

    Stores JSON files under data/optimization/recommendations/.
    """

    def __init__(self, data_dir: Path | None = None):
        settings = get_settings()
        base = data_dir or settings.data_dir
        self._dir = base / "optimization" / "recommendations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, RecommendedSet] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all recommendation sets from disk."""
        for path in sorted(self._dir.glob("recset-*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)
                rs = RecommendedSet(**data)
                self._cache[rs.id] = rs
            except Exception as e:
                logger.warning("Failed to load recommendation %s: %s", path.name, e)

    def _save(self, rs: RecommendedSet) -> None:
        """Save a recommendation set to disk."""
        path = self._dir / f"{rs.id}.json"
        with open(path, "w") as f:
            json.dump(rs.model_dump(mode="json"), f, indent=2, default=str)

    def generate(
        self,
        wfo_results: list[WalkForwardResult],
        constraints: SelectionConstraints | None = None,
    ) -> RecommendedSet:
        """
        Generate a recommended set from one or more WFO results.

        Runs ComboSelector.select() on each result and merges.
        """
        constraints = constraints or SelectionConstraints()
        selector = ComboSelector()
        all_selected: list[SelectedCombo] = []
        total_rejected = 0
        source_run_ids: list[str] = []

        for result in wfo_results:
            if result.status != "completed":
                continue
            source_run_ids.append(result.run_id)
            sel_result: SelectorResult = selector.select(result, constraints)
            all_selected.extend(sel_result.selected)
            total_rejected += len(sel_result.rejected)

        # De-duplicate by (symbol, bot, timeframe), keep highest rank
        seen: dict[str, SelectedCombo] = {}
        for combo in all_selected:
            key = f"{combo.symbol}:{combo.bot}:{combo.timeframe}"
            if key not in seen or combo.rank < seen[key].rank:
                seen[key] = combo

        combos_dicts = [
            {
                "symbol": c.symbol,
                "bot": c.bot,
                "timeframe": c.timeframe,
                "rank": c.rank,
                "metrics": c.metrics,
                "rationale": c.rationale,
            }
            for c in sorted(seen.values(), key=lambda c: c.rank)
        ]

        rs = RecommendedSet(
            criteria={
                "max_combos": constraints.max_combos,
                "max_per_symbol": constraints.max_per_symbol,
                "max_per_bot": constraints.max_per_bot,
                "min_oos_sharpe": constraints.min_oos_sharpe,
                "min_oos_trades": constraints.min_oos_trades,
                "min_folds_profitable_pct": constraints.min_folds_profitable_pct,
                "max_sharpe_cv": constraints.max_sharpe_cv,
            },
            combos=combos_dicts,
            rejected_count=total_rejected,
            source_run_ids=source_run_ids,
        )

        self._cache[rs.id] = rs
        self._save(rs)

        logger.info(
            "Generated recommendation %s: %d combos from %d WFO runs",
            rs.id,
            len(rs.combos),
            len(source_run_ids),
        )

        return rs

    def get(self, rec_id: str) -> RecommendedSet | None:
        """Get a recommendation set by ID."""
        return self._cache.get(rec_id)

    def get_latest(self) -> RecommendedSet | None:
        """Get the most recently generated recommendation set."""
        if not self._cache:
            return None
        return max(self._cache.values(), key=lambda r: r.generated_at)

    def list_all(self) -> list[RecommendedSet]:
        """List all recommendation sets, newest first."""
        return sorted(self._cache.values(), key=lambda r: r.generated_at, reverse=True)

    async def apply_to_demo(
        self,
        rec_id: str,
        allowlist_mgr: AllowlistManager,
        settings: Any,
    ) -> RecommendedSet | None:
        """
        Apply a recommendation set to the allowlist (DEMO only).

        Checks settings.mode != LIVE (fail-closed), writes entries,
        marks previous applied sets as superseded, emits event.
        """
        rs = self._cache.get(rec_id)
        if rs is None:
            return None

        # LIVE fail-closed check
        mode = getattr(settings, "mode", None)
        if mode == TradingMode.LIVE:
            raise PermissionError("Cannot apply recommendations in LIVE mode")

        # Mark any previously applied set as superseded
        for other in self._cache.values():
            if other.id != rec_id and other.status == "applied":
                other.status = "superseded"
                self._save(other)

        # Write each combo to allowlist
        from solat_engine.optimization.models import AllowlistEntry

        now = datetime.now(UTC)
        for combo in rs.combos:
            entry = AllowlistEntry(
                symbol=combo["symbol"],
                bot=combo["bot"],
                timeframe=combo["timeframe"],
                sharpe=combo.get("metrics", {}).get("avg_sharpe"),
                win_rate=combo.get("metrics", {}).get("avg_win_rate"),
                total_trades=combo.get("metrics", {}).get("total_trades", 0),
                source_run_id=rs.source_run_ids[0] if rs.source_run_ids else None,
                validated_at=now,
                enabled=True,
            )
            allowlist_mgr.add_entry(entry)

        rs.status = "applied"
        rs.applied_at = now
        self._save(rs)

        # Emit event
        event_bus = get_event_bus()
        await event_bus.publish(Event(
            type=EventType.RECOMMENDATION_APPLIED,
            data={
                "recommendation_id": rs.id,
                "combos_count": len(rs.combos),
            },
        ))

        logger.info(
            "Applied recommendation %s: %d combos written to allowlist",
            rs.id,
            len(rs.combos),
        )

        return rs
