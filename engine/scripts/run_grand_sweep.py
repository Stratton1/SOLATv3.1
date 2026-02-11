#!/usr/bin/env python3
"""
Grand Sweep Backtest Runner v4 — Catalogue-First.

Uses SEED_INSTRUMENTS as source of truth for symbols, supports 15m/30m
timeframes, preflights data before submitting, and generates ranked + JSON
outputs for analysis.

Outputs:
  data/sweep_results/sweep_{scope}_{timestamp}/
    results.csv         — raw results
    results.parquet     — raw results (binary)
    ranked.csv          — filtered + ranked by Sharpe
    top_picks.json      — diversified top-N for allowlist
    preflight.json      — preflight skip report
"""

import sys
from pathlib import Path

# Python 3.10 compatibility shim for datetime.UTC (introduced in 3.11)
import datetime as _dt
if not hasattr(_dt, 'UTC'):
    _dt.UTC = _dt.timezone.utc

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
import shutil
import time
from datetime import UTC, datetime, timedelta
from multiprocessing import cpu_count

import pandas as pd

from solat_engine.backtest.parallel_sweep import ParallelSweepRunner
from solat_engine.backtest.sweep_utils import (
    DEFAULT_TIMEFRAMES_ALL,
    DEFAULT_TIMEFRAMES_FULL,
    DEFAULT_TIMEFRAMES_LIVE,
    DERIVED_ONLY_TIMEFRAMES,
    LIVE_FX_PAIRS,
    auto_derive_timeframe,
    detect_broken_bots,
    discover_symbols_from_disk,
    generate_curated_allowlist,
    generate_ranked_csv,
    generate_top_picks_json,
    get_available_asset_classes,
    parse_timeframes,
    preflight_check_partition,
    resolve_symbols_from_catalogue,
)
from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.strategies.elite8_hardened import get_available_bots

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = DATA_DIR / "sweep_results"
OUTPUT_DIR.mkdir(exist_ok=True)

# Elite 8 bots
ELITE_8_BOTS = get_available_bots()


def run_preflight(
    symbols: list[str],
    timeframes: list[str],
    bots: list[str],
    data_dir: Path,
    start: datetime | None = None,
    end: datetime | None = None,
    derive_missing: bool = False,
) -> tuple[list[tuple[str, str, str]], list[dict], int]:
    """
    Preflight all (bot, symbol, timeframe) combos.

    Returns:
        (valid_combos, skip_reports, derived_count)
        - valid_combos: list of (bot, symbol, timeframe) tuples that have data
        - skip_reports: list of dicts describing skipped combos
        - derived_count: number of timeframes derived from 1m
    """
    valid_combos: list[tuple[str, str, str]] = []
    skip_reports: list[dict] = []
    derived_count = 0

    # Cache preflight results per (symbol, timeframe) to avoid redundant checks
    pf_cache: dict[tuple[str, str], bool] = {}

    for symbol in symbols:
        for tf in timeframes:
            cache_key = (symbol, tf)
            if cache_key in pf_cache:
                available = pf_cache[cache_key]
            else:
                pf = preflight_check_partition(data_dir, symbol, tf, start, end)
                available = pf.available

                # Try deriving if missing and requested
                if not available and derive_missing:
                    print(f"  Deriving {symbol}/{tf} from 1m...", end=" ", flush=True)
                    ok = auto_derive_timeframe(data_dir, symbol, tf, start, end)
                    if ok:
                        available = True
                        derived_count += 1
                        print("OK")
                    else:
                        print("SKIP (no 1m source)")

                pf_cache[cache_key] = available

            if available:
                for bot in bots:
                    valid_combos.append((bot, symbol, tf))
            else:
                # Report skip once per (symbol, tf) — applies to all bots
                pf2 = preflight_check_partition(data_dir, symbol, tf, start, end)
                skip_reports.append({
                    "symbol": symbol,
                    "storage_symbol": resolve_storage_symbol(symbol),
                    "timeframe": tf,
                    "reason": pf2.skip_reason or "NO_DATA",
                    "bar_count": pf2.bar_count,
                    "data_start": pf2.data_start,
                    "data_end": pf2.data_end,
                    "bots_skipped": len(bots),
                })

    return valid_combos, skip_reports, derived_count


