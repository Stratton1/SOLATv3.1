"""
Performance metrics calculation for backtesting.

Computes Sharpe, Sortino, Calmar, max drawdown, win rate, etc.
"""

import math
from collections.abc import Sequence

from solat_engine.backtest.models import EquityPoint, MetricsSummary, TradeRecord
from solat_engine.logging import get_logger

logger = get_logger(__name__)

# Annualization factors (assuming bars are the base unit)
BARS_PER_DAY_1M = 1440  # 24 * 60 for 1-minute bars
BARS_PER_YEAR_1M = BARS_PER_DAY_1M * 252  # Trading days
RISK_FREE_RATE = 0.0  # Assume 0 for simplicity


def calculate_returns(equity_curve: Sequence[EquityPoint]) -> list[float]:
    """Calculate period-over-period returns from equity curve."""
    if len(equity_curve) < 2:
        return []

    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        if prev_equity > 0:
            ret = (curr_equity - prev_equity) / prev_equity
            returns.append(ret)
        else:
            returns.append(0.0)

    return returns


def calculate_sharpe_ratio(
    returns: Sequence[float],
    risk_free_rate: float = RISK_FREE_RATE,
    periods_per_year: int = BARS_PER_YEAR_1M,
) -> float:
    """
    Calculate Sharpe ratio.

    Sharpe = (mean_return - risk_free) / std_dev * sqrt(periods_per_year)
    """
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    excess_ret = mean_ret - (risk_free_rate / periods_per_year)

    # Standard deviation
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    if std_dev <= 0:
        # Zero volatility: return based on sign of excess returns
        if excess_ret > 0:
            return 99.99  # Cap at high positive value
        elif excess_ret < 0:
            return -99.99  # Cap at high negative value
        return 0.0

    return (excess_ret / std_dev) * math.sqrt(periods_per_year)


def calculate_sortino_ratio(
    returns: Sequence[float],
    risk_free_rate: float = RISK_FREE_RATE,
    periods_per_year: int = BARS_PER_YEAR_1M,
) -> float:
    """
    Calculate Sortino ratio (uses downside deviation).

    Sortino = (mean_return - risk_free) / downside_dev * sqrt(periods_per_year)
    """
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    excess_ret = mean_ret - (risk_free_rate / periods_per_year)

    # Downside deviation (only negative returns)
    downside_returns = [r for r in returns if r < 0]
    if len(downside_returns) < 1:
        return float("inf") if excess_ret > 0 else 0.0

    downside_variance = sum(r**2 for r in downside_returns) / len(downside_returns)
    downside_dev = math.sqrt(downside_variance) if downside_variance > 0 else 0.0

    if downside_dev <= 0:
        return 0.0

    return (excess_ret / downside_dev) * math.sqrt(periods_per_year)


def calculate_max_drawdown(equity_curve: Sequence[EquityPoint]) -> tuple[float, float, int]:
    """
    Calculate maximum drawdown.

    Returns (max_drawdown_absolute, max_drawdown_pct, max_drawdown_duration_bars).
    """
    if len(equity_curve) < 2:
        return 0.0, 0.0, 0

    max_dd = 0.0
    max_dd_pct = 0.0
    max_duration = 0
    current_duration = 0

    high_water_mark = equity_curve[0].equity

    for point in equity_curve:
        if point.equity > high_water_mark:
            high_water_mark = point.equity
            current_duration = 0
        else:
            current_duration += 1
            dd = high_water_mark - point.equity
            dd_pct = dd / high_water_mark if high_water_mark > 0 else 0.0

            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
            if current_duration > max_duration:
                max_duration = current_duration

    return max_dd, max_dd_pct, max_duration


def calculate_calmar_ratio(
    total_return_pct: float,
    max_drawdown_pct: float,
    years: float = 1.0,
) -> float:
    """
    Calculate Calmar ratio.

    Calmar = CAGR / Max Drawdown
    """
    if max_drawdown_pct <= 0 or years <= 0:
        return 0.0

    cagr = float((1 + total_return_pct) ** (1 / years) - 1)
    return cagr / max_drawdown_pct


def calculate_volatility(
    returns: Sequence[float],
    periods_per_year: int = BARS_PER_YEAR_1M,
) -> float:
    """Calculate annualized volatility."""
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0.0

    return std_dev * math.sqrt(periods_per_year)


