"""
Scoring system for strategy combos.

Implements hard gates + weighted 0-100 scoring with stability penalties.
Used to rank baseline and tuned variants for portfolio selection.
"""

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HardGates:
    """Hard rejection thresholds. Failing any gate = rejected."""

    max_drawdown_pct: float = 20.0
    min_trades_sweep: int = 30
    min_trades_oos: int = 10
    min_exposure_pct: float = 1.0
    max_exposure_pct: float = 90.0
    min_folds_profitable_pct: float = 0.50


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for composite score components. Must sum to 1.0."""

    oos_sharpe: float = 0.45
    oos_return: float = 0.20
    drawdown: float = 0.25
    trade_confidence: float = 0.10


@dataclass
class ComboScore:
    """Scored combo with breakdown and rejection info."""

    bot: str
    symbol: str
    timeframe: str
    variant_id: str = "baseline"
    params_override: dict[str, Any] = field(default_factory=dict)

    # Score
    score_total: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)

    # Rejection
    rejected: bool = False
    rejection_reasons: list[str] = field(default_factory=list)

    # Raw inputs
    oos_sharpe: float = 0.0
    oos_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    exposure_time_pct: float = 0.0
    folds_profitable_pct: float = 0.0
    sharpe_cv: float = 0.0
    trades_per_day: float = 0.0
    oos_trades: int = 0
    win_rate: float = 0.0

    # Source
    wf_run_id: str | None = None
    sweep_run_id: str | None = None

    @property
    def combo_id(self) -> str:
        base = f"{self.symbol}:{self.bot}:{self.timeframe}"
        if self.variant_id != "baseline":
            return f"{base}:{self.variant_id}"
        return base


def apply_hard_gates(
    metrics: dict[str, Any],
    gates: HardGates | None = None,
) -> tuple[bool, list[str]]:
    """
    Apply hard rejection gates to a combo's metrics.

    Args:
        metrics: Dict with keys matching ComboScore fields
        gates: Thresholds (defaults to HardGates())

    Returns:
        (passed, list_of_rejection_reasons)
    """
    g = gates or HardGates()
    reasons: list[str] = []

    dd = metrics.get("max_drawdown_pct", 0.0)
    total_trades = metrics.get("total_trades", 0)
    oos_trades = metrics.get("oos_trades", 0)
    exposure = metrics.get("exposure_time_pct", 0.0)
    folds_pct = metrics.get("folds_profitable_pct", 0.0)
    oos_sharpe = metrics.get("oos_sharpe", 0.0)

    # Check for NaN/Inf in critical fields
    for key in ("oos_sharpe", "oos_return_pct", "max_drawdown_pct"):
        val = metrics.get(key, 0.0)
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            reasons.append(f"NaN/Inf in {key}")

    if dd > g.max_drawdown_pct:
        reasons.append(f"DD {dd:.1f}% > {g.max_drawdown_pct:.1f}%")

    if total_trades < g.min_trades_sweep:
        reasons.append(f"Trades {total_trades} < {g.min_trades_sweep}")

    if oos_trades > 0 and oos_trades < g.min_trades_oos:
        reasons.append(f"OOS trades {oos_trades} < {g.min_trades_oos}")

    if exposure > 0 and exposure < g.min_exposure_pct:
        reasons.append(f"Exposure {exposure:.1f}% < {g.min_exposure_pct:.1f}%")

    if exposure > g.max_exposure_pct:
        reasons.append(f"Exposure {exposure:.1f}% > {g.max_exposure_pct:.1f}%")

    if folds_pct > 0 and folds_pct < g.min_folds_profitable_pct:
        reasons.append(f"Folds profitable {folds_pct:.0%} < {g.min_folds_profitable_pct:.0%}")

    passed = len(reasons) == 0
    return passed, reasons


def compute_weighted_score(
    oos_sharpe: float,
    oos_return_pct: float,
    max_drawdown_pct: float,
    trades_per_day: float,
    folds_profitable_pct: float,
    sharpe_cv: float,
    weights: ScoringWeights | None = None,
) -> tuple[float, dict[str, float]]:
    """
    Compute weighted 0-100 score with stability penalties.

    Args:
        oos_sharpe: Out-of-sample Sharpe ratio
        oos_return_pct: Out-of-sample return percentage (0.1 = 10%)
        max_drawdown_pct: Maximum drawdown percentage (0.1 = 10%)
        trades_per_day: Trades per day
        folds_profitable_pct: Fraction of WF folds that were profitable (0-1)
        sharpe_cv: Coefficient of variation of Sharpe across folds
        weights: Scoring weights

    Returns:
        (score_total, breakdown_dict)
    """
    w = weights or ScoringWeights()
    breakdown: dict[str, float] = {}

    # 1. Sharpe component (45%): clamp at 6.0
    sharpe_clamped = min(max(oos_sharpe, 0.0), 6.0)
    sharpe_score = (sharpe_clamped / 6.0) * 100.0
    breakdown["sharpe_raw"] = sharpe_score

    # 2. Return component (20%): clamp at 100%
    # oos_return_pct is in decimal (0.1 = 10%) if < 2.0, else already percentage
    return_pct = oos_return_pct * 100.0 if abs(oos_return_pct) < 2.0 else oos_return_pct
    return_clamped = min(max(return_pct, 0.0), 100.0)
    return_score = return_clamped
    breakdown["return_raw"] = return_score

    # 3. Drawdown component (25%): nonlinear, bonus if <= 10%
    # max_drawdown_pct: decimal (0.1 = 10%) if < 1.0, else already percentage
    dd_pct = max_drawdown_pct * 100.0 if max_drawdown_pct < 1.0 else max_drawdown_pct
    dd_clamped = min(max(dd_pct, 0.0), 20.0)
    dd_score = (1.0 - (dd_clamped / 20.0) ** 2) * 100.0
    if dd_clamped <= 10.0:
        dd_score = min(dd_score * 1.1, 100.0)  # 10% bonus
    breakdown["drawdown_raw"] = dd_score

    # 4. Trade confidence (10%): trades_per_day + folds + CV penalty
    tpd_norm = min(trades_per_day / 3.0, 1.0)  # Normalize 0-3 trades/day -> 0-1
    folds_norm = min(max(folds_profitable_pct, 0.0), 1.0)
    cv_penalty = min(max(sharpe_cv - 0.75, 0.0) / 1.25, 1.0)  # Penalty starts at CV > 0.75
    confidence_score = (0.5 * tpd_norm + 0.5 * folds_norm) * 100.0 * (1.0 - cv_penalty)
    breakdown["confidence_raw"] = confidence_score

    # Weighted total
    total = (
        w.oos_sharpe * sharpe_score
        + w.oos_return * return_score
        + w.drawdown * dd_score
        + w.trade_confidence * confidence_score
    )

    # Stability penalties
    penalty = 0.0
    if sharpe_cv > 0.75:
        cv_pen = min((sharpe_cv - 0.75) / 1.25, 1.0) * 15.0
        penalty += cv_pen
        breakdown["penalty_sharpe_cv"] = -cv_pen

    if 0 < folds_profitable_pct < 0.60:
        folds_pen = (0.60 - folds_profitable_pct) / 0.60 * 8.0
        penalty += folds_pen
        breakdown["penalty_folds"] = -folds_pen

    total = max(total - penalty, 0.0)
    total = min(total, 100.0)

    breakdown["total_before_penalties"] = total + penalty
    breakdown["total_penalties"] = -penalty

    return round(total, 2), breakdown


def score_combo(
    metrics: dict[str, Any],
    gates: HardGates | None = None,
    weights: ScoringWeights | None = None,
) -> ComboScore:
    """
    Score a single combo: apply hard gates, then compute weighted score.

    Args:
        metrics: Dict with bot, symbol, timeframe, and metric fields
        gates: Hard gate thresholds
        weights: Scoring weights

    Returns:
        ComboScore with score and/or rejection info
    """
    cs = ComboScore(
        bot=metrics.get("bot", ""),
        symbol=metrics.get("symbol", ""),
        timeframe=metrics.get("timeframe", ""),
        variant_id=metrics.get("variant_id", "baseline"),
        params_override=metrics.get("params_override", {}),
        oos_sharpe=metrics.get("oos_sharpe", 0.0),
        oos_return_pct=metrics.get("oos_return_pct", 0.0),
        max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
        total_trades=metrics.get("total_trades", 0),
        exposure_time_pct=metrics.get("exposure_time_pct", 0.0),
        folds_profitable_pct=metrics.get("folds_profitable_pct", 0.0),
        sharpe_cv=metrics.get("sharpe_cv", 0.0),
        trades_per_day=metrics.get("trades_per_day", 0.0),
        oos_trades=metrics.get("oos_trades", 0),
        win_rate=metrics.get("win_rate", 0.0),
        wf_run_id=metrics.get("wf_run_id"),
        sweep_run_id=metrics.get("sweep_run_id"),
    )

    # Apply hard gates
    passed, reasons = apply_hard_gates(metrics, gates)
    if not passed:
        cs.rejected = True
        cs.rejection_reasons = reasons
        cs.score_total = 0.0
        return cs

    # Compute weighted score
    score, breakdown = compute_weighted_score(
        oos_sharpe=cs.oos_sharpe,
        oos_return_pct=cs.oos_return_pct,
        max_drawdown_pct=cs.max_drawdown_pct,
        trades_per_day=cs.trades_per_day,
        folds_profitable_pct=cs.folds_profitable_pct,
        sharpe_cv=cs.sharpe_cv,
        weights=weights,
    )

    cs.score_total = score
    cs.score_breakdown = breakdown
    return cs
