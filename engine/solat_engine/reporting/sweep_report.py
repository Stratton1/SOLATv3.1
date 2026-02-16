"""
Canonical sweep report generator.

Produces consistent Markdown + CSV + JSON output from sweep results.
Used by all sweep scripts (grand sweep, smoke benchmark, walk-forward, etc.).

The single source of truth for metrics is MetricsSummary (backtest/models.py).
ComboResultRow is a flat projection of MetricsSummary fields for tabular output.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Verdict rules (deterministic, documented)
# ---------------------------------------------------------------------------
# Sharpe >= 1.5 AND PF >= 1.5 AND trades >= 10 AND MDD <= 30%  => "Strong"
# Sharpe >= 0.75 AND PF >= 1.2 AND trades >= 10               => "Moderate"
# Sharpe >= 0.3 AND trades >= 5                                 => "Weak"
# Sharpe >= -0.15 AND trades >= 1                               => "Flat"
# trades == 0                                                   => "No Trades"
# else                                                          => "Poor"

COLUMN_GLOSSARY: dict[str, str] = {
    # IDs
    "bot": "Strategy/bot name",
    "symbol": "Instrument symbol (e.g. EURUSD)",
    "timeframe": "Bar timeframe (e.g. 1h, 4h)",
    "pass_id": "Sweep pass identifier (e.g. cache_on, cache_off)",
    "run_id": "Unique backtest run identifier",
    "combo_id": "Deterministic hash of bot+symbol+timeframe+dates",
    "sweep_id": "Parent sweep identifier",
    "success": "Whether the backtest completed without error",
    "error": "Error message if backtest failed",
    # Data range
    "date_start": "First bar date (ISO)",
    "date_end": "Last bar date (ISO)",
    "days": "Duration in calendar days",
    "bars": "Total number of bars processed",
    "runtime_s": "Wall-clock time for this combo (seconds)",
    # Trading activity
    "trades": "Total closed trades",
    "wins": "Number of winning trades",
    "losses": "Number of losing trades",
    "long_trades": "Number of long trades",
    "short_trades": "Number of short trades",
    "win_rate": "Fraction of winning trades (0-1)",
    "avg_trade_pnl": "Average P&L per trade",
    "median_trade_return_pct": "Median trade return as percentage",
    "expectancy": "Expected value per trade (avg_win*wr - avg_loss*(1-wr))",
    "trades_per_day": "Average trades per calendar day",
    "avg_bars_held": "Average number of bars a trade is held",
    # Performance
    "net_pnl": "Total net profit/loss",
    "net_return_pct": "Total return as percentage of initial capital",
    "cagr": "Compound annual growth rate",
    "sharpe": "Annualized Sharpe ratio (excess return / volatility)",
    "sortino": "Sortino ratio (excess return / downside volatility)",
    "calmar": "Calmar ratio (CAGR / max drawdown)",
    "volatility": "Annualized return volatility (std dev)",
    "profit_factor": "Gross profit / gross loss",
    "payoff_ratio": "Average win / average loss",
    "max_drawdown_pct": "Maximum drawdown as percentage of equity peak",
    "max_drawdown_duration_bars": "Longest drawdown period in bars",
    "avg_drawdown_pct": "Average drawdown as percentage",
    "time_in_market_pct": "Percentage of time with open positions",
    # Risk / extremes
    "largest_win": "Largest single winning trade P&L",
    "largest_loss": "Largest single losing trade P&L (negative)",
    "max_consecutive_wins": "Longest streak of consecutive wins",
    "max_consecutive_losses": "Longest streak of consecutive losses",
    # Execution quality
    "total_orders": "Total orders submitted",
    "rejected_orders": "Orders rejected by risk engine",
    "total_transaction_costs": "Sum of spread + slippage + fees",
    "avg_spread_paid": "Average spread cost per trade",
    "avg_slippage": "Average slippage per trade",
    # Equity context
    "initial_cash": "Starting capital",
    "start_equity": "Equity at start of backtest",
    "end_equity": "Equity at end of backtest",
    "equity_peak": "Highest equity reached during backtest",
    "max_drawdown": "Maximum drawdown in absolute currency terms",
    "downside_volatility": "Volatility of negative returns only",
    # Trade detail
    "median_bars_held": "Median number of bars a trade is held",
    "avg_win": "Average winning trade P&L",
    "avg_loss": "Average losing trade P&L (negative)",
    # Distribution
    "skewness": "Skewness of trade return distribution",
    "kurtosis": "Kurtosis of trade return distribution",
    # Execution detail
    "filled_orders": "Orders that were filled",
    "partial_fills_count": "Orders partially filled",
    "total_spread_cost": "Total spread cost across all trades",
    "total_slippage_cost": "Total slippage cost across all trades",
    "total_fees": "Total commission fees across all trades",
    # Annualized / exposure
    "annualized_return": "Annualized return rate",
    "exposure_adjusted_return": "Return adjusted for time in market",
    "avg_drawdown_duration_bars": "Average drawdown duration in bars",
    "avg_exposure": "Average portfolio exposure",
    "max_exposure": "Peak portfolio exposure",
    "warnings_count": "Number of diagnostic warnings",
    # Data quality
    "missing_bar_pct": "Percentage of expected bars that are missing",
    "data_gaps_detected": "Number of data gaps detected",
    # Strategy health
    "zero_trade": "True if strategy generated zero trades",
    # Verdict
    "verdict": "Deterministic quality verdict (Strong/Moderate/Weak/Flat/Poor/No Trades)",
    "verdict_flags": "Comma-separated warning flags (NO_TRADES, HIGH_DD, LOW_TRADES, UNPROFITABLE)",
}

VERDICT_RULES = """
Verdict is assigned deterministically:
  Strong   : Sharpe >= 1.5, PF >= 1.5, trades >= 10, MDD <= 30%
  Moderate : Sharpe >= 0.75, PF >= 1.2, trades >= 10
  Weak     : Sharpe >= 0.3, trades >= 5
  Flat     : Sharpe >= -0.15, trades >= 1
  No Trades: trades == 0
  Poor     : everything else
