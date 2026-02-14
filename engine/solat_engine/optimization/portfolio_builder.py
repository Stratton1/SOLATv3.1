"""
Diversified portfolio builder with risk constraints.

Takes scored combos (baseline + tuned variants) and builds a 15-25 slot portfolio
respecting symbol, bot-family, timeframe, and currency exposure caps.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from solat_engine.optimization.models import AllowlistEntry
from solat_engine.optimization.scoring import ComboScore


# ============================================================================
# Currency Exposure Mapping
# ============================================================================

FX_CURRENCY_EXPOSURE: dict[str, tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"), "AUDUSD": ("AUD", "USD"), "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"), "EURGBP": ("EUR", "GBP"), "EURJPY": ("EUR", "JPY"),
    "GBPJPY": ("GBP", "JPY"), "EURAUD": ("EUR", "AUD"), "EURCAD": ("EUR", "CAD"),
    "EURCHF": ("EUR", "CHF"), "EURNZD": ("EUR", "NZD"),
    "GBPAUD": ("GBP", "AUD"), "GBPCAD": ("GBP", "CAD"),
    "GBPCHF": ("GBP", "CHF"), "GBPNZD": ("GBP", "NZD"),
    "AUDJPY": ("AUD", "JPY"), "AUDNZD": ("AUD", "NZD"),
    "AUDCAD": ("AUD", "CAD"), "AUDCHF": ("AUD", "CHF"),
    "NZDJPY": ("NZD", "JPY"), "NZDCAD": ("NZD", "CAD"), "NZDCHF": ("NZD", "CHF"),
    "CADJPY": ("CAD", "JPY"), "CADCHF": ("CAD", "CHF"), "CHFJPY": ("CHF", "JPY"),
}


def _get_currencies(symbol: str) -> list[str]:
    """Get currency exposure for a symbol. Non-FX symbols return empty."""
    pair = FX_CURRENCY_EXPOSURE.get(symbol.upper())
    if pair:
        return list(pair)
    return []


def _get_bot_family(bot: str, variant_id: str) -> str:
    """Get bot family name (strips variant suffix)."""
    # All variants of CloudTwist (baseline, tunedA, tunedB) = same family
    return bot


# ============================================================================
# Data Models
# ============================================================================


@dataclass(frozen=True)
class PortfolioConstraints:
    """Constraints for portfolio construction."""

    max_slots: int = 25
    min_slots: int = 15
    max_per_symbol: int = 2
    max_per_timeframe: int = 10
    max_per_bot_family: int = 6
    max_per_currency: int = 8
    risk_per_trade_pct: float = 1.0
    max_concurrent_risk_pct: float = 10.0
    min_score: float = 40.0


@dataclass
class PortfolioSlot:
    """A single slot in the portfolio."""

    rank: int
    bot: str
    symbol: str
    timeframe: str
    variant_id: str
    params_override: dict[str, Any]
    score_total: float
    risk_per_trade_pct: float
    oos_sharpe: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int

    @property
    def combo_id(self) -> str:
        base = f"{self.symbol}:{self.bot}:{self.timeframe}"
        if self.variant_id != "baseline":
            return f"{base}:{self.variant_id}"
        return base


@dataclass
class PortfolioResult:
    """Result of portfolio construction."""

    slots: list[PortfolioSlot] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    constraints: PortfolioConstraints = field(default_factory=PortfolioConstraints)
    avg_score: float = 0.0
    total_slots: int = 0
    currency_distribution: dict[str, int] = field(default_factory=dict)
    bot_distribution: dict[str, int] = field(default_factory=dict)
    timeframe_distribution: dict[str, int] = field(default_factory=dict)
    symbol_distribution: dict[str, int] = field(default_factory=dict)


# ============================================================================
# Portfolio Builder
# ============================================================================


class PortfolioBuilder:
    """Build diversified portfolio from scored combos."""

    def build(
        self,
        scored_combos: list[ComboScore],
        constraints: PortfolioConstraints | None = None,
    ) -> PortfolioResult:
        """
        Build portfolio by greedy fill in score order, checking constraints.

        Algorithm:
        1. Filter out rejected combos and those below min_score
        2. Sort by score descending
        3. Greedily add, checking each constraint:
           - max_per_symbol
           - max_per_bot_family
           - max_per_timeframe
           - max_per_currency
           - max_slots
        4. Stop when max_slots reached or no more candidates
        """
        c = constraints or PortfolioConstraints()

        # Filter and sort
        candidates = [
            s for s in scored_combos
            if not s.rejected and s.score_total >= c.min_score
        ]
        candidates.sort(key=lambda s: s.score_total, reverse=True)

        # Tracking counters
        symbol_count: dict[str, int] = {}
        bot_family_count: dict[str, int] = {}
        timeframe_count: dict[str, int] = {}
        currency_count: dict[str, int] = {}

        slots: list[PortfolioSlot] = []
        rejected: list[dict[str, Any]] = []

        for combo in candidates:
            if len(slots) >= c.max_slots:
                break

            family = _get_bot_family(combo.bot, combo.variant_id)
            currencies = _get_currencies(combo.symbol)

            # Check symbol cap
            if symbol_count.get(combo.symbol, 0) >= c.max_per_symbol:
                rejected.append({
                    "combo_id": combo.combo_id,
                    "score": combo.score_total,
                    "reason": f"symbol cap ({c.max_per_symbol})",
                })
                continue

            # Check bot family cap
            if bot_family_count.get(family, 0) >= c.max_per_bot_family:
                rejected.append({
                    "combo_id": combo.combo_id,
                    "score": combo.score_total,
                    "reason": f"bot family cap ({c.max_per_bot_family})",
                })
                continue

            # Check timeframe cap
            if timeframe_count.get(combo.timeframe, 0) >= c.max_per_timeframe:
                rejected.append({
                    "combo_id": combo.combo_id,
                    "score": combo.score_total,
                    "reason": f"timeframe cap ({c.max_per_timeframe})",
                })
                continue

            # Check currency cap
            currency_blocked = False
            for cur in currencies:
                if currency_count.get(cur, 0) >= c.max_per_currency:
                    rejected.append({
                        "combo_id": combo.combo_id,
                        "score": combo.score_total,
                        "reason": f"currency cap {cur} ({c.max_per_currency})",
                    })
                    currency_blocked = True
                    break
            if currency_blocked:
                continue

            # Add slot
            slot = PortfolioSlot(
                rank=len(slots) + 1,
                bot=combo.bot,
                symbol=combo.symbol,
                timeframe=combo.timeframe,
                variant_id=combo.variant_id,
                params_override=combo.params_override,
                score_total=combo.score_total,
                risk_per_trade_pct=c.risk_per_trade_pct,
                oos_sharpe=combo.oos_sharpe,
                max_drawdown_pct=combo.max_drawdown_pct,
                win_rate=combo.win_rate,
                total_trades=combo.total_trades,
            )
            slots.append(slot)

            # Update counters
            symbol_count[combo.symbol] = symbol_count.get(combo.symbol, 0) + 1
            bot_family_count[family] = bot_family_count.get(family, 0) + 1
            timeframe_count[combo.timeframe] = timeframe_count.get(combo.timeframe, 0) + 1
            for cur in currencies:
                currency_count[cur] = currency_count.get(cur, 0) + 1

        # Compute result stats
        avg_score = sum(s.score_total for s in slots) / len(slots) if slots else 0.0

        return PortfolioResult(
            slots=slots,
            rejected=rejected,
            constraints=c,
            avg_score=round(avg_score, 2),
            total_slots=len(slots),
            currency_distribution=dict(currency_count),
            bot_distribution=dict(bot_family_count),
            timeframe_distribution=dict(timeframe_count),
            symbol_distribution=dict(symbol_count),
        )

    def to_allowlist(self, result: PortfolioResult) -> list[AllowlistEntry]:
        """Convert portfolio result to allowlist entries."""
        entries = []
        for slot in result.slots:
            entries.append(AllowlistEntry(
                symbol=slot.symbol,
                bot=slot.bot,
                timeframe=slot.timeframe,
                sharpe=slot.oos_sharpe,
                win_rate=slot.win_rate,
                max_drawdown_pct=slot.max_drawdown_pct,
                total_trades=slot.total_trades,
                enabled=True,
                variant_id=slot.variant_id,
                params_override=slot.params_override,
                score_total=slot.score_total,
                validated_at=datetime.now(UTC),
            ))
        return entries

    def to_markdown_report(self, result: PortfolioResult) -> str:
        """Generate human-readable markdown portfolio report."""
        lines = [
            "# Portfolio Report",
            "",
            f"**Total Slots:** {result.total_slots}",
            f"**Average Score:** {result.avg_score:.1f}",
            f"**Risk/Trade:** {result.constraints.risk_per_trade_pct:.1f}%",
            f"**Max Concurrent Risk:** {result.constraints.max_concurrent_risk_pct:.1f}%",
            "",
            "## Slots",
            "",
            "| Rank | Bot | Symbol | TF | Variant | Score | Sharpe | DD% | WR% | Trades |",
            "|------|-----|--------|----|---------|-------|--------|-----|-----|--------|",
        ]

        for s in result.slots:
            lines.append(
                f"| {s.rank} | {s.bot} | {s.symbol} | {s.timeframe} | "
                f"{s.variant_id} | {s.score_total:.1f} | {s.oos_sharpe:.2f} | "
                f"{s.max_drawdown_pct:.1f} | {s.win_rate:.0%} | {s.total_trades} |"
            )

        lines.extend([
            "",
            "## Distribution",
            "",
            f"**Symbols:** {result.symbol_distribution}",
            f"**Bots:** {result.bot_distribution}",
            f"**Timeframes:** {result.timeframe_distribution}",
            f"**Currencies:** {result.currency_distribution}",
        ])

        if result.rejected:
            lines.extend([
                "",
                f"## Rejected ({len(result.rejected)} combos)",
                "",
            ])
            for r in result.rejected[:10]:
                lines.append(f"- {r['combo_id']} (score={r['score']:.1f}): {r['reason']}")
            if len(result.rejected) > 10:
                lines.append(f"- ... and {len(result.rejected) - 10} more")

        return "\n".join(lines)