def print_summary(results_csv: Path, min_trades: int, include_aggregates: bool = False) -> None:
    """Print sweep summary table from results CSV."""
    try:
        if not results_csv.exists():
            return

        df = pd.read_csv(results_csv)

        # Exclude skipped
        if "skipped" in df.columns:
            df = df[df["skipped"] != True]  # noqa: E712

        successful = df[df["success"]] if "success" in df.columns else df

        print(f"\n{'='*60}")
        print("SWEEP SUMMARY")
        print(f"{'='*60}")

        if len(successful) > 0 and "sharpe" in successful.columns:
            top = successful[successful["total_trades"] >= min_trades].nlargest(20, "sharpe")
            if len(top) > 0:
                print(f"\nTOP 20 BY SHARPE (min {min_trades} trades):")
                cols = ["bot", "symbol", "timeframe", "total_trades", "sharpe", "win_rate",
                        "max_drawdown", "pnl"]
                available = [c for c in cols if c in top.columns]
                print(top[available].to_string(index=False))

            qualified = successful[successful["total_trades"] >= min_trades]

            if include_aggregates:
                print(f"\nBOT PERFORMANCE (avg Sharpe where trades >= {min_trades}):")
                if len(qualified) > 0:
                    bot_perf = qualified.groupby("bot").agg({
                        "sharpe": "mean",
                        "win_rate": "mean",
                        "total_trades": "sum",
                    }).round(3).sort_values("sharpe", ascending=False)
                    print(bot_perf.to_string())

                print(f"\nSYMBOL PERFORMANCE (avg Sharpe where trades >= {min_trades}):")
                if len(qualified) > 0:
                    sym_perf = qualified.groupby("symbol").agg({
                        "sharpe": "mean",
                        "win_rate": "mean",
                        "total_trades": "sum",
                    }).round(3).sort_values("sharpe", ascending=False)
                    print(sym_perf.head(15).to_string())

                print(f"\nTIMEFRAME PERFORMANCE:")
                if len(qualified) > 0:
                    tf_perf = qualified.groupby("timeframe").agg({
                        "sharpe": "mean",
                        "win_rate": "mean",
                        "total_trades": "sum",
                    }).round(3).sort_values("sharpe", ascending=False)
                    print(tf_perf.to_string())

        total = len(df)
        ok = len(df[df["success"]]) if "success" in df.columns else len(df)

        # FIX: Read skipped count from preflight.json if it exists
        skipped_count = 0
        preflight_path = results_csv.parent / "preflight.json"
        if preflight_path.exists():
            try:
                with open(preflight_path) as f:
                    preflight_data = json.load(f)
                    skipped_count = preflight_data.get("skipped_combos", 0)
            except Exception:
                pass  # Silently handle preflight read errors

        print(f"\nTotal combinations tested: {total}")
        print(f"Successful: {ok}")
        print(f"Failed: {total - ok}")
        if skipped_count > 0:
            print(f"Skipped (no data): {skipped_count}")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\nWARNING: Failed to print summary: {e}", file=sys.stderr)
        print(f"Results CSV exists: {results_csv.exists()}")
        if results_csv.exists():
            print(f"{'='*60}\n")