def calculate_trade_metrics(trades: Sequence[TradeRecord]) -> dict[str, float]:
    """Calculate trading metrics from trade records."""
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_trade_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_bars_held": 0.0,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    total_trades = len(trades)
    winning_trades = len(wins)
    losing_trades = len(losses)

    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_win = gross_profit / winning_trades if winning_trades > 0 else 0.0
    avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0.0

    # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    loss_rate = losing_trades / total_trades if total_trades > 0 else 0.0
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    largest_win = max((t.pnl for t in wins), default=0.0)
    largest_loss = min((t.pnl for t in losses), default=0.0)

    avg_bars_held = sum(t.bars_held for t in trades) / total_trades if total_trades > 0 else 0.0

    total_pnl = gross_profit - gross_loss
    avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor if profit_factor != float("inf") else 999.99,
        "expectancy": expectancy,
        "avg_trade_pnl": avg_trade_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "avg_bars_held": avg_bars_held,
    }


def calculate_exposure_metrics(
    equity_curve: Sequence[EquityPoint],
    position_flags: Sequence[bool],
) -> dict[str, float]:
    """Calculate exposure/time-in-market metrics."""
    if not equity_curve or not position_flags:
        return {
            "avg_exposure": 0.0,
            "max_exposure": 0.0,
            "time_in_market_pct": 0.0,
        }

    in_market_count = sum(1 for f in position_flags if f)
    time_in_market = in_market_count / len(position_flags) if position_flags else 0.0

    return {
        "avg_exposure": 0.0,  # Would need exposure values per bar
        "max_exposure": 0.0,
        "time_in_market_pct": time_in_market,
    }


def compute_metrics_summary(
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[TradeRecord],
    initial_cash: float,
    bot: str | None = None,
    symbol: str | None = None,
    bars_per_day: int = BARS_PER_DAY_1M,
) -> MetricsSummary:
    """
    Compute complete metrics summary.

    Args:
        equity_curve: Sequence of equity points
        trades: Sequence of trade records
        initial_cash: Starting capital
        bot: Optional bot identifier
        symbol: Optional symbol filter
        bars_per_day: Number of bars per trading day (for annualization)

    Returns:
        MetricsSummary with all computed metrics
    """
    # Filter trades by bot/symbol if specified
    filtered_trades = list(trades)
    if bot:
        filtered_trades = [t for t in filtered_trades if t.bot == bot]
    if symbol:
        filtered_trades = [t for t in filtered_trades if t.symbol == symbol]

    # Calculate returns
    returns = calculate_returns(equity_curve)

    # Total return
    final_equity = equity_curve[-1].equity if equity_curve else initial_cash
    total_return = final_equity - initial_cash
    total_return_pct = total_return / initial_cash if initial_cash > 0 else 0.0

    # Annualization
    bars_per_year = bars_per_day * 252
    num_bars = len(equity_curve)
    years = num_bars / bars_per_year if bars_per_year > 0 else 1.0
    years = max(years, 1 / 365)  # At least 1 day

    # CAGR
    cagr = (final_equity / initial_cash) ** (1 / years) - 1 if initial_cash > 0 and years > 0 else 0.0

    # Risk metrics
    sharpe = calculate_sharpe_ratio(returns, periods_per_year=bars_per_year)
    sortino = calculate_sortino_ratio(returns, periods_per_year=bars_per_year)
    max_dd, max_dd_pct, max_dd_duration = calculate_max_drawdown(equity_curve)
    calmar = calculate_calmar_ratio(total_return_pct, max_dd_pct, years)
    volatility = calculate_volatility(returns, periods_per_year=bars_per_year)

    # Trade metrics
    trade_metrics = calculate_trade_metrics(filtered_trades)

    # Time in market (approximation: bars with open positions)
    # This would need position tracking per bar for accuracy
    time_in_market = 0.0
    if filtered_trades and equity_curve:
        total_bars_held = sum(t.bars_held for t in filtered_trades)
        time_in_market = total_bars_held / num_bars if num_bars > 0 else 0.0

    return MetricsSummary(
        bot=bot,
        symbol=symbol,
        total_return=total_return,
        total_return_pct=total_return_pct,
        annualized_return=cagr,
        cagr=cagr,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration_bars=max_dd_duration,
        volatility=volatility,
        total_trades=trade_metrics["total_trades"],
        winning_trades=trade_metrics["winning_trades"],
        losing_trades=trade_metrics["losing_trades"],
        win_rate=trade_metrics["win_rate"],
        profit_factor=trade_metrics["profit_factor"],
        expectancy=trade_metrics["expectancy"],
        avg_trade_pnl=trade_metrics["avg_trade_pnl"],
        avg_win=trade_metrics["avg_win"],
        avg_loss=trade_metrics["avg_loss"],
        largest_win=trade_metrics["largest_win"],
        largest_loss=trade_metrics["largest_loss"],
        avg_bars_held=trade_metrics["avg_bars_held"],
        time_in_market_pct=time_in_market,
    )
