"""
Combo Selector — selects diversified, robust combos from walk-forward results.

Pipeline: filter -> rank by consistency_score -> diversify (max_per_symbol/bot) -> explain
"""

from dataclasses import dataclass, field
from typing import Any

from solat_engine.logging import get_logger
from solat_engine.optimization.models import AllowlistEntry, WalkForwardResult

logger = get_logger(__name__)


@dataclass
class SelectionConstraints:
    """Constraints for combo selection."""

    max_combos: int = 15
    max_per_symbol: int = 3
    max_per_bot: int = 5
    min_oos_sharpe: float = 0.3
    min_oos_trades: int = 20
    min_folds_profitable_pct: float = 0.5
    max_sharpe_cv: float = 2.0


@dataclass
class SelectedCombo:
    """A combo selected by the selector with rationale."""

    symbol: str
    bot: str
    timeframe: str
    rank: int
    metrics: dict[str, Any]
    rationale: str


@dataclass
class SelectorResult:
    """Result of combo selection."""

    selected: list[SelectedCombo] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    constraints: SelectionConstraints = field(default_factory=SelectionConstraints)


class ComboSelector:
    """
    Selects the best combos from walk-forward results.

    Pipeline:
    1. Filter by min sharpe, min trades, min folds profitable, max sharpe CV
    2. Rank by consistency_score (sharpe / sharpe_std)
    3. Diversify: enforce max_per_symbol and max_per_bot
    4. Explain: generate rationale string for each selected combo
    """

    def select(
        self,
        wfo_result: WalkForwardResult,
        constraints: SelectionConstraints | None = None,
    ) -> SelectorResult:
        """
        Select combos from walk-forward results.

        Args:
            wfo_result: Completed walk-forward result
            constraints: Selection constraints (uses defaults if None)

        Returns:
            SelectorResult with selected and rejected combos
        """
        constraints = constraints or SelectionConstraints()
        result = SelectorResult(constraints=constraints)

        if not wfo_result.recommended_combos:
            return result

        # Step 1: Filter
        candidates = []
        for combo in wfo_result.recommended_combos:
            avg_sharpe = combo.get("avg_sharpe", 0)
            total_trades = combo.get("total_trades", 0)
            folds_profitable_pct = combo.get("folds_profitable_pct", 0)
            sharpe_cv = combo.get("sharpe_cv", float("inf"))

            reasons = []
            if avg_sharpe < constraints.min_oos_sharpe:
                reasons.append(f"sharpe {avg_sharpe:.2f} < {constraints.min_oos_sharpe}")
            if total_trades < constraints.min_oos_trades:
                reasons.append(f"trades {total_trades} < {constraints.min_oos_trades}")
            if folds_profitable_pct < constraints.min_folds_profitable_pct:
                reasons.append(
                    f"folds_profitable {folds_profitable_pct:.0%} < "
                    f"{constraints.min_folds_profitable_pct:.0%}"
                )
            if sharpe_cv > constraints.max_sharpe_cv:
                reasons.append(f"sharpe_cv {sharpe_cv:.2f} > {constraints.max_sharpe_cv}")

            if reasons:
                result.rejected.append({
                    **combo,
                    "rejection_reasons": reasons,
                })
            else:
                candidates.append(combo)

        # Step 2: Rank by consistency_score
        candidates.sort(
            key=lambda c: c.get("consistency_score", 0), reverse=True
        )

        # Step 3: Diversify
        symbol_counts: dict[str, int] = {}
        bot_counts: dict[str, int] = {}
        rank = 0

        for combo in candidates:
            symbol = combo.get("symbol", "")
            bot = combo.get("bot", "")

            # Check diversification limits
            if symbol_counts.get(symbol, 0) >= constraints.max_per_symbol:
                result.rejected.append({
                    **combo,
                    "rejection_reasons": [
                        f"symbol {symbol} at max ({constraints.max_per_symbol})"
                    ],
                })
                continue

            if bot_counts.get(bot, 0) >= constraints.max_per_bot:
                result.rejected.append({
                    **combo,
                    "rejection_reasons": [
                        f"bot {bot} at max ({constraints.max_per_bot})"
                    ],
                })
                continue

            if len(result.selected) >= constraints.max_combos:
                result.rejected.append({
                    **combo,
                    "rejection_reasons": [
                        f"max_combos limit ({constraints.max_combos}) reached"
                    ],
                })
                continue

            # Select this combo
            rank += 1
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            bot_counts[bot] = bot_counts.get(bot, 0) + 1

            # Step 4: Generate rationale
            rationale = self._build_rationale(combo, rank)

            result.selected.append(SelectedCombo(
                symbol=symbol,
                bot=bot,
                timeframe=combo.get("timeframe", ""),
                rank=rank,
                metrics={
                    "avg_sharpe": combo.get("avg_sharpe", 0),
                    "avg_win_rate": combo.get("avg_win_rate", 0),
                    "avg_return_pct": combo.get("avg_return_pct", 0),
                    "total_trades": combo.get("total_trades", 0),
                    "sharpe_cv": combo.get("sharpe_cv", 0),
                    "folds_profitable_pct": combo.get("folds_profitable_pct", 0),
                    "consistency_score": combo.get("consistency_score", 0),
                    "windows_count": combo.get("windows_count", 0),
                },
                rationale=rationale,
            ))

        logger.info(
            "Selector: %d selected, %d rejected from %d candidates",
            len(result.selected),
            len(result.rejected),
            len(wfo_result.recommended_combos),
        )

        return result

    def _build_rationale(self, combo: dict[str, Any], rank: int) -> str:
        """Build a human-readable rationale for selection."""
        avg_sharpe = combo.get("avg_sharpe", 0)
        folds_pct = combo.get("folds_profitable_pct", 0)
        sharpe_cv = combo.get("sharpe_cv", 0)
        consistency = combo.get("consistency_score", 0)
        total_trades = combo.get("total_trades", 0)
        windows = combo.get("windows_count", 0)

        return (
            f"Rank #{rank}: OOS Sharpe={avg_sharpe:.2f} across {windows} folds, "
            f"{folds_pct:.0%} profitable, CV={sharpe_cv:.2f}, "
            f"consistency={consistency:.2f}, {total_trades} trades"
        )

    def to_allowlist_entries(
        self, selected: list[SelectedCombo], run_id: str
    ) -> list[AllowlistEntry]:
        """Convert selected combos to AllowlistEntry list."""
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        entries = []
        for combo in selected:
            entries.append(AllowlistEntry(
                symbol=combo.symbol,
                bot=combo.bot,
                timeframe=combo.timeframe,
                sharpe=combo.metrics.get("avg_sharpe"),
                win_rate=combo.metrics.get("avg_win_rate"),
                total_trades=combo.metrics.get("total_trades", 0),
                source_run_id=run_id,
                validated_at=now,
                enabled=True,
            ))
        return entries