def main():
    """Run the grand sweep using ParallelSweepRunner with catalogue-first discovery."""

    parser = argparse.ArgumentParser(
        description="Grand Sweep Backtest Runner v4.2 (all timeframes, disk discovery, auto-prune)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  # Basic scopes
  %(prog)s --scope live                              # 10 FX pairs, 1h+4h
  %(prog)s --scope all --derive-missing              # 28 instruments, 15m+30m+1h+4h
  %(prog)s --scope disk                              # Discover symbols from disk
  %(prog)s --scope mini                              # Quick smoke test

  # Full timeframe coverage (v4.2)
  %(prog)s --scope live --timeframes all              # 1m/5m/15m/30m/1h/4h
  %(prog)s --scope live --timeframes 1m 5m 15m        # Specific set
  %(prog)s --scope full --timeframes all --workers 7  # Everything

  # Curated picks with auto-prune (v4.2)
  %(prog)s --scope live --min-sharpe 1.5              # Higher quality filter
  %(prog)s --scope all --broken-bot-threshold 0.8     # Stricter broken bot detection

  # Apply allowlist to engine (v4.2)
  %(prog)s --scope live --apply-allowlist             # Generate + POST to engine

  # Advanced
  %(prog)s --asset-classes fx index --timeframes all  # FX + indices, all TFs
  %(prog)s --timeframes 15m 1h --top-n 50             # Custom TFs, top 50 picks
""",
    )
    parser.add_argument(
        "--scope", choices=["live", "all", "full", "mini", "disk"], default="live",
        help="Scope: live=10 FX pairs (1h+4h), all=28 instruments (15m+30m+1h+4h), "
             "full=alias for all, mini=quick test (2 pairs, 2 bots), "
             "disk=discover symbols from parquet directory",
    )
    parser.add_argument(
        "--max-days-back", type=int, default=None,
        help="Override --start with N days before --end (e.g. --max-days-back 365)",
    )
    parser.add_argument(
        "--asset-classes", nargs="+", default=None,
        help=f"Filter by asset class: {', '.join(get_available_asset_classes())}",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Explicit list of symbols to test (overrides --scope and --asset-classes)",
    )
    parser.add_argument(
        "--timeframes", nargs="+", default=None,
        help="Timeframes to test (e.g. 15m 30m 1h 4h). Defaults depend on scope.",
    )
    parser.add_argument(
        "--workers", type=int, default=None,
        help=f"Number of parallel workers (default: {max(1, cpu_count() - 1)})",
    )
    parser.add_argument(
        "--min-trades", type=int, default=30,
        help="Minimum trades to include in ranked output (default: 30)",
    )
    parser.add_argument(
        "--max-combos", type=int, default=None,
        help="Cap total combinations",
    )
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="Stop on first combo failure",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-run all combos even if completed",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Don't resume from checkpoint, start fresh",
    )
    parser.add_argument(
        "--start", default="2023-01-01", help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", default="2025-12-31", help="End date (YYYY-MM-DD)",
    )

    # New flags (deliverables E, F, G)
    parser.add_argument(
        "--top-n", type=int, default=30,
        help="Number of top picks in output JSON (default: 30)",
    )
    parser.add_argument(
        "--diversify-by", nargs="+", default=["symbol", "timeframe"],
        help="Columns to diversify top picks by (default: symbol timeframe). "
             "Use 'none' to disable.",
    )
    parser.add_argument(
        "--derive-missing", action="store_true",
        help="Auto-derive 15m/30m from 1m data where missing",
    )
    parser.add_argument(
        "--walk-forward", action="store_true",
        help="Include walk-forward OOS metrics in output (slower)",
    )

    # Grand Sweep v4.2 additions
    parser.add_argument(
        "--min-sharpe", type=float, default=1.0,
        help="Minimum Sharpe ratio for curated picks (default: 1.0)",
    )
    parser.add_argument(
        "--broken-bot-threshold", type=float, default=0.5,
        help="Flag bot as broken if >= this fraction of combos have 0 trades (default: 0.5)",
    )
    parser.add_argument(
        "--apply-allowlist", action="store_true",
        help="POST curated allowlist to engine /execution/allowlist endpoint (explicit only)",
    )
    parser.add_argument(
        "--include-aggregates", action="store_true",
        help="Include bot/symbol/timeframe average tables in console output (default: suppress)",
    )
    parser.add_argument(
        "--max-per-timeframe", type=int, default=None,
        help="Max combos per timeframe in curated allowlist (default: unlimited)",
    )
    args = parser.parse_args()

    # Require Python 3.11+ for heavy sweep (CPU/parallelism)
    if sys.version_info < (3, 11):
        print("WARNING: Python 3.11+ recommended for sweep (current: %s)"
              % sys.version.split()[0], file=sys.stderr)

    # =========================================================================
    # A) Symbol resolution from catalogue
    # =========================================================================
    # Normalise 'full' → 'all' (alias)
    effective_scope = "all" if args.scope == "full" else args.scope

    if args.symbols:
        symbols = args.symbols
        bots = ELITE_8_BOTS
    elif args.asset_classes:
        symbols = resolve_symbols_from_catalogue(args.asset_classes)
        if not symbols:
            print("ERROR: No symbols matched given asset classes", file=sys.stderr)
            sys.exit(1)
        bots = ELITE_8_BOTS
    elif effective_scope == "mini":
        symbols = ["EURUSD", "GBPUSD"]
        bots = ["TKCrossSniper", "KumoBreaker"]
    elif effective_scope == "live":
        symbols = LIVE_FX_PAIRS
        bots = ELITE_8_BOTS
    elif effective_scope == "disk":
        # Discover symbols from parquet directory
        symbols = discover_symbols_from_disk(DATA_DIR)
        if not symbols:
            print("ERROR: No symbols found on disk", file=sys.stderr)
            sys.exit(1)
        bots = ELITE_8_BOTS
    else:  # all / full
        symbols = resolve_symbols_from_catalogue()
        bots = ELITE_8_BOTS

    # =========================================================================
    # B) Timeframe resolution
    # =========================================================================
    if args.timeframes:
        tf_strings = args.timeframes
        # Handle "all" keyword
        if tf_strings == ["all"]:
            tf_strings = DEFAULT_TIMEFRAMES_FULL
    elif effective_scope == "all":
        tf_strings = DEFAULT_TIMEFRAMES_ALL
    elif effective_scope == "mini":
        tf_strings = ["1h"]
    elif effective_scope == "disk":
        # For disk scope, default to full timeframe set
        tf_strings = DEFAULT_TIMEFRAMES_FULL
    else:
        tf_strings = DEFAULT_TIMEFRAMES_LIVE

    # Validate timeframes
    try:
        tf_enums = parse_timeframes(tf_strings)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    timeframes = [tf.value for tf in tf_enums]
    workers = args.workers or max(1, cpu_count() - 1)

    # Parse dates
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    if args.max_days_back is not None:
        start = end - timedelta(days=args.max_days_back)
    else:
        start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)

    # =========================================================================
    # C) Preflight checks
    # =========================================================================
    print(f"\n{'='*60}")
    print(f"PARALLEL GRAND SWEEP v4 (Catalogue-First)")
    print(f"{datetime.now().isoformat()}")
    print(f"{'='*60}")
    print(f"Bots: {len(bots)} - {', '.join(bots)}")
    print(f"Symbols: {len(symbols)} (catalogue-sourced)")
    print(f"Timeframes: {timeframes}")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Derive missing: {args.derive_missing}")
    print(f"Workers: {workers}")
    print(f"Resume: {not args.no_resume}")
    print(f"{'='*60}")

    print("\nRunning data preflight checks...")
    valid_combos, skip_reports, derived_count = run_preflight(
        symbols=symbols,
        timeframes=timeframes,
        bots=bots,
        data_dir=DATA_DIR,
        start=start,
        end=end,
        derive_missing=args.derive_missing,
    )

    total_potential = len(bots) * len(symbols) * len(timeframes)
    skipped_combos = total_potential - len(valid_combos)

    print(f"\nPreflight results:")
    print(f"  Valid combos: {len(valid_combos)}")
    print(f"  Skipped: {skipped_combos} ({len(skip_reports)} symbol/tf pairs)")
    if derived_count:
        print(f"  Derived from 1m: {derived_count}")

    if not valid_combos:
        pairs_with_data = len(symbols) * len(timeframes) - len(skip_reports)
        print(f"\n{'='*60}", file=sys.stderr)
        print("DIAGNOSTICS: No valid combos found", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"  Stage 1 - Symbols discovered:          {len(symbols)}", file=sys.stderr)
        print(f"  Stage 2 - Timeframes requested:        {len(timeframes)}", file=sys.stderr)
        print(f"  Stage 3 - Total potential combos:      {total_potential}", file=sys.stderr)
        print(f"  Stage 4 - Symbol/TF pairs with data:   {pairs_with_data}"
              f" of {len(symbols) * len(timeframes)}", file=sys.stderr)
        print(f"  Stage 5 - Valid combos after preflight: 0", file=sys.stderr)

        if skip_reports:
            reason_counts: dict[str, int] = {}
            for sr in skip_reports:
                reason = sr.get("reason", "UNKNOWN")
                reason_counts[reason] = reason_counts.get(reason, 0) + sr.get("bots_skipped", 1)

            print(f"\n  Skip reasons:", file=sys.stderr)
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                print(f"    {reason}: {count} combos removed", file=sys.stderr)

            print(f"\n  Missing data locations (first 5):", file=sys.stderr)
            for sr in skip_reports[:5]:
                storage_sym = sr.get("storage_symbol", sr["symbol"])
                tf = sr["timeframe"]
                expected = f"data/parquet/bars/instrument_symbol={storage_sym}/timeframe={tf}/data.parquet"
                print(f"    {sr['symbol']}/{tf} -> {expected}", file=sys.stderr)

        print(f"\n  Suggestions:", file=sys.stderr)
        print(f"    - Sync data:      use /data/sync endpoint", file=sys.stderr)
        print(f"    - Derive from 1m: add --derive-missing flag", file=sys.stderr)
        print(f"    - Narrow scope:   --scope mini or --symbols EURUSD GBPUSD", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        sys.exit(1)

    if args.max_combos:
        valid_combos = valid_combos[:args.max_combos]

    # Build symbol/tf lists for ParallelSweepRunner from valid combos
    sweep_bots = list(dict.fromkeys(b for b, _, _ in valid_combos))
    sweep_symbols = list(dict.fromkeys(s for _, s, _ in valid_combos))
    sweep_timeframes = list(dict.fromkeys(t for _, _, t in valid_combos))

    # Map canonical symbols to storage symbols for the runner
    symbol_map = {sym: resolve_storage_symbol(sym) for sym in sweep_symbols}
    storage_symbols = [symbol_map[s] for s in sweep_symbols]

    print(f"\nStarting sweep: {len(valid_combos)} combos")
    print(f"  Bots: {len(sweep_bots)}")
    print(f"  Symbols: {len(sweep_symbols)} -> storage: {storage_symbols}")
    print(f"  Timeframes: {sweep_timeframes}")
    print(f"{'='*60}\n")

    # =========================================================================
    # Progress callback
    # =========================================================================
    last_print_time = [0.0]

    def print_progress(event: dict) -> None:
        event_type = event.get("type")
        if event_type == "sweep_started":
            print(f"Started sweep {event['sweep_id']}: "
                  f"{event['total_combos']} combos "
                  f"({event['pending']} pending, {event['skipped']} skipped)")
        elif event_type == "sweep_progress":
            now = time.time()
            if now - last_print_time[0] >= 1.0:
                last_print_time[0] = now
                eta = f"ETA: {event['eta_s']:.0f}s" if event.get("eta_s") else ""
                sharpe = (f"Sharpe={event['last_sharpe']:.3f}"
                          if event.get("last_sharpe") is not None else "")
                print(f"\r[{event['completed']}/{event['total']}] "
                      f"{event['percent']:.1f}% {event.get('last_combo', '')} "
                      f"{sharpe} {eta}    ", end="", flush=True)
        elif event_type == "sweep_completed":
            print(f"\n\nSweep {event['sweep_id']} completed: "
                  f"{event['completed']}/{event['total']} in {event['duration_s']:.1f}s")
        elif event_type == "sweep_failed":
            print(f"\n\nSweep FAILED: {event.get('error', 'unknown error')}")

    # =========================================================================
    # Run parallel sweep (uses storage symbols for parquet lookup)
    # =========================================================================
    runner = ParallelSweepRunner(
        data_dir=DATA_DIR,
        max_workers=workers,
        progress_callback=print_progress,
    )

    result = runner.run(
        bots=sweep_bots,
        symbols=storage_symbols,
        timeframes=sweep_timeframes,
        start=start,
        end=end,
        resume=not args.no_resume,
        force=args.force,
        fail_fast=args.fail_fast,
        max_combos=args.max_combos,
    )

    # =========================================================================
    # E) Generate improved outputs
    # =========================================================================
    results_csv = Path(result["results_path"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scope_label = args.scope if not args.asset_classes else "_".join(args.asset_classes)
    output_subdir = OUTPUT_DIR / f"sweep_{scope_label}_{timestamp}"
    output_subdir.mkdir(parents=True, exist_ok=True)

    # Copy raw results
    if results_csv.exists():
        shutil.copy(results_csv, output_subdir / "results.csv")

    parquet_path = result.get("results_parquet_path")
    if parquet_path and Path(parquet_path).exists():
        shutil.copy(parquet_path, output_subdir / "results.parquet")

    # Write preflight report
    elapsed_s = result.get("duration_s", 0)
    preflight_report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": args.scope,
        "effective_scope": effective_scope,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "max_days_back": args.max_days_back,
        "workers": workers,
        "derive_missing": args.derive_missing,
        "elapsed_s": elapsed_s,
        "total_potential_combos": total_potential,
        "valid_combos": len(valid_combos),
        "skipped_combos": skipped_combos,
        "derived_from_1m": derived_count,
        "bots": sweep_bots,
        "symbols": sweep_symbols,
        "timeframes": sweep_timeframes,
        "skip_details": skip_reports,
    }
    with open(output_subdir / "preflight.json", "w") as f:
        json.dump(preflight_report, f, indent=2, default=str)

    # Generate ranked.csv + top_picks.json
    if results_csv.exists():
        raw_df = pd.read_csv(results_csv)

        ranked_df = generate_ranked_csv(
            raw_df,
            output_subdir / "ranked.csv",
            min_trades=args.min_trades,
        )

        diversify = args.diversify_by
        if diversify == ["none"]:
            diversify = None

        generate_top_picks_json(
            ranked_df,
            output_subdir / "top_picks.json",
            top_n=args.top_n,
            diversify_by=diversify,
            start=args.start,
            end=args.end,
            asset_classes=args.asset_classes,
            timeframes=timeframes,
            min_trades=args.min_trades,
        )

        # Detect broken bots (v4.2)
        broken_bots_report = detect_broken_bots(
            raw_df,
            zero_trade_threshold=args.broken_bot_threshold,
        )
        with open(output_subdir / "disabled_bots.json", "w") as f:
            json.dump(broken_bots_report, f, indent=2)

        broken_bot_names = [b["bot"] for b in broken_bots_report["broken_bots"]]

        # Generate curated allowlist (v4.2)
        # Apply min_sharpe filter to ranked_df
        curated_df = ranked_df[ranked_df["sharpe"] >= args.min_sharpe].copy()

        curated_allowlist = generate_curated_allowlist(
            curated_df,
            output_subdir / "curated_allowlist.json",
            broken_bots=broken_bot_names,
            max_per_symbol=3,
            max_per_bot=5,
            max_per_timeframe=args.max_per_timeframe,
        )

        # Optionally apply allowlist to engine
        if args.apply_allowlist:
            try:
                import requests
                engine_url = "http://127.0.0.1:8765"
                resp = requests.post(
                    f"{engine_url}/execution/allowlist",
                    json=curated_allowlist["symbols"],
                    timeout=10,
                )
                if resp.status_code == 200:
                    print(f"\n✅ Applied allowlist to engine: {engine_url}/execution/allowlist")
                else:
                    print(f"\n⚠️  Failed to apply allowlist: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"\n⚠️  Failed to apply allowlist to engine: {e}")
        else:
            print(f"\nℹ️  Curated allowlist not applied. Use --apply-allowlist to apply.")

        # Post-sweep diagnostics: ranked empty but raw results exist
        if ranked_df.empty and not raw_df.empty:
            successful = raw_df[raw_df["success"] == True] if "success" in raw_df.columns else raw_df  # noqa: E712
            with_trades = successful[successful["total_trades"] >= args.min_trades] if "total_trades" in successful.columns else successful
            above_sharpe = with_trades[with_trades["sharpe"] >= args.min_sharpe] if "sharpe" in with_trades.columns else with_trades

            print(f"\n{'='*60}", file=sys.stderr)
            print("DIAGNOSTICS: All combos filtered from ranked output", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            print(f"  Raw results:                    {len(raw_df)}", file=sys.stderr)
            print(f"  Successful:                     {len(successful)}", file=sys.stderr)
            print(f"  With >= {args.min_trades} trades:             {len(with_trades)}", file=sys.stderr)
            print(f"  Above Sharpe {args.min_sharpe}:             {len(above_sharpe)}", file=sys.stderr)
            print(f"\n  Suggestions:", file=sys.stderr)
            print(f"    - Lower --min-trades (current: {args.min_trades})", file=sys.stderr)
            print(f"    - Lower --min-sharpe (current: {args.min_sharpe})", file=sys.stderr)
            if len(successful) < len(raw_df):
                print(f"    - Investigate {len(raw_df) - len(successful)} failed combos", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

        ranked_count = len(ranked_df)
        curated_count = len(curated_df)
    else:
        ranked_count = 0
        curated_count = 0
        broken_bot_names = []

    # Print summary
    print_summary(results_csv, args.min_trades, include_aggregates=args.include_aggregates)

    # Output report
    print(f"\n{'='*60}")
    print("OUTPUT FILES")
    print(f"{'='*60}")
    print(f"  Sweep dir:     {result['sweep_dir']}")
    print(f"  Output dir:    {output_subdir}")
    print(f"  results.csv:   {output_subdir / 'results.csv'}")
    if parquet_path:
        print(f"  results.parquet: {output_subdir / 'results.parquet'}")
    print(f"  ranked.csv:    {output_subdir / 'ranked.csv'} ({ranked_count} combos)")
    print(f"  top_picks.json: {output_subdir / 'top_picks.json'}")
    print(f"  preflight.json: {output_subdir / 'preflight.json'}")
    if results_csv.exists():
        print(f"  disabled_bots.json: {output_subdir / 'disabled_bots.json'} "
              f"({len(broken_bot_names)} broken)")
        print(f"  curated_allowlist.json: {output_subdir / 'curated_allowlist.json'} "
              f"({curated_count} combos)")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    main()
