#!/usr/bin/env python3
"""
Quick backtest runner for SOLAT strategies.

Usage:
    python scripts/run_backtest.py --bot TKCrossSniper --symbols EURUSD
    python scripts/run_backtest.py --sweep  # Run all 8 bots
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig
from solat_engine.data.parquet_store import ParquetStore


def print_metrics_report(m: dict) -> None:
    """Print standardized A-F metrics report from a MetricsSummary dict."""
    w = 60
    print(f"\n{'='*w}")
    print("BACKTEST METRICS REPORT (A-F)")
    print(f"{'='*w}")

    # A. Run Metadata
    print(f"\n--- A. Run Metadata {'—'*38}")
    print(f"  Run ID:           {m.get('run_id', 'N/A')}")
    print(f"  Bot:              {m.get('bot', 'N/A')}")
    print(f"  Symbol:           {m.get('symbol', 'N/A')}")
    print(f"  Timeframe:        {m.get('timeframe', 'N/A')}")
    ds = m.get('data_start')
    de = m.get('data_end')
    print(f"  Data Start:       {ds[:10] if ds else 'N/A'}")
    print(f"  Data End:         {de[:10] if de else 'N/A'}")
    print(f"  Bar Count:        {m.get('bar_count', 0):,}")
    print(f"  Initial Cash:     {m.get('initial_cash', 0):,.2f}")
    print(f"  Commission:       {m.get('commission_model', 'flat')}")
    print(f"  Spread Model:     {m.get('spread_model', 'fixed')}")
    print(f"  Slippage Model:   {m.get('slippage_model', 'fixed')}")

    # B. Trade Summary
    print(f"\n--- B. Trade Summary {'—'*37}")
    print(f"  Total Trades:     {m.get('total_trades', 0)}")
    print(f"  Winning:          {m.get('winning_trades', 0)}")
    print(f"  Losing:           {m.get('losing_trades', 0)}")
    print(f"  Win Rate:         {m.get('win_rate', 0)*100:.1f}%")
    print(f"  Long Trades:      {m.get('long_trades', 0)}")
    print(f"  Short Trades:     {m.get('short_trades', 0)}")
    print(f"  Profit Factor:    {m.get('profit_factor', 0):.2f}")
    print(f"  Expectancy:       {m.get('expectancy', 0):.2f}")
    print(f"  Payoff Ratio:     {m.get('payoff_ratio', 0):.2f}")
    print(f"  Avg Win:          {m.get('avg_win', 0):.2f}")
    print(f"  Avg Loss:         {m.get('avg_loss', 0):.2f}")
    print(f"  Avg Trade PnL:    {m.get('avg_trade_pnl', 0):.2f}")
    print(f"  Largest Win:      {m.get('largest_win', 0):.2f}")
    print(f"  Largest Loss:     {m.get('largest_loss', 0):.2f}")
    print(f"  Median Return %:  {m.get('median_trade_return_pct', 0)*100:.4f}%")
    print(f"  Avg Bars Held:    {m.get('avg_bars_held', 0):.1f}")
    print(f"  Median Bars Held: {m.get('median_bars_held', 0):.1f}")
    print(f"  Max Consec Wins:  {m.get('max_consecutive_wins', 0)}")
    print(f"  Max Consec Losses:{m.get('max_consecutive_losses', 0)}")

    # C. Equity / Performance
    print(f"\n--- C. Equity / Performance {'—'*30}")
    print(f"  Start Equity:     {m.get('start_equity', 0):,.2f}")
    print(f"  End Equity:       {m.get('end_equity', 0):,.2f}")
    print(f"  Total Return:     {m.get('total_return', 0):,.2f}")
    print(f"  Total Return %:   {m.get('total_return_pct', 0)*100:.4f}%")
    print(f"  CAGR:             {m.get('cagr', 0)*100:.4f}%")
    print(f"  Sharpe Ratio:     {m.get('sharpe_ratio', 0):.4f}")
    print(f"  Sortino Ratio:    {m.get('sortino_ratio', 0):.4f}")
    print(f"  Calmar Ratio:     {m.get('calmar_ratio', 0):.4f}")
    print(f"  Max Drawdown:     {m.get('max_drawdown', 0):,.2f}")
    print(f"  Max Drawdown %:   {m.get('max_drawdown_pct', 0)*100:.4f}%")
    print(f"  Max DD Duration:  {m.get('max_drawdown_duration_bars', 0)} bars")
    print(f"  Volatility:       {m.get('volatility', 0):.4f}")
    print(f"  Downside Vol:     {m.get('downside_volatility', 0):.4f}")
    print(f"  Avg Drawdown %:   {m.get('avg_drawdown_pct', 0)*100:.4f}%")
    print(f"  Avg DD Duration:  {m.get('avg_drawdown_duration_bars', 0):.1f} bars")
    print(f"  Time in Market:   {m.get('time_in_market_pct', 0)*100:.2f}%")

    # D. Risk / Distribution
    print(f"\n--- D. Risk / Distribution {'—'*31}")
    print(f"  Skewness:         {m.get('skewness', 0):.4f}")
    print(f"  Kurtosis:         {m.get('kurtosis', 0):.4f}")
    print(f"  Exp-Adj Return:   {m.get('exposure_adjusted_return', 0)*100:.4f}%")

    # E. Execution Realism
    print(f"\n--- E. Execution Realism {'—'*33}")
    print(f"  Total Orders:     {m.get('total_orders', 0)}")
    print(f"  Filled:           {m.get('filled_orders', 0)}")
    print(f"  Rejected:         {m.get('rejected_orders', 0)}")
    print(f"  Partial Fills:    {m.get('partial_fills_count', 0)}")
    print(f"  Avg Spread Paid:  {m.get('avg_spread_paid', 0):.4f}")
    print(f"  Avg Slippage:     {m.get('avg_slippage', 0):.4f}")
    print(f"  Total Spread Cost:{m.get('total_spread_cost', 0):.2f}")
    print(f"  Total Slip Cost:  {m.get('total_slippage_cost', 0):.2f}")
    print(f"  Total Fees:       {m.get('total_fees', 0):.2f}")
    print(f"  Total Txn Costs:  {m.get('total_transaction_costs', 0):.2f}")

    # F. Diagnostics / Integrity
    print(f"\n--- F. Diagnostics {'—'*39}")
    print(f"  Data Gaps:        {m.get('data_gaps_detected', 0)}")
    nan_ok = m.get('nan_inf_checks_passed', True)
    print(f"  NaN/Inf Clean:    {'PASS' if nan_ok else 'FAIL'}")
    print(f"  Warnings:         {m.get('warnings_count', 0)}")

    print(f"\n{'='*w}")


def run_single_backtest(
    bot: str,
    symbols: list[str],
    timeframe: str = "1h",
    start_date: str = "2023-01-01",
    end_date: str = "2025-12-31",
    initial_cash: float = 10000.0,
    fixed_size: float | None = None,
    risk_per_trade_pct: float = 2.0,
    max_positions: int = 3,
) -> dict:
    """Run a single bot backtest."""
    # Use absolute paths from script location
    script_dir = Path(__file__).parent.parent
    data_dir = script_dir / "data"  # Root data dir - ParquetStore appends parquet/bars
    artefacts_dir = script_dir / "data" / "runs"
    artefacts_dir.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(data_dir)
    engine = BacktestEngineV1(store, artefacts_dir)

    # Parse dates
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)

    from solat_engine.backtest.models import SizingMethod

    risk = RiskConfig(
        sizing_method=SizingMethod.FIXED_SIZE if fixed_size else SizingMethod.RISK_PER_TRADE,
        fixed_size=fixed_size or 1.0,
        risk_per_trade_pct=risk_per_trade_pct,
        max_open_positions=max_positions
    )

    request = BacktestRequest(
        bots=[bot],
        symbols=symbols,
        timeframe=timeframe,
        start=start_dt,
        end=end_dt,
        initial_cash=initial_cash,
        risk=risk,
    )

    result = engine.run(request)

    # Get first bot's results
    bot_metrics = {}
    trades_count = 0
    if result.per_bot_results:
        for br in result.per_bot_results:
            if br.bot == bot:
                bot_metrics = br.metrics.model_dump()
                trades_count = br.trades_count
                break

    return {
        "bot": bot,
        "metrics": bot_metrics,
        "total_trades": trades_count,
        "run_id": result.run_id,
        "warnings": result.warnings,
    }


def run_sweep(
    symbols: list[str] | None = None,
    timeframe: str = "1h",
    start_date: str = "2023-01-01",
    end_date: str = "2025-12-31",
) -> dict:
    """Run all 8 bots."""
    bots = [
        "TKCrossSniper",
        "KumoBreaker",
        "ChikouConfirmer",
        "KijunBouncer",
        "CloudTwist",
        "MomentumRider",
        "TrendSurfer",
        "ReversalHunter",
    ]

    if symbols is None:
        # Core FX pairs
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

    results = []
    for bot in bots:
        print(f"\n{'='*60}")
        print(f"Running: {bot}")
        print(f"{'='*60}")

        try:
            result = run_single_backtest(
                bot=bot,
                symbols=symbols,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )
            results.append(result)

            # Print full A-F report for each bot
            print_metrics_report(result["metrics"])

        except Exception as e:
            print(f"ERROR {bot}: {e}")
            results.append({"bot": bot, "error": str(e)})

    return {"results": results, "symbols": symbols, "timeframe": timeframe}


def main():
    parser = argparse.ArgumentParser(description="Run SOLAT backtests")
    parser.add_argument("--bot", help="Bot name to run")
    parser.add_argument("--symbols", nargs="+", default=["EURUSD"], help="Symbols to trade")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--start", default="2023-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    parser.add_argument("--initial-cash", type=float, default=10000.0, help="Initial cash")
    parser.add_argument("--fixed-size", type=float, help="Fixed lot size (overrides percentage sizing)")
    parser.add_argument("--risk-pct", type=float, default=2.0, help="Risk percentage per trade")
    parser.add_argument("--max-pos", type=int, default=3, help="Max concurrent positions")
    parser.add_argument("--sweep", action="store_true", help="Run all 8 bots")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"SOLAT BACKTEST - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    if args.sweep:
        sweep_results = run_sweep(
            symbols=args.symbols if args.symbols != ["EURUSD"] else None,
            timeframe=args.timeframe,
            start_date=args.start,
            end_date=args.end,
        )

        # Summary
        print(f"\n{'='*60}")
        print("SWEEP SUMMARY")
        print(f"{'='*60}")

        good_bots = []
        for r in sweep_results["results"]:
            if "error" not in r:
                sharpe = r["metrics"].get("sharpe_ratio", 0)
                if sharpe > 1.0:
                    good_bots.append((r["bot"], sharpe))

        print(f"Bots with Sharpe > 1.0: {len(good_bots)}/8")
        for bot, sharpe in sorted(good_bots, key=lambda x: -x[1]):
            print(f"  {bot}: {sharpe:.2f}")

    elif args.bot:
        result = run_single_backtest(
            bot=args.bot,
            symbols=args.symbols,
            timeframe=args.timeframe,
            start_date=args.start,
            end_date=args.end,
            initial_cash=args.initial_cash,
            fixed_size=args.fixed_size,
            risk_per_trade_pct=args.risk_pct,
            max_positions=args.max_pos,
        )

        # Print full A-F report
        print_metrics_report(result["metrics"])

        if result["warnings"]:
            print(f"\nWarnings ({len(result['warnings'])}):")
            for w in result["warnings"][:10]:
                print(f"  - {w}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