""".strip()


def compute_verdict(
    sharpe: float,
    profit_factor: float,
    total_trades: int,
    max_drawdown_pct: float,
) -> str:
    """Deterministic verdict label from metrics."""
    if total_trades == 0:
        return "No Trades"
    if sharpe >= 1.5 and profit_factor >= 1.5 and total_trades >= 10 and max_drawdown_pct <= 30.0:
        return "Strong"
    if sharpe >= 0.75 and profit_factor >= 1.2 and total_trades >= 10:
        return "Moderate"
    if sharpe >= 0.3 and total_trades >= 5:
        return "Weak"
    if sharpe >= -0.15 and total_trades >= 1:
        return "Flat"
    return "Poor"


# ---------------------------------------------------------------------------
# ComboResultRow — flat projection of a single combo's full metrics
# ---------------------------------------------------------------------------

@dataclass
class ComboResultRow:
    """One row in the sweep report. All metrics for a single bot/symbol/TF combo."""

    # --- IDs / keys ---
    bot: str = ""
    symbol: str = ""
    timeframe: str = ""
    pass_id: str = ""          # e.g. "cache_on", "cache_off"
    run_id: str = ""
    combo_id: str = ""
    sweep_id: str = ""
    success: bool = True
    error: str = ""

    # --- Data range ---
    date_start: str = ""       # ISO date
    date_end: str = ""         # ISO date
    days: float = 0.0          # duration in calendar days
    bars: int = 0
    runtime_s: float = 0.0

    # --- Trading activity ---
    trades: int = 0
    wins: int = 0
    losses: int = 0
    long_trades: int = 0
    short_trades: int = 0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    median_trade_return_pct: float = 0.0
    expectancy: float = 0.0
    trades_per_day: float = 0.0
    avg_bars_held: float = 0.0

    # --- Performance ---
    net_pnl: float = 0.0
    net_return_pct: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    volatility: float = 0.0
    profit_factor: float = 0.0
    payoff_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    avg_drawdown_pct: float = 0.0
    time_in_market_pct: float = 0.0

    # --- Risk / extremes ---
    largest_win: float = 0.0
    largest_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # --- Execution quality ---
    total_orders: int = 0
    rejected_orders: int = 0
    total_transaction_costs: float = 0.0
    avg_spread_paid: float = 0.0
    avg_slippage: float = 0.0

    # --- Equity context ---
    initial_cash: float = 0.0
    start_equity: float = 0.0
    end_equity: float = 0.0
    equity_peak: float = 0.0
    max_drawdown: float = 0.0          # absolute drawdown (not %)
    downside_volatility: float = 0.0

    # --- Trade detail ---
    median_bars_held: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # --- Distribution ---
    skewness: float = 0.0
    kurtosis: float = 0.0

    # --- Execution detail ---
    filled_orders: int = 0
    partial_fills_count: int = 0
    total_spread_cost: float = 0.0
    total_slippage_cost: float = 0.0
    total_fees: float = 0.0

    # --- Annualized / exposure ---
    annualized_return: float = 0.0
    exposure_adjusted_return: float = 0.0
    avg_drawdown_duration_bars: float = 0.0
    avg_exposure: float = 0.0
    max_exposure: float = 0.0
    warnings_count: int = 0

    # --- Data quality ---
    missing_bar_pct: float = 0.0
    data_gaps_detected: int = 0

    # --- Signal / strategy health ---
    zero_trade: bool = False

    # --- Verdict ---
    verdict: str = ""
    verdict_flags: str = ""

    def __post_init__(self) -> None:
        self.zero_trade = self.trades == 0
        if not self.verdict:
            self.verdict = compute_verdict(
                self.sharpe, self.profit_factor, self.trades, self.max_drawdown_pct,
            )
        # Compute verdict flags
        flags: list[str] = []
        if self.trades == 0:
            flags.append("NO_TRADES")
        if self.max_drawdown_pct > 30:
            flags.append("HIGH_DD")
        if 0 < self.trades < 10:
            flags.append("LOW_TRADES")
        if self.profit_factor < 1.0 and self.trades > 0:
            flags.append("UNPROFITABLE")
        self.verdict_flags = ",".join(flags) if flags else ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    # Core columns for the compact Markdown table
    CORE_COLUMNS = [
        "bot", "symbol", "timeframe", "days", "bars", "trades",
        "win_rate", "sharpe", "sortino", "profit_factor",
        "max_drawdown_pct", "net_return_pct", "expectancy",
        "trades_per_day", "runtime_s", "verdict",
    ]


# ---------------------------------------------------------------------------
# Converters: populate ComboResultRow from existing data structures
# ---------------------------------------------------------------------------

def row_from_metrics_summary(
    metrics: Any,
    *,
    bot: str = "",
    symbol: str = "",
    timeframe: str = "",
    pass_id: str = "",
    run_id: str = "",
    combo_id: str = "",
    runtime_s: float = 0.0,
    success: bool = True,
    error: str = "",
) -> ComboResultRow:
    """Build a ComboResultRow from a MetricsSummary object."""
    m = metrics
    return ComboResultRow(
        bot=bot or getattr(m, "bot", "") or "",
        symbol=symbol or getattr(m, "symbol", "") or "",
        timeframe=timeframe or getattr(m, "timeframe", "") or "",
        pass_id=pass_id,
        run_id=run_id or getattr(m, "run_id", "") or "",
        combo_id=combo_id,
        success=success,
        error=error,
        date_start=_iso(getattr(m, "data_start", None)),
        date_end=_iso(getattr(m, "data_end", None)),
        days=getattr(m, "duration_days", 0.0) or 0.0,
        bars=getattr(m, "bar_count", 0) or 0,
        runtime_s=runtime_s,
        trades=getattr(m, "total_trades", 0) or 0,
        wins=getattr(m, "winning_trades", 0) or 0,
        losses=getattr(m, "losing_trades", 0) or 0,
        long_trades=getattr(m, "long_trades", 0) or 0,
        short_trades=getattr(m, "short_trades", 0) or 0,
        win_rate=getattr(m, "win_rate", 0.0) or 0.0,
        avg_trade_pnl=getattr(m, "avg_trade_pnl", 0.0) or 0.0,
        median_trade_return_pct=getattr(m, "median_trade_return_pct", 0.0) or 0.0,
        expectancy=getattr(m, "expectancy", 0.0) or 0.0,
        trades_per_day=getattr(m, "trades_per_day", 0.0) or 0.0,
        avg_bars_held=getattr(m, "avg_bars_held", 0.0) or 0.0,
        net_pnl=getattr(m, "total_return", 0.0) or 0.0,
        net_return_pct=getattr(m, "total_return_pct", 0.0) or 0.0,
        cagr=getattr(m, "cagr", 0.0) or 0.0,
        sharpe=getattr(m, "sharpe_ratio", 0.0) or 0.0,
        sortino=getattr(m, "sortino_ratio", 0.0) or 0.0,
        calmar=getattr(m, "calmar_ratio", 0.0) or 0.0,
        volatility=getattr(m, "volatility", 0.0) or 0.0,
        profit_factor=getattr(m, "profit_factor", 0.0) or 0.0,
        payoff_ratio=getattr(m, "payoff_ratio", 0.0) or 0.0,
        max_drawdown_pct=getattr(m, "max_drawdown_pct", 0.0) or 0.0,
        max_drawdown_duration_bars=getattr(m, "max_drawdown_duration_bars", 0) or 0,
        avg_drawdown_pct=getattr(m, "avg_drawdown_pct", 0.0) or 0.0,
        time_in_market_pct=getattr(m, "time_in_market_pct", 0.0) or 0.0,
        largest_win=getattr(m, "largest_win", 0.0) or 0.0,
        largest_loss=getattr(m, "largest_loss", 0.0) or 0.0,
        max_consecutive_wins=getattr(m, "max_consecutive_wins", 0) or 0,
        max_consecutive_losses=getattr(m, "max_consecutive_losses", 0) or 0,
        total_orders=getattr(m, "total_orders", 0) or 0,
        rejected_orders=getattr(m, "rejected_orders", 0) or 0,
        total_transaction_costs=getattr(m, "total_transaction_costs", 0.0) or 0.0,
        avg_spread_paid=getattr(m, "avg_spread_paid", 0.0) or 0.0,
        avg_slippage=getattr(m, "avg_slippage", 0.0) or 0.0,
        # v3 fields
        initial_cash=getattr(m, "initial_cash", 0.0) or 0.0,
        start_equity=getattr(m, "start_equity", 0.0) or 0.0,
        end_equity=getattr(m, "end_equity", 0.0) or 0.0,
        equity_peak=getattr(m, "equity_peak", 0.0) or 0.0,
        max_drawdown=getattr(m, "max_drawdown", 0.0) or 0.0,
        downside_volatility=getattr(m, "downside_volatility", 0.0) or 0.0,
        median_bars_held=getattr(m, "median_bars_held", 0.0) or 0.0,
        avg_win=getattr(m, "avg_win", 0.0) or 0.0,
        avg_loss=getattr(m, "avg_loss", 0.0) or 0.0,
        skewness=getattr(m, "skewness", 0.0) or 0.0,
        kurtosis=getattr(m, "kurtosis", 0.0) or 0.0,
        filled_orders=getattr(m, "filled_orders", 0) or 0,
        partial_fills_count=getattr(m, "partial_fills_count", 0) or 0,
        total_spread_cost=getattr(m, "total_spread_cost", 0.0) or 0.0,
        total_slippage_cost=getattr(m, "total_slippage_cost", 0.0) or 0.0,
        total_fees=getattr(m, "total_fees", 0.0) or 0.0,
        annualized_return=getattr(m, "annualized_return", 0.0) or 0.0,
        exposure_adjusted_return=getattr(m, "exposure_adjusted_return", 0.0) or 0.0,
        avg_drawdown_duration_bars=getattr(m, "avg_drawdown_duration_bars", 0.0) or 0.0,
        avg_exposure=getattr(m, "avg_exposure", 0.0) or 0.0,
        max_exposure=getattr(m, "max_exposure", 0.0) or 0.0,
        warnings_count=getattr(m, "warnings_count", 0) or 0,
        missing_bar_pct=getattr(m, "missing_bar_pct", 0.0) or 0.0,
        data_gaps_detected=getattr(m, "data_gaps_detected", 0) or 0,
    )


def rows_from_combo_results(
    combo_results: list[Any],
    pass_id: str = "",
) -> list[ComboResultRow]:
    """Convert a list of parallel_sweep.ComboResult to ComboResultRows.

    ComboResult only carries a subset of MetricsSummary fields, so some
    columns will be zero/blank. This is the fallback when full MetricsSummary
    is not available.
    """
    rows = []
    for cr in combo_results:
        rows.append(ComboResultRow(
            bot=cr.bot,
            symbol=cr.symbol,
            timeframe=cr.timeframe,
            pass_id=pass_id,
            combo_id=getattr(cr, "combo_id", ""),
            success=cr.success,
            error=getattr(cr, "error", "") or "",
            runtime_s=getattr(cr, "duration_s", 0.0),
            trades=getattr(cr, "total_trades", 0),
            win_rate=getattr(cr, "win_rate", 0.0),
            sharpe=getattr(cr, "sharpe", 0.0),
            sortino=getattr(cr, "sortino", 0.0),
            calmar=getattr(cr, "calmar", 0.0),
            profit_factor=getattr(cr, "profit_factor", 0.0),
            payoff_ratio=getattr(cr, "payoff_ratio", 0.0),
            max_drawdown_pct=getattr(cr, "max_drawdown", 0.0),
            net_pnl=getattr(cr, "pnl", 0.0),
            net_return_pct=getattr(cr, "total_return_pct", 0.0),
            avg_trade_pnl=getattr(cr, "avg_trade_pnl", 0.0),
            expectancy=getattr(cr, "expectancy", 0.0),
            volatility=getattr(cr, "volatility", 0.0),
            time_in_market_pct=getattr(cr, "time_in_market_pct", 0.0),
            max_consecutive_wins=getattr(cr, "max_consecutive_wins", 0),
            max_consecutive_losses=getattr(cr, "max_consecutive_losses", 0),
            total_transaction_costs=getattr(cr, "total_transaction_costs", 0.0),
            # v2 fields
            wins=getattr(cr, "winning_trades", 0),
            losses=getattr(cr, "losing_trades", 0),
            long_trades=getattr(cr, "long_trades", 0),
            short_trades=getattr(cr, "short_trades", 0),
            largest_win=getattr(cr, "largest_win", 0.0),
            largest_loss=getattr(cr, "largest_loss", 0.0),
            cagr=getattr(cr, "cagr", 0.0),
            days=getattr(cr, "duration_days", 0.0),
            bars=getattr(cr, "bar_count", 0),
            date_start=getattr(cr, "data_start", ""),
            date_end=getattr(cr, "data_end", ""),
            rejected_orders=getattr(cr, "rejected_orders", 0),
            total_orders=getattr(cr, "total_orders", 0),
            trades_per_day=getattr(cr, "trades_per_day", 0.0),
            avg_bars_held=getattr(cr, "avg_bars_held", 0.0),
            median_trade_return_pct=getattr(cr, "median_trade_return_pct", 0.0),
            max_drawdown_duration_bars=getattr(cr, "max_drawdown_duration_bars", 0),
            avg_drawdown_pct=getattr(cr, "avg_drawdown_pct", 0.0),
            avg_spread_paid=getattr(cr, "avg_spread_paid", 0.0),
            avg_slippage=getattr(cr, "avg_slippage", 0.0),
            # v3 fields
            initial_cash=getattr(cr, "initial_cash", 0.0),
            start_equity=getattr(cr, "start_equity", 0.0),
            end_equity=getattr(cr, "end_equity", 0.0),
            equity_peak=getattr(cr, "equity_peak", 0.0),
            max_drawdown=getattr(cr, "max_drawdown_abs", 0.0),
            downside_volatility=getattr(cr, "downside_volatility", 0.0),
            median_bars_held=getattr(cr, "median_bars_held", 0.0),
            avg_win=getattr(cr, "avg_win", 0.0),
            avg_loss=getattr(cr, "avg_loss", 0.0),
            skewness=getattr(cr, "skewness", 0.0),
            kurtosis=getattr(cr, "kurtosis", 0.0),
            filled_orders=getattr(cr, "filled_orders", 0),
            partial_fills_count=getattr(cr, "partial_fills_count", 0),
            total_spread_cost=getattr(cr, "total_spread_cost", 0.0),
            total_slippage_cost=getattr(cr, "total_slippage_cost", 0.0),
            total_fees=getattr(cr, "total_fees", 0.0),
            annualized_return=getattr(cr, "annualized_return", 0.0),
            exposure_adjusted_return=getattr(cr, "exposure_adjusted_return", 0.0),
            avg_drawdown_duration_bars=getattr(cr, "avg_drawdown_duration_bars", 0.0),
            avg_exposure=getattr(cr, "avg_exposure", 0.0),
            max_exposure=getattr(cr, "max_exposure", 0.0),
            warnings_count=getattr(cr, "warnings_count", 0),
            missing_bar_pct=getattr(cr, "missing_bar_pct", 0.0),
            data_gaps_detected=getattr(cr, "data_gaps_detected", 0),
        ))
    return rows


def rows_from_metrics_summary(
    metrics_list: list[Any],
    *,
    pass_id: str = "",
) -> list[ComboResultRow]:
    """Convert a list of MetricsSummary objects to rows."""
    return [
        row_from_metrics_summary(m, pass_id=pass_id)
        for m in metrics_list
    ]


# ---------------------------------------------------------------------------
# Report metadata
# ---------------------------------------------------------------------------

@dataclass
class SweepReportMetadata:
    """Metadata for the sweep report header."""
    sweep_name: str = "Sweep Report"
    generated_at: str = ""
    dataset: str = ""
    grid_description: str = ""
    bots: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    passes: list[str] = field(default_factory=list)
    date_start: str = ""
    date_end: str = ""
    engine_version: str = ""
    git_hash: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Aggregation / summary
# ---------------------------------------------------------------------------

@dataclass
class AggBucket:
    """Stats for a group (bot, symbol, timeframe, pass)."""
    key: str
    combos: int = 0
    active_combos: int = 0
    zero_trade_combos: int = 0
    total_trades: int = 0
    avg_sharpe: float = 0.0
    median_sharpe: float = 0.0
    avg_profit_factor: float = 0.0
    avg_max_drawdown_pct: float = 0.0
    avg_win_rate: float = 0.0
    avg_net_return_pct: float = 0.0
    total_runtime_s: float = 0.0
    best_combo: str = ""
    best_sharpe: float = 0.0
    worst_combo: str = ""
    worst_sharpe: float = 0.0


@dataclass
class SweepSummary:
    """Aggregated summary of a sweep."""
    total_combos: int = 0
    succeeded: int = 0
    failed: int = 0
    active_combos: int = 0
    zero_trade_combos: int = 0
    total_runtime_s: float = 0.0
    avg_runtime_s: float = 0.0
    median_sharpe: float = 0.0
    p25_sharpe: float = 0.0
    p75_sharpe: float = 0.0
    best_sharpe: float = 0.0
    worst_sharpe: float = 0.0
    median_pf: float = 0.0
    median_mdd: float = 0.0
    median_win_rate: float = 0.0
    by_bot: list[AggBucket] = field(default_factory=list)
    by_symbol: list[AggBucket] = field(default_factory=list)
    by_timeframe: list[AggBucket] = field(default_factory=list)
    by_pass: list[AggBucket] = field(default_factory=list)


def _aggregate_bucket(key: str, rows: list[ComboResultRow]) -> AggBucket:
    """Compute aggregate stats for a group of rows."""
    active = [r for r in rows if r.trades > 0 and r.success]
    sharpes = [r.sharpe for r in active]
    bucket = AggBucket(
        key=key,
        combos=len(rows),
        active_combos=len(active),
        zero_trade_combos=sum(1 for r in rows if r.trades == 0 and r.success),
        total_trades=sum(r.trades for r in active),
        total_runtime_s=sum(r.runtime_s for r in rows),
    )
    if active:
        bucket.avg_sharpe = statistics.mean(sharpes)
        bucket.median_sharpe = statistics.median(sharpes)
        bucket.avg_profit_factor = statistics.mean(r.profit_factor for r in active)
        bucket.avg_max_drawdown_pct = statistics.mean(r.max_drawdown_pct for r in active)
        bucket.avg_win_rate = statistics.mean(r.win_rate for r in active)
        bucket.avg_net_return_pct = statistics.mean(r.net_return_pct for r in active)
        best = max(active, key=lambda r: r.sharpe)
        worst = min(active, key=lambda r: r.sharpe)
        bucket.best_combo = f"{best.bot}/{best.symbol}/{best.timeframe}"
        bucket.best_sharpe = best.sharpe
        bucket.worst_combo = f"{worst.bot}/{worst.symbol}/{worst.timeframe}"
        bucket.worst_sharpe = worst.sharpe
    return bucket


def compute_summary(rows: list[ComboResultRow]) -> SweepSummary:
    """Compute full aggregated summary from rows."""
    s = SweepSummary()
    s.total_combos = len(rows)
    s.succeeded = sum(1 for r in rows if r.success)
    s.failed = sum(1 for r in rows if not r.success)

    active = [r for r in rows if r.trades > 0 and r.success]
    s.active_combos = len(active)
    s.zero_trade_combos = sum(1 for r in rows if r.trades == 0 and r.success)
    s.total_runtime_s = sum(r.runtime_s for r in rows)
    s.avg_runtime_s = s.total_runtime_s / len(rows) if rows else 0.0

    sharpes = sorted(r.sharpe for r in active)
    if sharpes:
        s.median_sharpe = statistics.median(sharpes)
        s.p25_sharpe = sharpes[len(sharpes) // 4]
        s.p75_sharpe = sharpes[3 * len(sharpes) // 4]
        s.best_sharpe = sharpes[-1]
        s.worst_sharpe = sharpes[0]
    pfs = [r.profit_factor for r in active]
    if pfs:
        s.median_pf = statistics.median(pfs)
    mdds = [r.max_drawdown_pct for r in active]
    if mdds:
        s.median_mdd = statistics.median(mdds)
    wrs = [r.win_rate for r in active]
    if wrs:
        s.median_win_rate = statistics.median(wrs)

    # By bot
    bots = sorted(set(r.bot for r in rows))
    s.by_bot = [_aggregate_bucket(b, [r for r in rows if r.bot == b]) for b in bots]
    s.by_bot.sort(key=lambda x: x.avg_sharpe, reverse=True)

    # By symbol
    symbols = sorted(set(r.symbol for r in rows))
    s.by_symbol = [_aggregate_bucket(sym, [r for r in rows if r.symbol == sym]) for sym in symbols]
    s.by_symbol.sort(key=lambda x: x.avg_sharpe, reverse=True)

    # By timeframe
    tfs = sorted(set(r.timeframe for r in rows))
    s.by_timeframe = [_aggregate_bucket(tf, [r for r in rows if r.timeframe == tf]) for tf in tfs]
    s.by_timeframe.sort(key=lambda x: x.avg_sharpe, reverse=True)

    # By pass
    passes = sorted(set(r.pass_id for r in rows if r.pass_id))
    if passes:
        s.by_pass = [_aggregate_bucket(p, [r for r in rows if r.pass_id == p]) for p in passes]

    return s


# ---------------------------------------------------------------------------
# Recommendation engine (deterministic rules)
# ---------------------------------------------------------------------------

DEMO_THRESHOLDS = {"min_sharpe": 1.0, "min_pf": 1.0, "min_trades": 10, "max_mdd": 40.0}
BROKEN_THRESHOLD = {"zero_ratio": 0.5}


def _recommendations(rows: list[ComboResultRow], summary: SweepSummary) -> dict[str, list[str]]:
    """Generate deterministic recommendations."""
    recs: dict[str, list[str]] = {"demo_candidates": [], "needs_fixing": [], "deprioritize": []}

    # DEMO candidates
    for r in sorted(rows, key=lambda x: x.sharpe, reverse=True):
        if (
            r.trades >= DEMO_THRESHOLDS["min_trades"]
            and r.sharpe >= DEMO_THRESHOLDS["min_sharpe"]
            and r.profit_factor >= DEMO_THRESHOLDS["min_pf"]
            and r.max_drawdown_pct <= DEMO_THRESHOLDS["max_mdd"]
        ):
            recs["demo_candidates"].append(
                f"{r.bot}/{r.symbol}/{r.timeframe} "
                f"(Sharpe {r.sharpe:.2f}, PF {r.profit_factor:.2f}, "
                f"MDD {r.max_drawdown_pct:.1f}%, {r.trades} trades)"
            )

    # Needs fixing (broken bots)
    for b in summary.by_bot:
        if b.combos > 0 and b.zero_trade_combos / b.combos >= BROKEN_THRESHOLD["zero_ratio"]:
            recs["needs_fixing"].append(
                f"{b.key}: {b.zero_trade_combos}/{b.combos} combos zero-trade "
                f"({b.zero_trade_combos/b.combos:.0%})"
            )

    # Deprioritize (consistently poor)
    for b in summary.by_bot:
        if b.active_combos >= 3 and b.avg_sharpe < -0.5:
            recs["deprioritize"].append(
                f"{b.key}: avg Sharpe {b.avg_sharpe:.2f} across {b.active_combos} combos"
            )
    for b in summary.by_symbol:
        if b.active_combos >= 3 and b.avg_sharpe < -0.5:
            recs["deprioritize"].append(
                f"{b.key}: avg Sharpe {b.avg_sharpe:.2f} across {b.active_combos} combos"
            )

    return recs


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows_data: list[list[str]], align: list[str] | None = None) -> str:
    """Render a Markdown table."""
    if not rows_data:
        return "_No data._\n"
    if align is None:
        align = ["l"] * len(headers)

    # Compute column widths
    widths = [len(h) for h in headers]
    for row in rows_data:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def _pad(val: str, width: int, a: str) -> str:
        if a == "r":
            return val.rjust(width)
        return val.ljust(width)

    sep_parts = []
    for i, w in enumerate(widths):
        if align[i] == "r":
            sep_parts.append("-" * (w - 1) + ":")
        else:
            sep_parts.append("-" * w)

    lines = []
    lines.append("| " + " | ".join(_pad(h, widths[i], "l") for i, h in enumerate(headers)) + " |")
    lines.append("| " + " | ".join(sep_parts) + " |")
    for row in rows_data:
        cells = []
        for i, cell in enumerate(row):
            a = align[i] if i < len(align) else "l"
            w = widths[i] if i < len(widths) else len(cell)
            cells.append(_pad(cell, w, a))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _fmt(v: float, decimals: int = 2) -> str:
    if v == 0.0:
        return "0"
    return f"{v:.{decimals}f}"


def _fmtpct(v: float) -> str:
    if v == 0.0:
        return "0%"
    return f"{v:.1f}%"


def _fmt_runtime(s: float) -> str:
    if s < 60:
        return f"{s:.1f}s"
    return f"{s / 60:.1f}m"


def render_markdown(
    rows: list[ComboResultRow],
    metadata: SweepReportMetadata,
    summary: SweepSummary | None = None,
    *,
    top_n: int = 20,
    include_full_table: bool = False,
) -> str:
    """Render the canonical sweep report as Markdown."""
    if summary is None:
        summary = compute_summary(rows)

    active = [r for r in rows if r.trades > 0 and r.success]
    active_ranked = sorted(active, key=lambda r: r.sharpe, reverse=True)
    zero_trade = [r for r in rows if r.trades == 0 and r.success]
    failed = [r for r in rows if not r.success]

    recs = _recommendations(rows, summary)

    lines: list[str] = []

    # ===== 1. Header =====
    lines.append(f"# {metadata.sweep_name}\n")
    lines.append(f"**Generated:** {metadata.generated_at}  ")
    if metadata.dataset:
        lines.append(f"**Dataset:** {metadata.dataset}  ")
    if metadata.grid_description:
        lines.append(f"**Grid:** {metadata.grid_description}  ")
    if metadata.date_start and metadata.date_end:
        lines.append(f"**Period:** {metadata.date_start} to {metadata.date_end}  ")
    if metadata.engine_version:
        lines.append(f"**Engine:** v{metadata.engine_version}  ")
    if metadata.git_hash:
        lines.append(f"**Git:** `{metadata.git_hash[:8]}`  ")
    if metadata.notes:
        lines.append(f"**Notes:** {metadata.notes}  ")
    lines.append("")

    # ===== 2. Executive Summary =====
    lines.append("---\n")
    lines.append("## Executive Summary\n")

    exec_headers = ["Metric", "Value"]
    exec_rows = [
        ["Total combos", str(summary.total_combos)],
        ["Succeeded", str(summary.succeeded)],
        ["Failed", str(summary.failed)],
        ["Active (traded)", str(summary.active_combos)],
        ["Zero-trade", str(summary.zero_trade_combos)],
        ["Total runtime", _fmt_runtime(summary.total_runtime_s)],
        ["Avg runtime/combo", _fmt_runtime(summary.avg_runtime_s)],
    ]
    if active_ranked:
        exec_rows.extend([
            ["Median Sharpe", _fmt(summary.median_sharpe)],
            ["P25 / P75 Sharpe", f"{_fmt(summary.p25_sharpe)} / {_fmt(summary.p75_sharpe)}"],
            ["Best Sharpe", _fmt(summary.best_sharpe)],
            ["Worst Sharpe", _fmt(summary.worst_sharpe)],
            ["Median PF", _fmt(summary.median_pf)],
            ["Median MDD", _fmtpct(summary.median_mdd)],
            ["Median Win Rate", _fmtpct(summary.median_win_rate * 100)],
        ])

    # Pass comparison
    if summary.by_pass:
        for p in summary.by_pass:
            exec_rows.append([f"Pass '{p.key}' runtime", _fmt_runtime(p.total_runtime_s)])
        if len(summary.by_pass) == 2:
            a, b = summary.by_pass
            if b.total_runtime_s > 0:
                speedup = b.total_runtime_s / a.total_runtime_s if a.total_runtime_s > 0 else 1.0
                exec_rows.append(["Speedup", f"{speedup:.2f}x"])

    lines.append(_md_table(exec_headers, exec_rows, ["l", "r"]))

    # ===== 3. Leaderboards =====
    lines.append("---\n")
    lines.append("## Leaderboards\n")

    # Top N by Sharpe
    lines.append(f"### Top {min(top_n, len(active_ranked))} by Sharpe\n")
    lb_headers = ["Rank", "Bot", "Symbol", "TF", "Sharpe", "PF", "MDD%", "WinRate",
                   "Trades", "Return%", "Expect", "Days", "Time", "Verdict"]
    lb_align = ["r", "l", "l", "l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"]
    lb_rows = []
    for i, r in enumerate(active_ranked[:top_n], 1):
        lb_rows.append([
            str(i), r.bot, r.symbol, r.timeframe,
            _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
            _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
            _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
        ])
    lines.append(_md_table(lb_headers, lb_rows, lb_align))

    # Worst N by Sharpe
    if len(active_ranked) > top_n:
        worst = active_ranked[-top_n:]
        worst.reverse()
        lines.append(f"### Worst {min(top_n, len(worst))} by Sharpe\n")
        wb_rows = []
        for i, r in enumerate(worst, 1):
            wb_rows.append([
                str(i), r.bot, r.symbol, r.timeframe,
                _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
                _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
                _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
            ])
        lines.append(_md_table(lb_headers, wb_rows, lb_align))

    # Top N by Return%
    by_return = sorted(active, key=lambda r: r.net_return_pct, reverse=True)
    lines.append(f"### Top {min(top_n, len(by_return))} by Return%\n")
    ret_rows = []
    for i, r in enumerate(by_return[:top_n], 1):
        ret_rows.append([
            str(i), r.bot, r.symbol, r.timeframe,
            _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
            _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
            _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
        ])
    lines.append(_md_table(lb_headers, ret_rows, lb_align))

    # Worst N by Max Drawdown%
    by_mdd = sorted(active, key=lambda r: r.max_drawdown_pct, reverse=True)
    lines.append(f"### Worst {min(top_n, len(by_mdd))} by Max Drawdown%\n")
    mdd_rows = []
    for i, r in enumerate(by_mdd[:top_n], 1):
        mdd_rows.append([
            str(i), r.bot, r.symbol, r.timeframe,
            _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
            _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
            _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
        ])
    lines.append(_md_table(lb_headers, mdd_rows, lb_align))

    # Most Active by Trades/Day
    by_activity = sorted(active, key=lambda r: r.trades_per_day, reverse=True)
    lines.append(f"### Most Active {min(top_n, len(by_activity))} by Trades/Day\n")
    act_rows = []
    for i, r in enumerate(by_activity[:top_n], 1):
        act_rows.append([
            str(i), r.bot, r.symbol, r.timeframe,
            _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
            _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
            _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
        ])
    lines.append(_md_table(lb_headers, act_rows, lb_align))

    # ===== 4. Full Results =====
    if include_full_table and active_ranked:
        lines.append("---\n")
        lines.append(f"## Full Results ({len(active_ranked)} active combos)\n")
        full_rows = []
        for i, r in enumerate(active_ranked, 1):
            full_rows.append([
                str(i), r.bot, r.symbol, r.timeframe,
                _fmt(r.sharpe), _fmt(r.profit_factor), _fmtpct(r.max_drawdown_pct),
                _fmtpct(r.win_rate * 100), str(r.trades), _fmtpct(r.net_return_pct),
                _fmt(r.expectancy), _fmt(r.days, 0), _fmt_runtime(r.runtime_s), r.verdict,
            ])
        lines.append(_md_table(lb_headers, full_rows, lb_align))
    elif active_ranked:
        lines.append("---\n")
        lines.append(f"## Full Results\n\n"
                      f"_{len(active_ranked)} active combos. See CSV sidecar for complete data._\n")

    # ===== 5. Zero-trade combos =====
    if zero_trade:
        lines.append("---\n")
        lines.append(f"## Zero-Trade Combos ({len(zero_trade)})\n")
        zt_headers = ["Bot", "Symbol", "TF", "Days", "Bars", "Time", "Note"]
        zt_align = ["l", "l", "l", "r", "r", "r", "l"]
        zt_rows = []
        for r in sorted(zero_trade, key=lambda x: (x.bot, x.symbol, x.timeframe)):
            zt_rows.append([
                r.bot, r.symbol, r.timeframe,
                _fmt(r.days, 0), str(r.bars), _fmt_runtime(r.runtime_s),
                "No signals generated",
            ])
        lines.append(_md_table(zt_headers, zt_rows, zt_align))

    # ===== 6. Aggregates =====
    lines.append("---\n")
    lines.append("## Aggregates\n")

    agg_headers = ["Key", "Combos", "Active", "ZeroTrade", "Trades", "Avg Sharpe",
                    "Med Sharpe", "Avg PF", "Avg MDD%", "Avg WR%", "Best", "Worst"]
    agg_align = ["l", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l", "l"]

    def _agg_rows(buckets: list[AggBucket]) -> list[list[str]]:
        out = []
        for b in buckets:
            out.append([
                b.key, str(b.combos), str(b.active_combos), str(b.zero_trade_combos),
                str(b.total_trades), _fmt(b.avg_sharpe), _fmt(b.median_sharpe),
                _fmt(b.avg_profit_factor), _fmtpct(b.avg_max_drawdown_pct),
                _fmtpct(b.avg_win_rate * 100),
                f"{b.best_combo} ({_fmt(b.best_sharpe)})" if b.best_combo else "-",
                f"{b.worst_combo} ({_fmt(b.worst_sharpe)})" if b.worst_combo else "-",
            ])
        return out

    lines.append("### By Bot\n")
    lines.append(_md_table(agg_headers, _agg_rows(summary.by_bot), agg_align))
    lines.append("### By Symbol\n")
    lines.append(_md_table(agg_headers, _agg_rows(summary.by_symbol), agg_align))
    lines.append("### By Timeframe\n")
    lines.append(_md_table(agg_headers, _agg_rows(summary.by_timeframe), agg_align))

    if summary.by_pass:
        lines.append("### By Pass\n")
        pass_headers = ["Pass", "Runtime", "Avg/Combo", "Combos"]
        pass_align = ["l", "r", "r", "r"]
        pass_rows = [[
            p.key, _fmt_runtime(p.total_runtime_s),
            _fmt_runtime(p.total_runtime_s / p.combos if p.combos else 0),
            str(p.combos),
        ] for p in summary.by_pass]
        lines.append(_md_table(pass_headers, pass_rows, pass_align))

    # ===== 7. Recommendations =====
    lines.append("---\n")
    lines.append("## Recommendations\n")
    lines.append(f"_Thresholds: Sharpe >= {DEMO_THRESHOLDS['min_sharpe']}, "
                  f"PF >= {DEMO_THRESHOLDS['min_pf']}, "
                  f"trades >= {DEMO_THRESHOLDS['min_trades']}, "
                  f"MDD <= {DEMO_THRESHOLDS['max_mdd']}%_\n")

    if recs["demo_candidates"]:
        lines.append(f"### DEMO Candidates ({len(recs['demo_candidates'])})\n")
        for c in recs["demo_candidates"]:
            lines.append(f"- {c}")
        lines.append("")
    else:
        lines.append("### DEMO Candidates\n\n_None meet all thresholds._\n")

    if recs["needs_fixing"]:
        lines.append(f"### Needs Fixing ({len(recs['needs_fixing'])})\n")
        for c in recs["needs_fixing"]:
            lines.append(f"- {c}")
        lines.append("")

    if recs["deprioritize"]:
        lines.append(f"### Deprioritize ({len(recs['deprioritize'])})\n")
        for c in recs["deprioritize"]:
            lines.append(f"- {c}")
        lines.append("")

    # Verdict rules appendix
    lines.append("---\n")
    lines.append("## Appendix: Verdict Rules\n")
    lines.append("```")
    lines.append(VERDICT_RULES)
    lines.append("```\n")

    # Column glossary appendix
    lines.append("---\n")
    lines.append("## Appendix: Column Glossary\n")
    gloss_headers = ["Column", "Description"]
    gloss_align = ["l", "l"]
    gloss_rows = [[col, desc] for col, desc in COLUMN_GLOSSARY.items()]
    lines.append(_md_table(gloss_headers, gloss_rows, gloss_align))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV / JSON writers
# ---------------------------------------------------------------------------

def write_csv(rows: list[ComboResultRow], path: Path) -> None:
    """Write all rows to CSV with full column set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ComboResultRow.field_names()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r.to_dict())


