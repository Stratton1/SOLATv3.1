#!/usr/bin/env python3
"""
Import historical forex data from histdata.com into SOLAT's Parquet store.

This script downloads 1-minute OHLCV data and aggregates it to multiple timeframes.
Data source: https://www.histdata.com/ via the histdata Python package.

Usage:
    python scripts/import_histdata.py --symbols EURUSD,GBPUSD --years 2024,2025
    python scripts/import_histdata.py --all-symbols --years 2020-2025
"""

import argparse
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger

logger = get_logger(__name__)

# Symbol mapping: histdata format -> SOLAT format
SYMBOL_MAP = {
    # Major Forex Pairs
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "NZDUSD": "NZDUSD",
    # Cross Pairs
    "EURGBP": "EURGBP",
    "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY",
    "EURCHF": "EURCHF",
    "EURAUD": "EURAUD",
    "EURCAD": "EURCAD",
    "EURNZD": "EURNZD",
    "GBPCHF": "GBPCHF",
    "GBPAUD": "GBPAUD",
    "GBPCAD": "GBPCAD",
    "GBPNZD": "GBPNZD",
    "AUDJPY": "AUDJPY",
    "AUDCHF": "AUDCHF",
    "AUDCAD": "AUDCAD",
    "AUDNZD": "AUDNZD",
    "CADJPY": "CADJPY",
    "CADCHF": "CADCHF",
    "CHFJPY": "CHFJPY",
    "NZDJPY": "NZDJPY",
    "NZDCHF": "NZDCHF",
    "NZDCAD": "NZDCAD",
    # Commodities
    "XAUUSD": "GOLD",      # Gold
    "XAGUSD": "SILVER",    # Silver
    # Indices (histdata names)
    "GRXEUR": "DAX",       # German DAX
    "UKXGBP": "FTSE100",   # UK FTSE 100
    "SPXUSD": "SP500",     # S&P 500
    "NSXUSD": "NASDAQ",    # NASDAQ
    "JPXJPY": "NIKKEI",    # Nikkei 225
    "AUXAUD": "ASX200",    # Australia ASX 200
    "HKXHKD": "HSI",       # Hang Seng
    "ETXEUR": "EUROSTOXX", # Euro Stoxx 50
}

# Reverse mapping for lookup
SOLAT_TO_HISTDATA = {v: k for k, v in SYMBOL_MAP.items()}

# ALL available symbols from histdata.com
ALL_HISTDATA_SYMBOLS = [
    # Major Forex Pairs (7)
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Cross Pairs (21)
    "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "CADJPY", "CADCHF", "CHFJPY", "NZDJPY", "NZDCHF", "NZDCAD",
    # Commodities (2)
    "XAUUSD", "XAGUSD",
    # Indices (8)
    "GRXEUR", "UKXGBP", "SPXUSD", "NSXUSD", "JPXJPY", "AUXAUD", "HKXHKD", "ETXEUR",
]

# Default symbols to import (matches SOLAT seed instruments)
DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY",
    "XAUUSD",  # Gold
]


def parse_histdata_csv(csv_path: Path, symbol: str) -> pd.DataFrame:
    """
    Parse histdata CSV file into a DataFrame.

    Format: datetime;open;high;low;close;volume (semicolon separated)
    Datetime format: YYYYMMDD HHMMSS
    """
    df = pd.read_csv(
        csv_path,
        sep=";",
        header=None,
        names=["datetime", "open", "high", "low", "close", "volume"],
        dtype={
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float,
        },
    )

    # Parse datetime - format is "20120201 000000"
    df["timestamp_utc"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")

    # Convert from EST to UTC (histdata is in EST)
    # EST is UTC-5, so add 5 hours
    df["timestamp_utc"] = df["timestamp_utc"] + timedelta(hours=5)
    df["timestamp_utc"] = df["timestamp_utc"].dt.tz_localize("UTC")

    # Add symbol
    df["symbol"] = symbol

    # Drop original datetime column
    df = df.drop(columns=["datetime"])

    # Reorder columns
    df = df[["timestamp_utc", "symbol", "open", "high", "low", "close", "volume"]]

    return df


def aggregate_to_timeframe(df_1m: pd.DataFrame, timeframe: SupportedTimeframe) -> pd.DataFrame:
    """Aggregate 1-minute data to a higher timeframe."""
    if timeframe == SupportedTimeframe.M1:
        return df_1m

    # Set timestamp as index for resampling
    df = df_1m.set_index("timestamp_utc")

    # Map timeframe to pandas resample rule
    resample_rules = {
        SupportedTimeframe.M5: "5min",
        SupportedTimeframe.M15: "15min",
        SupportedTimeframe.H1: "1h",
        SupportedTimeframe.H4: "4h",
    }

    rule = resample_rules.get(timeframe)
    if not rule:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    # Resample OHLCV
    agg = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "symbol": "first",
    }).dropna()

    # Reset index
    agg = agg.reset_index()

    return agg


