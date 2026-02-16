#!/usr/bin/env python3
"""
Smoke sweep benchmark — measures cache ON vs OFF performance.

Runs 9 bots × N symbols × 2 TFs sequentially with a single worker,
timing total execution and per-combo averages.

Outputs canonical Markdown + CSV + JSON report via the shared reporting module.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import UTC, datetime

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest, RiskConfig, SizingMethod
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.reporting.sweep_report import (
    ComboResultRow,
    SweepReportMetadata,
    generate_sweep_report,
    row_from_metrics_summary,
)

DATA_DIR = Path(__file__).parent.parent / "data"
ARTEFACTS_DIR = DATA_DIR / "runs"
ARTEFACTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = DATA_DIR / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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


def run_sweep(store: ParquetStore, label: str) -> tuple[dict, list[ComboResultRow]]:
    """Run full sweep and return timing results + canonical rows."""
    total_combos = len(BOTS) * len(SYMBOLS) * len(TIMEFRAMES)
    print(f"\n{'='*60}")
    print(f"SWEEP: {label}")
    print(f"  Combos: {total_combos} ({len(BOTS)} bots × {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} TFs)")
    print(f"{'='*60}")

    rows: list[ComboResultRow] = []
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

                    # Build canonical row from MetricsSummary
                    if result.per_bot_results:
                        m = result.per_bot_results[0].metrics
                        row = row_from_metrics_summary(
                            m,
                            bot=bot,
                            symbol=symbol,
                            timeframe=tf,
                            pass_id=label,
                            run_id=result.run_id,
                            combo_id=f"{bot}_{symbol}_{tf}",
                            runtime_s=combo_time,
                            success=True,
                        )
                    else:
                        row = ComboResultRow(
                            bot=bot, symbol=symbol, timeframe=tf,
                            pass_id=label, combo_id=f"{bot}_{symbol}_{tf}",
                            success=True, runtime_s=combo_time,
                        )

                    rows.append(row)

                    if row.trades == 0:
                        zero_trades += 1
                    rejected_orders += row.rejected_orders
                    succeeded += 1

                    status = f"Sharpe={row.sharpe:7.2f} trades={row.trades:3d} rej={row.rejected_orders:2d}"
                    print(f"  {bot:18s} {symbol:8s} {tf:3s} {combo_time:5.1f}s {status}")

                except Exception as e:
                    combo_time = time.monotonic() - combo_start
                    failed += 1
                    print(f"  {bot:18s} {symbol:8s} {tf:3s} {combo_time:5.1f}s FAILED: {e}")
                    rows.append(ComboResultRow(
                        bot=bot, symbol=symbol, timeframe=tf,
                        pass_id=label, combo_id=f"{bot}_{symbol}_{tf}",
                        success=False, error=str(e)[:200],
                        runtime_s=combo_time,
                    ))

    sweep_time = time.monotonic() - sweep_start
    avg_time = sweep_time / len(rows) if rows else 0

    print(f"\n--- {label} Summary ---")
    print(f"  Total time:       {sweep_time:.1f}s ({sweep_time/60:.1f} min)")
    print(f"  Avg per combo:    {avg_time:.2f}s")
    print(f"  Succeeded:        {succeeded}/{total_combos}")
    print(f"  Failed:           {failed}")
    print(f"  Zero-trade bots:  {zero_trades}")
    print(f"  Total rejections: {rejected_orders}")

    stats = {
        "label": label,
        "total_time_s": sweep_time,
        "avg_combo_s": avg_time,
        "succeeded": succeeded,
        "failed": failed,
        "zero_trades": zero_trades,
        "rejected_orders": rejected_orders,
    }

    return stats, rows


def main():
    store = ParquetStore(DATA_DIR)

    # Run 1: Cache ON (default)
    cache_on_stats, cache_on_rows = run_sweep(store, "cache_on")

    # Clear cache for fair comparison
    store.clear_cache()

    # Run 2: Cache OFF (clear between every combo)
    original_read = store._read_partition_df

    def no_cache_read(*args, **kwargs):
        kwargs["use_cache"] = False
        return original_read(*args, **kwargs)

    store._read_partition_df = no_cache_read
    cache_off_stats, cache_off_rows = run_sweep(store, "cache_off")

    # Restore
    store._read_partition_df = original_read

    # Final comparison
    speedup = (
        cache_off_stats["total_time_s"] / cache_on_stats["total_time_s"]
        if cache_on_stats["total_time_s"] > 0 else 1.0
    )

    print(f"\n{'='*60}")
    print("BENCHMARK COMPARISON")
    print(f"{'='*60}")
    print(f"  Cache ON:   {cache_on_stats['total_time_s']:.1f}s "
          f"({cache_on_stats['total_time_s']/60:.1f} min)")
    print(f"  Cache OFF:  {cache_off_stats['total_time_s']:.1f}s "
          f"({cache_off_stats['total_time_s']/60:.1f} min)")
    print(f"  Speedup:    {speedup:.2f}x")

    # Generate canonical report (both passes combined)
    all_rows = cache_on_rows + cache_off_rows
    metadata = SweepReportMetadata(
        sweep_name="Smoke Sweep Benchmark — Cache ON vs OFF",
        dataset=f"2024 FX ({len(SYMBOLS)} pairs, {len(TIMEFRAMES)} TFs)",
        grid_description=f"{len(BOTS)} bots × {len(SYMBOLS)} symbols × {len(TIMEFRAMES)} TFs × 2 passes",
        bots=BOTS,
        symbols=SYMBOLS,
        timeframes=TIMEFRAMES,
        passes=["cache_on", "cache_off"],
        date_start="2024-01-01",
        date_end="2024-12-31",
        notes=f"Speedup: {speedup:.2f}x",
    )

    outputs = generate_sweep_report(
        all_rows, metadata, OUTPUT_DIR,
        top_n=20, include_full_table=True,
    )

    print(f"\n{'='*60}")
    print("REPORT FILES")
    print(f"{'='*60}")
    for fmt, path in outputs.items():
        print(f"  {fmt}: {path}")
    print(f"{'='*60}\n")

    return cache_on_stats, cache_off_stats


if __name__ == "__main__":
    main()
