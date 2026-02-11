#!/usr/bin/env python3
"""
Analyze interim sweep results from a running or completed sweep.

Usage:
    python3 analyze_sweep_interim.py aa2c3781
"""

import sys
import json
from pathlib import Path
import pandas as pd

def load_sweep_results(sweep_id: str) -> pd.DataFrame:
    """Load all completed combo results from a sweep."""
    sweep_dir = Path(__file__).parent.parent / "data" / "sweeps" / sweep_id
    combos_dir = sweep_dir / "combos"

    if not combos_dir.exists():
        print(f"Error: Sweep directory not found: {sweep_dir}")
        sys.exit(1)

    results = []
    for json_file in combos_dir.glob("*.json"):
        with open(json_file) as f:
            data = json.load(f)
            if data.get("success") and not data.get("skipped"):
                results.append(data)

    if not results:
        print(f"Error: No completed results found in {combos_dir}")
        sys.exit(1)

    df = pd.DataFrame(results)
    return df

def generate_rankings(df: pd.DataFrame) -> pd.DataFrame:
    """Generate ranked results by Sharpe ratio."""
    # Filter: min_trades >= 10
    df_filtered = df[df["total_trades"] >= 10].copy()

    # Sort by Sharpe descending
    df_ranked = df_filtered.sort_values("sharpe", ascending=False).reset_index(drop=True)

    # Add rank column
    df_ranked.insert(0, "rank", range(1, len(df_ranked) + 1))

    # Select key columns
    cols = [
        "rank", "bot", "symbol", "timeframe", "sharpe", "total_trades",
        "win_rate", "pnl", "max_drawdown", "profit_factor", "avg_trade_pnl"
    ]
    return df_ranked[cols]

def analyze_by_bot(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate performance by bot."""
    agg = df.groupby("bot").agg({
        "sharpe": ["mean", "median", "max", "min"],
        "total_trades": "sum",
        "win_rate": "mean",
        "pnl": "sum"
    }).round(2)

    agg.columns = ["_".join(col).strip() for col in agg.columns.values]
    agg = agg.sort_values("sharpe_mean", ascending=False)
    return agg

def analyze_by_timeframe(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate performance by timeframe."""
    agg = df.groupby("timeframe").agg({
        "sharpe": ["mean", "median", "max"],
        "total_trades": "mean",
        "win_rate": "mean"
    }).round(2)

    agg.columns = ["_".join(col).strip() for col in agg.columns.values]
    agg = agg.sort_values("sharpe_mean", ascending=False)
    return agg

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 analyze_sweep_interim.py <sweep_id>")
        sys.exit(1)

    sweep_id = sys.argv[1]

    print(f"Loading sweep results for {sweep_id}...")
    df = load_sweep_results(sweep_id)

    print(f"\n✅ Loaded {len(df)} completed combos\n")

    # Overall stats
    print("=" * 80)
    print("OVERALL STATISTICS")
    print("=" * 80)
    print(f"Total combos: {len(df)}")
    print(f"Total trades: {df['total_trades'].sum():,}")
    print(f"Mean Sharpe: {df['sharpe'].mean():.2f}")
    print(f"Median Sharpe: {df['sharpe'].median():.2f}")
    print(f"Best Sharpe: {df['sharpe'].max():.2f}")
    print(f"Worst Sharpe: {df['sharpe'].min():.2f}")
    print()

    # Top 10 combos
    print("=" * 80)
    print("TOP 10 COMBOS (by Sharpe)")
    print("=" * 80)
    ranked = generate_rankings(df)
    print(ranked.head(10).to_string(index=False))
    print()

    # Bot performance
    print("=" * 80)
    print("PERFORMANCE BY BOT")
    print("=" * 80)
    bot_agg = analyze_by_bot(df)
    print(bot_agg.to_string())
    print()

    # Timeframe performance
    print("=" * 80)
    print("PERFORMANCE BY TIMEFRAME")
    print("=" * 80)
    tf_agg = analyze_by_timeframe(df)
    print(tf_agg.to_string())
    print()

    # CloudTwist specific (if exists)
    if "CloudTwist" in df["bot"].values:
        print("=" * 80)
        print("CLOUDTWIST PERFORMANCE BREAKDOWN")
        print("=" * 80)
        ct = df[df["bot"] == "CloudTwist"].copy()
        ct_ranked = ct.sort_values("sharpe", ascending=False)
        ct_display = ct_ranked[["symbol", "timeframe", "sharpe", "total_trades", "win_rate", "pnl"]]
        print(ct_display.to_string(index=False))
        print()
        print(f"CloudTwist Summary:")
        print(f"  Mean Sharpe: {ct['sharpe'].mean():.2f}")
        print(f"  Median Sharpe: {ct['sharpe'].median():.2f}")
        print(f"  Best: {ct['sharpe'].max():.2f} ({ct_ranked.iloc[0]['symbol']} {ct_ranked.iloc[0]['timeframe']})")
        print()

    # Save ranked CSV
    output_dir = Path(__file__).parent.parent / "data" / "sweeps" / sweep_id
    ranked_path = output_dir / "ranked_interim.csv"
    ranked.to_csv(ranked_path, index=False)
    print(f"✅ Saved ranked results to: {ranked_path}")

if __name__ == "__main__":
    main()
