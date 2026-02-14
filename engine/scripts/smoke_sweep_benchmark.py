#!/usr/bin/env python3
"""
Smoke sweep benchmark — measures cache ON vs OFF performance.

Runs 9 bots × N symbols × 2 TFs sequentially with a single worker,
timing total execution and per-combo averages.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import UTC, datetime

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig, SizingMethod
from solat_engine.data.parquet_store import ParquetStore

DATA_DIR = Path(__file__).parent.parent / "data"
ARTEFACTS_DIR = DATA_DIR / "runs"
ARTEFACTS_DIR.mkdir(parents=True, exist_ok=True)

# Config
BOTS = [
    "TKCrossSniper", "KumoBreaker", "ChikouConfirmer", "KijunBouncer",
    "CloudTwist", "MomentumRider", "TrendSurfer", "ReversalHunter",
    "ChikouKaizen",
]
SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "NZDUSD", "USDCHF",
]
TIMEFRAMES = ["1h", "4h"]

START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 12, 31, tzinfo=UTC)


def run_sweep(store: ParquetStore, label: str) -> dict:
    """Run full sweep and return timing results."""
    total_combos = len(BOTS) * len(SYMBOLS) * len(TIMEFRAMES)
    print(f"\n{'='*60}")
    print(f"SWEEP: {label}")
    print(f"  Combos: {total_combos} ({len(BOTS)} bots × {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} TFs)")
    print(f"{'='*60}")

    results = []
    succeeded = 0
    failed = 0
    zero_trades = 0
    rejected_orders = 0

    sweep_start = time.monotonic()

    for tf in TIMEFRAMES:
        for symbol in SYMBOLS:
            for bot in BOTS:
                combo_start = time.monotonic()
                try:
                    engine = BacktestEngineV1(store, ARTEFACTS_DIR)
                    request = BacktestRequest(
                        bots=[bot],
                        symbols=[symbol],
                        timeframe=tf,
                        start=START,
                        end=END,
                        initial_cash=10000.0,
                        risk=RiskConfig(
                            sizing_method=SizingMethod.FIXED_SIZE,
                            fixed_size=1.0,
                            max_open_positions=3,
                        ),
                    )
                    result = engine.run(request)
                    combo_time = time.monotonic() - combo_start

                    # Extract metrics
                    sharpe = 0.0
                    trades = 0
                    rej = 0
                    if result.per_bot_results:
                        m = result.per_bot_results[0].metrics
                        sharpe = m.sharpe_ratio
                        trades = m.total_trades
                        rej = m.rejected_orders

                    if trades == 0:
                        zero_trades += 1
                    rejected_orders += rej
                    succeeded += 1

                    results.append({
                        "bot": bot, "symbol": symbol, "tf": tf,
                        "sharpe": sharpe, "trades": trades,
                        "rejected": rej, "time_s": combo_time,
                    })

                    status = f"Sharpe={sharpe:7.2f} trades={trades:3d} rej={rej:2d}"
                    print(f"  {bot:18s} {symbol:8s} {tf:3s} {combo_time:5.1f}s {status}")

                except Exception as e:
                    combo_time = time.monotonic() - combo_start
                    failed += 1
                    print(f"  {bot:18s} {symbol:8s} {tf:3s} {combo_time:5.1f}s FAILED: {e}")
                    results.append({
                        "bot": bot, "symbol": symbol, "tf": tf,
                        "sharpe": 0, "trades": 0, "rejected": 0,
                        "time_s": combo_time, "error": str(e),
                    })

    sweep_time = time.monotonic() - sweep_start

    # Summary
    combo_times = [r["time_s"] for r in results]
    avg_time = sum(combo_times) / len(combo_times) if combo_times else 0

    print(f"\n--- {label} Summary ---")
    print(f"  Total time:       {sweep_time:.1f}s ({sweep_time/60:.1f} min)")
    print(f"  Avg per combo:    {avg_time:.2f}s")
    print(f"  Succeeded:        {succeeded}/{total_combos}")
    print(f"  Failed:           {failed}")
    print(f"  Zero-trade bots:  {zero_trades}")
    print(f"  Total rejections: {rejected_orders}")

    return {
        "label": label,
        "total_time_s": sweep_time,
        "avg_combo_s": avg_time,
        "succeeded": succeeded,
        "failed": failed,
        "zero_trades": zero_trades,
        "rejected_orders": rejected_orders,
        "results": results,
    }


def main():
    store = ParquetStore(DATA_DIR)

    # Run 1: Cache ON (default)
    cache_on = run_sweep(store, "Cache ON")

    # Clear cache for fair comparison
    store.clear_cache()

    # Run 2: Cache OFF (clear between every combo)
    # Patch the store to clear cache after each read
    original_read = store._read_partition_df

    def no_cache_read(*args, **kwargs):
        kwargs["use_cache"] = False
        return original_read(*args, **kwargs)

    store._read_partition_df = no_cache_read
    cache_off = run_sweep(store, "Cache OFF")

    # Restore
    store._read_partition_df = original_read

    # Final comparison
    speedup = cache_off["total_time_s"] / cache_on["total_time_s"] if cache_on["total_time_s"] > 0 else 1.0

    print(f"\n{'='*60}")
    print("BENCHMARK COMPARISON")
    print(f"{'='*60}")
    print(f"  Cache ON:   {cache_on['total_time_s']:.1f}s ({cache_on['total_time_s']/60:.1f} min)")
    print(f"  Cache OFF:  {cache_off['total_time_s']:.1f}s ({cache_off['total_time_s']/60:.1f} min)")
    print(f"  Speedup:    {speedup:.2f}x")

    # Top performers
    all_results = cache_on["results"]
    valid = [r for r in all_results if r.get("trades", 0) > 0 and "error" not in r]
    valid.sort(key=lambda x: -x["sharpe"])

    print(f"\n--- Top 10 Performers ---")
    for r in valid[:10]:
        print(f"  {r['bot']:18s} {r['symbol']:8s} {r['tf']:3s} Sharpe={r['sharpe']:7.2f} trades={r['trades']:3d}")

    return cache_on, cache_off


if __name__ == "__main__":
    cache_on, cache_off = main()
