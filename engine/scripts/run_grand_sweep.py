#!/usr/bin/env python3
"""
Grand Sweep Backtest Runner.

Runs all Elite 8 strategies on all pairs across all timeframes.
Outputs results to a CSV for analysis.
"""

import sys
from pathlib import Path

# Python 3.10 compatibility shim for datetime.UTC (introduced in 3.11)
import datetime as _dt
if not hasattr(_dt, 'UTC'):
    _dt.UTC = _dt.timezone.utc

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime
from typing import Any

import pandas as pd

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, SweepRequest
from solat_engine.backtest.sweep import GrandSweep
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.strategies.elite8 import get_available_bots

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = DATA_DIR / "sweep_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# 10 LIVE-ready FX pairs (priority)
LIVE_FX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
]

# All available symbols
ALL_SYMBOLS = [
    # Major FX
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Cross FX
    "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCAD", "EURCHF", "EURNZD",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPNZD",
    "AUDJPY", "AUDNZD", "AUDCAD", "AUDCHF",
    "NZDJPY", "NZDCAD", "NZDCHF",
    "CADJPY", "CADCHF", "CHFJPY",
    # Commodities
    "GOLD", "SILVER",
    # Indices
    "SP500", "NASDAQ", "DAX", "FTSE100", "NIKKEI", "ASX200", "HSI",
]

# Timeframes (Ichimoku works best on 1h and 4h)
TIMEFRAMES = ["1h", "4h"]  # Focus on higher timeframes for Ichimoku
# TIMEFRAMES = ["5m", "15m", "1h", "4h"]  # Full set

# Elite 8 bots
ELITE_8_BOTS = get_available_bots()


def run_sweep(
    symbols: list[str],
    bots: list[str],
    timeframes: list[str],
    start_date: str = "2023-01-01",
    end_date: str = "2025-12-31",
    max_combos: int | None = None,
) -> pd.DataFrame:
    """Run grand sweep and return results as DataFrame."""
    # Parse dates
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=_dt.UTC)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=_dt.UTC)

    total_combos = len(bots) * len(symbols) * len(timeframes)
    if max_combos is not None:
        total_combos = min(total_combos, max_combos)

    print(f"\n{'='*60}")
    print(f"GRAND SWEEP - {datetime.now().isoformat()}")
    print(f"{'='*60}")
    print(f"Bots: {len(bots)} - {', '.join(bots)}")
    print(f"Symbols: {len(symbols)}")
    print(f"Timeframes: {timeframes}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Total combinations: {total_combos}" + (" (capped)" if max_combos else ""))
    print(f"{'='*60}\n")

    store = ParquetStore(DATA_DIR)

    results = []
    total = len(bots) * len(symbols) * len(timeframes)
    completed = 0

    for tf in timeframes:
        for symbol in symbols:
            for bot in bots:
                if max_combos is not None and completed >= max_combos:
                    return pd.DataFrame(results)
                completed += 1
                combo_id = f"{bot}/{symbol}/{tf}"

                try:
                    # Create request
                    request = BacktestRequest(
                        symbols=[symbol],
                        bots=[bot],
                        timeframe=tf,
                        start=start_dt,
                        end=end_dt,
                    )

                    # Run backtest
                    engine = BacktestEngineV1(
                        parquet_store=store,
                        artefacts_dir=DATA_DIR,
                    )
                    result = engine.run(request)

                    # Extract metrics
                    metrics = result.combined_metrics
                    if metrics:
                        row = {
                            "bot": bot,
                            "symbol": symbol,
                            "timeframe": tf,
                            "total_trades": metrics.total_trades,
                            "win_rate": round(metrics.win_rate * 100, 2) if metrics.win_rate else 0,
                            "sharpe": round(metrics.sharpe_ratio, 3) if metrics.sharpe_ratio else 0,
                            "sortino": round(metrics.sortino_ratio, 3) if metrics.sortino_ratio else 0,
                            "max_drawdown": round(metrics.max_drawdown_pct * 100, 2) if metrics.max_drawdown_pct else 0,
                            "total_return": round(metrics.total_return * 100, 2) if metrics.total_return else 0,
                            "profit_factor": round(metrics.profit_factor, 3) if metrics.profit_factor else 0,
                            "avg_trade_pnl": round(metrics.avg_trade_pnl, 4) if metrics.avg_trade_pnl else 0,
                            "ok": result.ok,
                            "errors": len(result.errors),
                        }
                        results.append(row)

                        # Progress
                        status = "✅" if metrics.sharpe_ratio and metrics.sharpe_ratio > 0 else "⚠️"
                        sharpe_val = metrics.sharpe_ratio or 0
                        print(f"[{completed}/{total}] {status} {combo_id}: {metrics.total_trades} trades, Sharpe={sharpe_val:.3f}")
                    else:
                        results.append({
                            "bot": bot,
                            "symbol": symbol,
                            "timeframe": tf,
                            "total_trades": 0,
                            "ok": False,
                            "errors": 1,
                        })
                        print(f"[{completed}/{total}] ❌ {combo_id}: No metrics")

                except Exception as e:
                    results.append({
                        "bot": bot,
                        "symbol": symbol,
                        "timeframe": tf,
                        "total_trades": 0,
                        "ok": False,
                        "errors": 1,
                        "error_msg": str(e)[:100],
                    })
                    print(f"[{completed}/{total}] ❌ {combo_id}: {str(e)[:50]}")

    return pd.DataFrame(results)


