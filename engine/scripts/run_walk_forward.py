#!/usr/bin/env python3
"""
Walk-Forward Optimization Runner.

Usage:
    python scripts/run_walk_forward.py --symbols EURUSD GBPUSD --bots TKCrossSniper KumoBreaker
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from solat_engine.data.parquet_store import ParquetStore
from solat_engine.optimization.models import (
    OptimizationMode,
    WalkForwardConfig,
    WindowType,
)
from solat_engine.optimization.walk_forward import WalkForwardEngine


async def run_walk_forward(
    symbols: list[str],
    bots: list[str],
    timeframe: str = "1h",
    start_date: str = "2023-01-01",
    end_date: str = "2024-12-31",
    in_sample_days: int = 180,
    out_of_sample_days: int = 60,
    step_days: int = 60,
) -> dict:
    """Run walk-forward optimization."""
    script_dir = Path(__file__).parent.parent
    data_dir = script_dir / "data"

    store = ParquetStore(data_dir)
    engine = WalkForwardEngine(parquet_store=store)

    # Parse dates
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)

    config = WalkForwardConfig(
        symbols=symbols,
        bots=bots,
        timeframes=[timeframe],
        start_date=start_dt,
        end_date=end_dt,
        window_type=WindowType.ROLLING,
        in_sample_days=in_sample_days,
        out_of_sample_days=out_of_sample_days,
        step_days=step_days,
        optimization_mode=OptimizationMode.SHARPE,
        top_n=10,
        min_trades=5,
        max_drawdown_pct=25.0,
        min_sharpe=0.0,
    )

    print(f"Walk-Forward Config:")
    print(f"  Symbols: {symbols}")
    print(f"  Bots: {bots}")
    print(f"  Timeframe: {timeframe}")
    print(f"  Date Range: {start_date} to {end_date}")
    print(f"  In-Sample: {in_sample_days} days")
    print(f"  Out-of-Sample: {out_of_sample_days} days")
    print(f"  Step: {step_days} days")
    print()

    result = await engine.run(config)

    return {
        "run_id": result.run_id,
        "status": result.status,
        "total_windows": result.total_windows,
        "completed_windows": result.completed_windows,
        "aggregate_sharpe": result.aggregate_sharpe,
        "aggregate_return_pct": result.aggregate_return_pct,
        "aggregate_win_rate": result.aggregate_win_rate,
        "aggregate_trades": result.aggregate_trades,
        "message": result.message,
    }


def main():
    parser = argparse.ArgumentParser(description="Run walk-forward optimization")
    parser.add_argument("--symbols", nargs="+", default=["EURUSD"], help="Symbols to optimize")
    parser.add_argument("--bots", nargs="+", default=["TKCrossSniper"], help="Bots to test")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--start", default="2023-01-01", help="Start date")
    parser.add_argument("--end", default="2024-12-31", help="End date")
    parser.add_argument("--is-days", type=int, default=180, help="In-sample days")
    parser.add_argument("--oos-days", type=int, default=60, help="Out-of-sample days")
    parser.add_argument("--step-days", type=int, default=60, help="Step days")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"WALK-FORWARD OPTIMIZATION - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    result = asyncio.run(run_walk_forward(
        symbols=args.symbols,
        bots=args.bots,
        timeframe=args.timeframe,
        start_date=args.start,
        end_date=args.end,
        in_sample_days=args.is_days,
        out_of_sample_days=args.oos_days,
        step_days=args.step_days,
    ))

    print(f"\n{'='*60}")
    print("WALK-FORWARD RESULTS")
    print(f"{'='*60}")
    print(f"Run ID: {result['run_id']}")
    print(f"Status: {result['status']}")
    print(f"Windows: {result['completed_windows']}/{result['total_windows']}")

    if result["aggregate_sharpe"] is not None:
        print(f"\nAggregate OOS Metrics:")
        print(f"  Sharpe:   {result['aggregate_sharpe']:.2f}")
        print(f"  Return:   {result['aggregate_return_pct']:.2f}%")
        print(f"  Win Rate: {result['aggregate_win_rate']:.2%}" if result['aggregate_win_rate'] else "")
        print(f"  Trades:   {result['aggregate_trades']}")

    if result["message"]:
        print(f"\nMessage: {result['message']}")


if __name__ == "__main__":
    main()
