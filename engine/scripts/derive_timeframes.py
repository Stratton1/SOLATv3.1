#!/usr/bin/env python3
"""
Derive higher timeframes from 1m base data.

CLI wrapper around aggregate_from_1m() from data/aggregate.py.
Reads 1m bars from ParquetStore, derives higher TFs, writes back.
"""

import sys
from pathlib import Path

# Python 3.10 compatibility shim
import datetime as _dt
if not hasattr(_dt, 'UTC'):
    _dt.UTC = _dt.timezone.utc

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from solat_engine.data.aggregate import aggregate_from_1m
from solat_engine.data.models import SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore

# Default data directory
DATA_DIR = Path(__file__).parent.parent / "data"

TF_MAP = {
    "5m": SupportedTimeframe.M5,
    "15m": SupportedTimeframe.M15,
    "30m": SupportedTimeframe.M30,
    "1h": SupportedTimeframe.H1,
    "4h": SupportedTimeframe.H4,
}


def main():
    parser = argparse.ArgumentParser(
        description="Derive higher timeframes from 1m bar data"
    )
    parser.add_argument(
        "--symbols", nargs="+", required=True,
        help="Symbols to derive (e.g. EURUSD GBPUSD)",
    )
    parser.add_argument(
        "--timeframes", nargs="+", default=["5m", "15m", "30m", "1h", "4h"],
        help="Target timeframes to derive (default: 5m 15m 30m 1h 4h)",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help=f"Data directory (default: {DATA_DIR})",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    store = ParquetStore(data_dir)

    # Validate timeframes
    target_tfs: list[SupportedTimeframe] = []
    for tf_str in args.timeframes:
        if tf_str not in TF_MAP:
            print(f"ERROR: Unknown timeframe '{tf_str}'. "
                  f"Valid: {', '.join(TF_MAP.keys())}", file=sys.stderr)
            sys.exit(1)
        target_tfs.append(TF_MAP[tf_str])

    print(f"Deriving timeframes: {args.timeframes}")
    print(f"Symbols: {args.symbols}")
    print(f"Data dir: {data_dir}")
    print()

    total_written = 0

    for symbol in args.symbols:
        print(f"  {symbol}: reading 1m bars...", end=" ", flush=True)

        # Read all 1m bars for this symbol
        m1_bars = store.read_bars(
            symbol=symbol,
            timeframe=SupportedTimeframe.M1,
        )

        if not m1_bars:
            print("no 1m data found, skipping")
            continue

        print(f"{len(m1_bars)} bars", end=" -> ", flush=True)

        # Aggregate to target timeframes
        results = aggregate_from_1m(m1_bars, target_timeframes=target_tfs)

        for tf, bars in results.items():
            if not bars:
                continue
            store.write_bars(bars)
            total_written += len(bars)
            print(f"{tf.value}({len(bars)})", end=" ", flush=True)

        print()

    print(f"\nDone. Total bars written: {total_written}")


if __name__ == "__main__":
    main()