def write_json_summary(
    rows: list[ComboResultRow],
    metadata: SweepReportMetadata,
    summary: SweepSummary | None,
    path: Path,
) -> None:
    """Write JSON summary for programmatic consumption."""
    if summary is None:
        summary = compute_summary(rows)

    # Identify fields that are all-zero (missing data)
    all_fields = ComboResultRow.field_names()
    numeric_fields = [
        f.name for f in fields(ComboResultRow)
        if f.type in ("float", "int") and f.name not in ("trades", "bars", "runtime_s")
    ]
    missing_fields = []
    for fname in numeric_fields:
        vals = [getattr(r, fname) for r in rows if r.success]
        if vals and all(v == 0 for v in vals):
            missing_fields.append(fname)

    obj = {
        "schema_version": "2.0",
        "generated_at": metadata.generated_at,
        "metadata": asdict(metadata),
        "summary": {
            "total_combos": summary.total_combos,
            "succeeded": summary.succeeded,
            "failed": summary.failed,
            "active_combos": summary.active_combos,
            "zero_trade_combos": summary.zero_trade_combos,
            "total_runtime_s": round(summary.total_runtime_s, 2),
            "avg_runtime_s": round(summary.avg_runtime_s, 2),
            "median_sharpe": round(summary.median_sharpe, 4),
            "p25_sharpe": round(summary.p25_sharpe, 4),
            "p75_sharpe": round(summary.p75_sharpe, 4),
            "best_sharpe": round(summary.best_sharpe, 4),
            "worst_sharpe": round(summary.worst_sharpe, 4),
            "median_pf": round(summary.median_pf, 4),
            "median_mdd": round(summary.median_mdd, 4),
            "median_win_rate": round(summary.median_win_rate, 4),
        },
        "by_bot": [asdict(b) for b in summary.by_bot],
        "by_symbol": [asdict(b) for b in summary.by_symbol],
        "by_timeframe": [asdict(b) for b in summary.by_timeframe],
        "by_pass": [asdict(b) for b in summary.by_pass],
        "missing_fields": missing_fields,
        "verdict_rules": VERDICT_RULES,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Top-level convenience function
# ---------------------------------------------------------------------------

def generate_sweep_report(
    rows: list[ComboResultRow],
    metadata: SweepReportMetadata,
    out_dir: Path,
    *,
    top_n: int = 20,
    include_full_table: bool = False,
    formats: set[str] | None = None,
) -> dict[str, Path]:
    """Generate all report artifacts (Markdown, CSV, JSON).

    Returns dict of format -> output path.
    """
    if formats is None:
        formats = {"md", "csv", "json"}

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = compute_summary(rows)
    outputs: dict[str, Path] = {}

    stem = f"sweep_report_{datetime.now(UTC).strftime('%Y-%m-%d_%H%M')}"

    if "md" in formats:
        md_path = out_dir / f"{stem}.md"
        md = render_markdown(rows, metadata, summary,
                             top_n=top_n, include_full_table=include_full_table)
        md_path.write_text(md)
        outputs["md"] = md_path

    if "csv" in formats:
        csv_path = out_dir / f"{stem}.csv"
        write_csv(rows, csv_path)
        outputs["csv"] = csv_path

    if "json" in formats:
        json_path = out_dir / f"{stem}.json"
        write_json_summary(rows, metadata, summary, json_path)
        outputs["json"] = json_path

    return outputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: Any) -> str:
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]
