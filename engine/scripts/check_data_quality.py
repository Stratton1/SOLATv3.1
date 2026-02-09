#!/usr/bin/env python3
"""
Data quality checker for imported historical data.

Checks for:
- Missing bars / gaps
- Invalid OHLC values
- Duplicate timestamps
- Data completeness
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def check_instrument(data_dir: Path, symbol: str, timeframe: str = "1h") -> dict:
    """Check data quality for a single instrument/timeframe."""
    parquet_path = data_dir / f"instrument_symbol={symbol}" / f"timeframe={timeframe}" / "data.parquet"

    if not parquet_path.exists():
        return {"symbol": symbol, "timeframe": timeframe, "error": "File not found"}

    # Load data
    df = pd.read_parquet(parquet_path)

    if df.empty:
        return {"symbol": symbol, "timeframe": timeframe, "error": "Empty dataframe"}

    # Ensure timestamp is datetime
    ts_col = "timestamp_utc" if "timestamp_utc" in df.columns else "timestamp"
    
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col])
        df = df.sort_values(ts_col)

    results = {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_bars": len(df),
        "start_date": df[ts_col].min().isoformat() if ts_col in df.columns else None,
        "end_date": df[ts_col].max().isoformat() if ts_col in df.columns else None,
        "issues": [],
    }

    # Check for duplicates
    if ts_col in df.columns:
        duplicates = df[ts_col].duplicated().sum()
        if duplicates > 0:
            results["issues"].append(f"{duplicates} duplicate timestamps")

    # Check OHLC validity
    if all(col in df.columns for col in ["open", "high", "low", "close"]):
        invalid_ohlc = (
            (df["high"] < df["low"]) |
            (df["high"] < df["open"]) |
            (df["high"] < df["close"]) |
            (df["low"] > df["open"]) |
            (df["low"] > df["close"])
        ).sum()
        if invalid_ohlc > 0:
            results["issues"].append(f"{invalid_ohlc} bars with invalid OHLC")

    # Check for gaps (only for 1h timeframe)
    # Expected gaps: ~52 weekends/year × years of data + holidays
    # Typical FX market gap budget: ~60-80 gaps/year
    if timeframe == "1h" and ts_col in df.columns:
        expected_gap = timedelta(hours=1)
        df_sorted = df.sort_values(ts_col)
        gaps = (df_sorted[ts_col].diff() > expected_gap * 2).sum()

        # Calculate expected gaps based on data range
        # FX markets: ~52 weekends + ~10 holidays + broker maintenance
        # Indices: more closures due to shorter trading hours
        start_date = df_sorted[ts_col].min()
        end_date = df_sorted[ts_col].max()
        years_of_data = max(1, (end_date - start_date).days / 365)
        expected_gaps_per_year = 100  # Conservative: weekends + holidays + maintenance
        gap_threshold = int(expected_gaps_per_year * years_of_data)

        if gaps > gap_threshold:
            results["issues"].append(f"{gaps} excessive gaps (>{gap_threshold} expected)")

    # Check for zero/null values
    if "close" in df.columns:
        zero_close = (df["close"] == 0).sum()
        if zero_close > 0:
            results["issues"].append(f"{zero_close} bars with zero close price")

    results["quality"] = "GOOD" if len(results["issues"]) == 0 else "ISSUES"

    return results


def main():
    parser = argparse.ArgumentParser(description="Check data quality")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/parquet/bars"),
        help="Path to bars data directory",
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        help="Timeframe to check",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}")
        return

    # Find all instruments
    instruments = []
    for d in data_dir.iterdir():
        if d.is_dir() and d.name.startswith("instrument_symbol="):
            symbol = d.name.split("=")[1]
            instruments.append(symbol)

    instruments.sort()

    print(f"\n{'='*60}")
    print(f"DATA QUALITY REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"Directory: {data_dir}")
    print(f"Timeframe: {args.timeframe}")
    print(f"Instruments: {len(instruments)}")
    print(f"{'='*60}\n")

    all_results = []
    for symbol in instruments:
        result = check_instrument(data_dir, symbol, args.timeframe)
        all_results.append(result)

        status = "✅" if result.get("quality") == "GOOD" else "⚠️"
        bars = result.get("total_bars", 0)
        start = result.get("start_date", "?")[:10] if result.get("start_date") else "?"
        end = result.get("end_date", "?")[:10] if result.get("end_date") else "?"
        issues = result.get("issues", [])

        print(f"{status} {symbol:12} | {bars:>8,} bars | {start} → {end}")
        if issues:
            for issue in issues:
                print(f"   ⚠️  {issue}")

    # Summary
    good = sum(1 for r in all_results if r.get("quality") == "GOOD")
    total_bars = sum(r.get("total_bars", 0) for r in all_results)

    print(f"\n{'='*60}")
    print(f"SUMMARY: {good}/{len(instruments)} instruments passed quality checks")
    print(f"TOTAL BARS: {total_bars:,}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