def df_to_bars(df: pd.DataFrame, timeframe: SupportedTimeframe) -> list[HistoricalBar]:
    """Convert DataFrame to list of HistoricalBar objects."""
    bars = []
    for _, row in df.iterrows():
        bar = HistoricalBar(
            timestamp_utc=row["timestamp_utc"].to_pydatetime(),
            instrument_symbol=row["symbol"],
            timeframe=timeframe,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        bars.append(bar)
    return bars


def download_and_import(
    symbols: list[str],
    years: list[int],
    data_dir: Path,
    timeframes: list[SupportedTimeframe] | None = None,
) -> dict[str, int]:
    """
    Download historical data and import into Parquet store.

    Args:
        symbols: List of SOLAT symbol names
        years: List of years to download
        data_dir: SOLAT data directory
        timeframes: Timeframes to generate (default: all)

    Returns:
        Dict mapping symbol to total bars imported
    """
    try:
        from histdata import download_hist_data
        from histdata.api import Platform as HistPlatform
    except ImportError:
        logger.error("histdata package not installed. Run: pip install histdata")
        raise

    if timeframes is None:
        timeframes = list(SupportedTimeframe)

    store = ParquetStore(data_dir)
    results = {}

    for symbol in symbols:
        # Get histdata symbol name
        histdata_symbol = SOLAT_TO_HISTDATA.get(symbol, symbol)
        solat_symbol = SYMBOL_MAP.get(histdata_symbol, symbol)

        logger.info("Processing %s (histdata: %s)", solat_symbol, histdata_symbol)

        all_1m_data = []

        for year in years:
            logger.info("  Downloading %s for %d...", histdata_symbol, year)

            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Try to download full year first
                    try:
                        zip_path = download_hist_data(
                            year=str(year),
                            pair=histdata_symbol,
                            output_directory=tmpdir,
                            verbose=False,
                        )

                        # Extract and parse CSV
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                            if csv_names:
                                zf.extract(csv_names[0], tmpdir)
                                csv_path = Path(tmpdir) / csv_names[0]
                                df = parse_histdata_csv(csv_path, solat_symbol)
                                all_1m_data.append(df)
                                logger.info("    Downloaded %d bars for %d", len(df), year)

                    except Exception as e:
                        logger.warning("    Could not download %d: %s", year, e)
                        # Try month by month
                        for month in range(1, 13):
                            try:
                                zip_path = download_hist_data(
                                    year=str(year),
                                    month=str(month),
                                    pair=histdata_symbol,
                                    output_directory=tmpdir,
                                    verbose=False,
                                )

                                with zipfile.ZipFile(zip_path, "r") as zf:
                                    csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                                    if csv_names:
                                        zf.extract(csv_names[0], tmpdir)
                                        csv_path = Path(tmpdir) / csv_names[0]
                                        df = parse_histdata_csv(csv_path, solat_symbol)
                                        all_1m_data.append(df)
                            except Exception:
                                pass  # Month not available

            except Exception as e:
                logger.error("  Error downloading %s %d: %s", histdata_symbol, year, e)

        if not all_1m_data:
            logger.warning("No data downloaded for %s", symbol)
            results[symbol] = 0
            continue

        # Combine all 1m data
        df_1m = pd.concat(all_1m_data, ignore_index=True)
        df_1m = df_1m.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"])

        logger.info("  Total 1m bars: %d", len(df_1m))

        # Generate and store each timeframe
        total_bars = 0
        for tf in timeframes:
            df_tf = aggregate_to_timeframe(df_1m, tf)
            bars = df_to_bars(df_tf, tf)

            if bars:
                written, deduped = store.write_bars(bars, run_id=f"histdata_import_{datetime.now(UTC).isoformat()}")
                total_bars += written
                logger.info("    %s: %d bars written (%d deduplicated)", tf.value, written, deduped)

        results[symbol] = total_bars

    return results


def main():
    parser = argparse.ArgumentParser(description="Import historical forex data from histdata.com")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols (e.g., EURUSD,GBPUSD)",
    )
    parser.add_argument(
        "--all-symbols",
        action="store_true",
        help="Import all default symbols",
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2024,2025",
        help="Years to download (e.g., '2024,2025' or '2020-2025')",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data",
        help="Data directory",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default=None,
        help="Comma-separated timeframes (e.g., '1m,5m,1h'). Default: all",
    )

    args = parser.parse_args()

    # Parse symbols
    if args.all_symbols:
        symbols = DEFAULT_SYMBOLS
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = DEFAULT_SYMBOLS

    # Parse years
    if "-" in args.years:
        start, end = args.years.split("-")
        years = list(range(int(start), int(end) + 1))
    else:
        years = [int(y.strip()) for y in args.years.split(",")]

    # Parse timeframes
    timeframes = None
    if args.timeframes:
        tf_map = {"1m": SupportedTimeframe.M1, "5m": SupportedTimeframe.M5,
                  "15m": SupportedTimeframe.M15, "1h": SupportedTimeframe.H1, "4h": SupportedTimeframe.H4}
        timeframes = [tf_map[t.strip()] for t in args.timeframes.split(",")]

    print(f"Importing data for {len(symbols)} symbols, years {years}")
    print(f"Symbols: {symbols}")
    print(f"Data directory: {args.data_dir}")
    print()

    results = download_and_import(symbols, years, args.data_dir, timeframes)

    print("\n=== Import Summary ===")
    total = 0
    for symbol, count in results.items():
        print(f"  {symbol}: {count:,} bars")
        total += count
    print(f"\nTotal: {total:,} bars imported")


if __name__ == "__main__":
    main()
