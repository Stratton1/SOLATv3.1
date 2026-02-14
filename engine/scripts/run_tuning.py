"""
SOLAT Tuning Pipeline CLI.

Usage:
    # Smoke mode (1 combo, 5 trials)
    python3 scripts/run_tuning.py --smoke

    # Tune specific combo
    python3 scripts/run_tuning.py --bot CloudTwist --symbol USDJPY --timeframe 4h --trials 40

    # Tune all combos from sweep results
    python3 scripts/run_tuning.py --sweep-results data/sweeps/*/results.csv --trials 40
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from solat_engine.data.parquet_store import ParquetStore
from solat_engine.optimization.scoring import ComboScore, score_combo
from solat_engine.optimization.search_space import get_default_params_dict
from solat_engine.optimization.tuner import ParamTuner, TuningConfig, TuningResult


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOLAT Parameter Tuning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--smoke", action="store_true", help="Smoke test: 1 combo, 5 trials")
    parser.add_argument("--bot", type=str, help="Specific bot to tune")
    parser.add_argument("--symbol", type=str, help="Specific symbol")
    parser.add_argument("--timeframe", type=str, default="4h", help="Timeframe (default: 4h)")
    parser.add_argument("--trials", type=int, default=40, help="Optuna trials per combo (default: 40)")
    parser.add_argument("--sweep-results", type=str, help="Path to sweep results CSV (tune top combos)")
    parser.add_argument("--top-n", type=int, default=20, help="Top N combos from sweep to tune")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date")
    parser.add_argument("--end", type=str, default="2025-12-31", help="End date")
    parser.add_argument("--data-dir", type=str, default="data", help="Data directory")
    parser.add_argument("--wf-folds", type=int, default=5, help="Walk-forward folds (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        # Try relative to engine/
        data_dir = Path(__file__).parent.parent / "data"

    store = ParquetStore(data_dir)
    run_id = f"tune_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    out_dir = data_dir / "tuning" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    artefacts_dir = data_dir / "artefacts" / "tuning"

    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=UTC)

    # Determine combos to tune
    combos: list[tuple[str, str, str]] = []

    if args.smoke:
        combos = [("CloudTwist", "USDJPY", "4h")]
        args.trials = 5
        args.wf_folds = 3
        print("SMOKE MODE: 1 combo, 5 trials, 3 folds")
    elif args.bot and args.symbol:
        combos = [(args.bot, args.symbol, args.timeframe)]
    elif args.sweep_results:
        import pandas as pd
        df = pd.read_csv(args.sweep_results)
        df = df[df["success"] & (df["total_trades"] >= 10)]
        df = df.nlargest(args.top_n, "sharpe")
        combos = [(row["bot"], row["symbol"], row["timeframe"]) for _, row in df.iterrows()]
    else:
        parser.error("Specify --smoke, --bot + --symbol, or --sweep-results")

    print(f"\n{'='*60}")
    print(f"SOLAT PARAMETER TUNING PIPELINE")
    print(f"{'='*60}")
    print(f"Run ID: {run_id}")
    print(f"Combos: {len(combos)}")
    print(f"Trials/combo: {args.trials}")
    print(f"WF folds: {args.wf_folds}")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Output: {out_dir}")
    print(f"{'='*60}\n")

    tuner = ParamTuner(parquet_store=store, artefacts_dir=artefacts_dir)
    all_results: list[TuningResult] = []
    all_scored: list[dict] = []

    for i, (bot, symbol, tf) in enumerate(combos):
        print(f"\n[{i+1}/{len(combos)}] Tuning {bot}/{symbol}/{tf}...")

        config = TuningConfig(
            bot=bot,
            symbol=symbol,
            timeframe=tf,
            start=start_dt,
            end=end_dt,
            n_trials=args.trials,
            seed=args.seed,
            data_dir=data_dir,
            wf_folds=args.wf_folds,
        )

        try:
            result = tuner.tune_combo(config)
            all_results.append(result)

            print(f"  Baseline score: {result.baseline_score:.1f}")
            if result.tuned_a:
                print(f"  tunedA score:   {result.tuned_a.score_total:.1f} (Sharpe={result.tuned_a.oos_sharpe:.2f}, DD={result.tuned_a.max_drawdown_pct:.1f}%)")
                print(f"    Diff: {result.tuned_a.params_diff}")
            if result.tuned_b:
                print(f"  tunedB score:   {result.tuned_b.score_total:.1f} (Sharpe={result.tuned_b.oos_sharpe:.2f}, DD={result.tuned_b.max_drawdown_pct:.1f}%)")
                print(f"    Diff: {result.tuned_b.params_diff}")
            print(f"  Duration: {result.duration_s:.1f}s")

            # Add baseline + variants to scored list
            baseline_entry = {
                "bot": bot, "symbol": symbol, "timeframe": tf,
                "variant_id": "baseline", "params_override": {},
                "score_total": result.baseline_score,
            }
            all_scored.append(baseline_entry)

            if result.tuned_a:
                all_scored.append({
                    "bot": bot, "symbol": symbol, "timeframe": tf,
                    "variant_id": "tunedA",
                    "params_override": result.tuned_a.params,
                    "score_total": result.tuned_a.score_total,
                    "oos_sharpe": result.tuned_a.oos_sharpe,
                    "oos_return_pct": result.tuned_a.oos_return_pct,
                    "max_drawdown_pct": result.tuned_a.max_drawdown_pct,
                    "total_trades": result.tuned_a.total_trades,
                    "win_rate": result.tuned_a.win_rate,
                })
            if result.tuned_b:
                all_scored.append({
                    "bot": bot, "symbol": symbol, "timeframe": tf,
                    "variant_id": "tunedB",
                    "params_override": result.tuned_b.params,
                    "score_total": result.tuned_b.score_total,
                    "oos_sharpe": result.tuned_b.oos_sharpe,
                    "oos_return_pct": result.tuned_b.oos_return_pct,
                    "max_drawdown_pct": result.tuned_b.max_drawdown_pct,
                    "total_trades": result.tuned_b.total_trades,
                    "win_rate": result.tuned_b.win_rate,
                })

        except Exception as e:
            print(f"  ERROR: {e}")

    # Write outputs
    summary_path = out_dir / "tuning_summary.json"
    with open(summary_path, "w") as f:
        json.dump([
            {
                "bot": r.bot, "symbol": r.symbol, "timeframe": r.timeframe,
                "baseline_score": r.baseline_score,
                "tuned_a": {
                    "variant_id": r.tuned_a.variant_id,
                    "params": r.tuned_a.params,
                    "params_diff": r.tuned_a.params_diff,
                    "score_total": r.tuned_a.score_total,
                    "oos_sharpe": r.tuned_a.oos_sharpe,
                } if r.tuned_a else None,
                "tuned_b": {
                    "variant_id": r.tuned_b.variant_id,
                    "params": r.tuned_b.params,
                    "params_diff": r.tuned_b.params_diff,
                    "score_total": r.tuned_b.score_total,
                    "oos_sharpe": r.tuned_b.oos_sharpe,
                } if r.tuned_b else None,
                "stage1_trials": r.stage1_trials,
                "duration_s": r.duration_s,
            }
            for r in all_results
        ], f, indent=2, default=str)

    scored_path = out_dir / "scored_combos.json"
    with open(scored_path, "w") as f:
        json.dump(all_scored, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"TUNING COMPLETE")
    print(f"{'='*60}")
    print(f"Combos tuned: {len(all_results)}")
    print(f"Total scored entries: {len(all_scored)} (baselines + variants)")
    print(f"Summary: {summary_path}")
    print(f"Scored combos: {scored_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