def main():
    """Run the grand sweep."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Run Grand Sweep backtest")
    parser.add_argument("--scope", choices=["live", "all", "mini"], default="live",
                       help="Scope: live=10 FX pairs, all=37 instruments, mini=quick test")
    parser.add_argument("--timeframes", nargs="+", default=["1h", "4h"],
                       help="Timeframes to test (e.g. 1h 4h or 30m)")
    parser.add_argument("--max-combos", type=int, default=None,
                       help="Cap total combinations (for sanity runs); default no cap")
    args = parser.parse_args()

    # Require Python 3.11+ for heavy sweep (CPU/parallelism)
    if sys.version_info < (3, 11):
        print("WARNING: Python 3.11+ recommended for sweep (current: %s)" % sys.version.split()[0], file=sys.stderr)

    # Select symbols based on scope
    if args.scope == "mini":
        symbols = ["EURUSD", "GBPUSD"]
        bots = ["TKCrossSniper", "KumoBreaker"]
    elif args.scope == "live":
        symbols = LIVE_FX_PAIRS
        bots = ELITE_8_BOTS
    else:
        symbols = ALL_SYMBOLS
        bots = ELITE_8_BOTS

    timeframes = args.timeframes

    # Run sweep
    df = run_sweep(
        symbols=symbols,
        bots=bots,
        timeframes=timeframes,
        max_combos=args.max_combos,
    )

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"sweep_{args.scope}_{timestamp}.csv"
    df.to_csv(output_file, index=False)
    print(f"\n📁 Results saved to: {output_file}")

    # Print summary
    print(f"\n{'='*60}")
    print("SWEEP SUMMARY")
    print(f"{'='*60}")

    if len(df) > 0 and "sharpe" in df.columns:
        # Top performers by Sharpe
        top = df[df["total_trades"] >= 10].nlargest(20, "sharpe")
        if len(top) > 0:
            print("\n🏆 TOP 20 BY SHARPE (min 10 trades):")
            print(top[["bot", "symbol", "timeframe", "total_trades", "sharpe", "win_rate", "max_drawdown", "total_return"]].to_string(index=False))

        # Best bot overall
        print("\n📊 BOT PERFORMANCE (avg Sharpe where trades >= 10):")
        bot_perf = df[df["total_trades"] >= 10].groupby("bot").agg({
            "sharpe": "mean",
            "win_rate": "mean",
            "total_trades": "sum",
            "total_return": "mean",
        }).round(3).sort_values("sharpe", ascending=False)
        print(bot_perf.to_string())

        # Best symbol
        print("\n🌍 SYMBOL PERFORMANCE (avg Sharpe where trades >= 10):")
        sym_perf = df[df["total_trades"] >= 10].groupby("symbol").agg({
            "sharpe": "mean",
            "win_rate": "mean",
            "total_trades": "sum",
        }).round(3).sort_values("sharpe", ascending=False)
        print(sym_perf.head(15).to_string())

        # Best timeframe
        print("\n⏱️ TIMEFRAME PERFORMANCE:")
        tf_perf = df[df["total_trades"] >= 10].groupby("timeframe").agg({
            "sharpe": "mean",
            "win_rate": "mean",
            "total_trades": "sum",
        }).round(3).sort_values("sharpe", ascending=False)
        print(tf_perf.to_string())

    print(f"\n{'='*60}")
    print(f"Total combinations tested: {len(df)}")
    print(f"Successful: {len(df[df['ok'] == True])}")
    print(f"Failed: {len(df[df['ok'] == False])}")
    print(f"{'='*60}\n")

    return df


if __name__ == "__main__":
    main()
