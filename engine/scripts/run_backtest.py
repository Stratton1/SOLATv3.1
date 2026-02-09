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


def run_single_backtest(
    bot: str,
    symbols: list[str],
    timeframe: str = "1h",
    start_date: str = "2023-01-01",
    end_date: str = "2025-12-31",
    initial_cash: float = 100000.0,
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

    request = BacktestRequest(
        bots=[bot],
        symbols=symbols,
        timeframe=timeframe,
        start=start_dt,
        end=end_dt,
        initial_cash=initial_cash,
        risk=RiskConfig(position_size_pct=2.0, max_positions=3),
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

            metrics = result["metrics"]
            sharpe = metrics.get("sharpe_ratio", 0)
            total_return = metrics.get("total_return_pct", 0)
            win_rate = metrics.get("win_rate", 0)
            trades = result["total_trades"]

            status = "✅" if sharpe > 1.0 else "⚠️"
            print(f"{status} {bot:20} | Sharpe: {sharpe:6.2f} | Return: {total_return:6.1f}% | Win: {win_rate*100:5.1f}% | Trades: {trades}")

        except Exception as e:
            print(f"❌ {bot}: Error - {e}")
            results.append({"bot": bot, "error": str(e)})

    return {"results": results, "symbols": symbols, "timeframe": timeframe}


def main():
    parser = argparse.ArgumentParser(description="Run SOLAT backtests")
    parser.add_argument("--bot", help="Bot name to run")
    parser.add_argument("--symbols", nargs="+", default=["EURUSD"], help="Symbols to trade")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--start", default="2023-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
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
            print(f"  ✅ {bot}: {sharpe:.2f}")

    elif args.bot:
        result = run_single_backtest(
            bot=args.bot,
            symbols=args.symbols,
            timeframe=args.timeframe,
            start_date=args.start,
            end_date=args.end,
        )

        print(f"\nBot: {result['bot']}")
        print(f"Run ID: {result['run_id']}")
        print(f"Total Trades: {result['total_trades']}")
        print(f"\nMetrics:")
        for key, value in result["metrics"].items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
