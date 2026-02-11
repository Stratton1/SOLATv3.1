"""
Sweep utilities: catalogue-first symbol discovery, timeframe management,
data preflight, auto-derivation, and output generation.

Used by run_grand_sweep.py and the ParallelSweepRunner.
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from solat_engine.catalog.models import AssetClass
from solat_engine.catalog.seed import SEED_INSTRUMENTS
from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.data.models import SupportedTimeframe
from solat_engine.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# A) Catalogue-First Symbol Discovery
# =============================================================================

# 10 LIVE-ready FX pairs (canonical catalogue symbols)
LIVE_FX_PAIRS: list[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
    "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY",
]

# Build asset class -> symbols mapping once at import time
_ASSET_CLASS_SYMBOLS: dict[str, list[str]] = {}
for _item in SEED_INSTRUMENTS:
    _ac = _item.asset_class.value
    if _ac not in _ASSET_CLASS_SYMBOLS:
        _ASSET_CLASS_SYMBOLS[_ac] = []
    _ASSET_CLASS_SYMBOLS[_ac].append(_item.symbol)


def resolve_symbols_from_catalogue(
    asset_classes: list[str] | None = None,
) -> list[str]:
    """
    Get canonical symbols from SEED_INSTRUMENTS.

    Args:
        asset_classes: Optional filter (e.g. ["fx", "index"]). If None, returns all.

    Returns:
        Canonical symbols in seed order, deduplicated.
    """
    if asset_classes is None:
        return [item.symbol for item in SEED_INSTRUMENTS]

    symbols: list[str] = []
    for ac in asset_classes:
        ac_lower = ac.lower()
        matched = _ASSET_CLASS_SYMBOLS.get(ac_lower, [])
        if not matched:
            logger.warning("Unknown asset class '%s', skipping", ac)
        symbols.extend(matched)

    # Deduplicate preserving order
    return list(dict.fromkeys(symbols))


def get_available_asset_classes() -> list[str]:
    """Return list of asset classes with at least one seed instrument."""
    return list(_ASSET_CLASS_SYMBOLS.keys())


# =============================================================================
# B) Timeframe Management
# =============================================================================

# Default timeframes for each scope
DEFAULT_TIMEFRAMES_FULL = ["1m", "5m", "15m", "30m", "1h", "4h"]  # Complete set
DEFAULT_TIMEFRAMES_ALL = ["15m", "30m", "1h", "4h"]  # Legacy compatibility
DEFAULT_TIMEFRAMES_LIVE = ["1h", "4h"]

# Timeframes that are always derived from 1m (never IG-native)
DERIVED_ONLY_TIMEFRAMES = {"30m"}


def parse_timeframes(raw: list[str]) -> list[SupportedTimeframe]:
    """
    Parse and validate timeframe strings against SupportedTimeframe.

    Args:
        raw: List of timeframe strings (e.g. ["15m", "1h", "4h"])

    Returns:
        List of validated SupportedTimeframe enums.

    Raises:
        ValueError: If any timeframe is unsupported.
    """
    valid_values = {tf.value for tf in SupportedTimeframe}
    result = []
    for tf_str in raw:
        if tf_str not in valid_values:
            raise ValueError(
                f"Unsupported timeframe '{tf_str}'. Valid: {sorted(valid_values)}"
            )
        result.append(SupportedTimeframe(tf_str))
    return result


# =============================================================================
# C) Data Preflight
# =============================================================================


class PreflightResult:
    """Result of a data preflight check for a single combo."""

    __slots__ = ("symbol", "timeframe", "available", "skip_reason", "bar_count",
                 "data_start", "data_end", "storage_symbol")

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        available: bool,
        skip_reason: str | None = None,
        bar_count: int = 0,
        data_start: str | None = None,
        data_end: str | None = None,
        storage_symbol: str | None = None,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.available = available
        self.skip_reason = skip_reason
        self.bar_count = bar_count
        self.data_start = data_start
        self.data_end = data_end
        self.storage_symbol = storage_symbol


def preflight_check_partition(
    data_dir: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> PreflightResult:
    """
    Fast partition existence + coverage check without reading full data.

    Uses manifest JSON (tiny) or Parquet file existence as fallback.

    Args:
        data_dir: Root data directory
        symbol: Canonical symbol
        timeframe: Timeframe string (e.g. "1h")
        start: Requested start date (for range check)
        end: Requested end date (for range check)

    Returns:
        PreflightResult with availability info
    """
    storage_sym = resolve_storage_symbol(symbol)
    tf_enum = SupportedTimeframe(timeframe)

    # Check manifest first (fast, no parquet read)
    manifest_path = data_dir / "parquet" / "manifests" / f"{storage_sym}_{timeframe}.json"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            bar_count = manifest.get("row_count", 0)
            data_start = manifest.get("first_available_from")
            data_end = manifest.get("last_synced_to")

            if bar_count == 0:
                return PreflightResult(
                    symbol=symbol, timeframe=timeframe, available=False,
                    skip_reason="NO_DATA", storage_symbol=storage_sym,
                )

            # Check range overlap if requested
            if start and data_end:
                # Parse data_end to compare
                try:
                    de = datetime.fromisoformat(data_end.replace("Z", "+00:00"))
                    if de < start:
                        return PreflightResult(
                            symbol=symbol, timeframe=timeframe, available=False,
                            skip_reason="INSUFFICIENT_RANGE",
                            bar_count=bar_count, data_start=data_start, data_end=data_end,
                            storage_symbol=storage_sym,
                        )
                except (ValueError, TypeError):
                    pass

            return PreflightResult(
                symbol=symbol, timeframe=timeframe, available=True,
                bar_count=bar_count, data_start=data_start, data_end=data_end,
                storage_symbol=storage_sym,
            )
        except (json.JSONDecodeError, KeyError):
            pass  # Fall through to parquet check

    # Fallback: check parquet file exists
    parquet_path = (
        data_dir / "parquet" / "bars"
        / f"instrument_symbol={storage_sym}"
        / f"timeframe={timeframe}"
        / "data.parquet"
    )
    if parquet_path.exists():
        return PreflightResult(
            symbol=symbol, timeframe=timeframe, available=True,
            storage_symbol=storage_sym,
        )

    return PreflightResult(
        symbol=symbol, timeframe=timeframe, available=False,
        skip_reason="NO_DATA", storage_symbol=storage_sym,
    )


def preflight_check_1m_source(
    data_dir: Path,
    symbol: str,
) -> PreflightResult:
    """Check if 1m source data exists for deriving higher timeframes."""
    return preflight_check_partition(data_dir, symbol, "1m")


# =============================================================================
# D) Auto-Derive 15m/30m from 1m
# =============================================================================


def auto_derive_timeframe(
    data_dir: Path,
    symbol: str,
    target_tf: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> bool:
    """
    Derive a timeframe from 1m data if the target is missing.

    Idempotent: if target already exists, returns True immediately.
    Safe: writes to temp file then renames.

    Args:
        data_dir: Root data directory
        symbol: Canonical symbol
        target_tf: Target timeframe string (e.g. "15m", "30m")
        start: Optional start filter
        end: Optional end filter

    Returns:
        True if target data now exists, False if derivation failed.
    """
    from solat_engine.data.aggregate import aggregate_bars

    # Already have it?
    check = preflight_check_partition(data_dir, symbol, target_tf, start, end)
    if check.available:
        return True

    storage_sym = resolve_storage_symbol(symbol)
    target_enum = SupportedTimeframe(target_tf)

    # Check 1m source
    source_check = preflight_check_1m_source(data_dir, symbol)
    if not source_check.available:
        logger.debug("Cannot derive %s/%s: no 1m source data", symbol, target_tf)
        return False

    # Read 1m parquet directly (DataFrame, no HistoricalBar conversion for speed)
    source_path = (
        data_dir / "parquet" / "bars"
        / f"instrument_symbol={storage_sym}"
        / f"timeframe=1m"
        / "data.parquet"
    )
    if not source_path.exists():
        return False

    try:
        df_1m = pd.read_parquet(source_path)
        if df_1m.empty:
            return False

        df_1m["timestamp_utc"] = pd.to_datetime(df_1m["timestamp_utc"], utc=True)
        df_1m = df_1m.sort_values("timestamp_utc")

        # Apply date filter if provided
        if start:
            start_ts = pd.Timestamp(start, tz="UTC")
            df_1m = df_1m[df_1m["timestamp_utc"] >= start_ts]
        if end:
            end_ts = pd.Timestamp(end, tz="UTC")
            df_1m = df_1m[df_1m["timestamp_utc"] < end_ts]

        if df_1m.empty:
            return False

        # Resample using pandas directly (much faster than HistoricalBar round-trip)
        from solat_engine.data.aggregate import TIMEFRAME_FREQ

        freq = TIMEFRAME_FREQ.get(target_enum)
        if freq is None:
            return False

        df_1m_indexed = df_1m.set_index("timestamp_utc")
        agg_df = df_1m_indexed.resample(freq, label="left", closed="left").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["open"]).reset_index()

        if agg_df.empty:
            return False

        # Add metadata columns
        agg_df["instrument_symbol"] = storage_sym
        agg_df["timeframe"] = target_tf

        # Write atomically
        target_dir = (
            data_dir / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / f"timeframe={target_tf}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "data.parquet"

        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir, prefix=".tmp_derive_", suffix=".parquet"
        )
        os.close(fd)
        try:
            agg_df.to_parquet(tmp_path, index=False, compression="snappy")
            os.rename(tmp_path, target_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # Write manifest
        manifest_dir = data_dir / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{storage_sym}_{target_tf}.json"

        min_ts = agg_df["timestamp_utc"].min()
        max_ts = agg_df["timestamp_utc"].max()
        manifest_data = {
            "instrument_symbol": storage_sym,
            "timeframe": target_tf,
            "first_available_from": str(min_ts),
            "last_synced_to": str(max_ts),
            "row_count": len(agg_df),
            "last_run_id": "auto_derive",
            "last_updated": datetime.now(UTC).isoformat(),
            "file_paths": [str(target_path.relative_to(data_dir))],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2, default=str)

        logger.info(
            "Derived %d %s bars for %s from 1m data",
            len(agg_df), target_tf, symbol,
        )
        return True

    except Exception as e:
        logger.warning("Failed to derive %s/%s from 1m: %s", symbol, target_tf, e)
        return False


# =============================================================================
# E) Output Generation: Ranked CSV + Top Picks JSON
# =============================================================================


def generate_ranked_csv(
    results_df: pd.DataFrame,
    output_path: Path,
    min_trades: int = 30,
) -> pd.DataFrame:
    """
    Generate ranked results filtered by min_trades and excluding skipped/failed.

    Ranking: sharpe desc, max_drawdown asc (lower is better), win_rate desc, pnl desc.

    Returns the ranked DataFrame.
    """
    df = results_df.copy()

    # Filter: successful + enough trades + not skipped
    mask = df["success"] == True  # noqa: E712
    if "skipped" in df.columns:
        mask = mask & (df["skipped"] != True)  # noqa: E712
    if "total_trades" in df.columns:
        mask = mask & (df["total_trades"] >= min_trades)

    ranked = df[mask].copy()
    if ranked.empty:
        ranked.to_csv(output_path, index=False)
        return ranked

    # Sort: sharpe desc, then max_drawdown asc (less negative = better),
    # then win_rate desc, then pnl desc
    ranked = ranked.sort_values(
        by=["sharpe", "max_drawdown", "win_rate", "pnl"],
        ascending=[False, True, False, False],
    ).reset_index(drop=True)

    # Add rank column
    ranked.insert(0, "rank", range(1, len(ranked) + 1))

    ranked.to_csv(output_path, index=False)
    return ranked


def generate_top_picks_json(
    ranked_df: pd.DataFrame,
    output_path: Path,
    top_n: int = 30,
    diversify_by: list[str] | None = None,
    start: str = "",
    end: str = "",
    asset_classes: list[str] | None = None,
    timeframes: list[str] | None = None,
    min_trades: int = 30,
) -> dict[str, Any]:
    """
    Generate top_picks.json with diversified top-N combos.

    Args:
        ranked_df: Pre-ranked DataFrame (from generate_ranked_csv).
        output_path: Where to write the JSON.
        top_n: Max picks to include.
        diversify_by: Columns to diversify by (default: ["symbol", "timeframe"]).
            "none" disables diversification.
        start/end: Date range strings.
        asset_classes/timeframes: Filter metadata.
        min_trades: Min trades filter.

    Returns:
        The top_picks dict.
    """
    if diversify_by is None:
        diversify_by = ["symbol", "timeframe"]

    if ranked_df.empty:
        picks: list[dict[str, Any]] = []
    elif not diversify_by or diversify_by == ["none"]:
        # No diversification, just take top N
        picks = _df_to_picks(ranked_df.head(top_n))
    else:
        # Diversified selection: round-robin by group
        picks = _diversified_select(ranked_df, top_n, diversify_by)

    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "start": start,
        "end": end,
        "filters": {
            "min_trades": min_trades,
            "asset_classes": asset_classes or [],
            "timeframes": timeframes or [],
        },
        "count": len(picks),
        "picks": picks,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result


def _diversified_select(
    df: pd.DataFrame,
    top_n: int,
    diversify_by: list[str],
) -> list[dict[str, Any]]:
    """
    Select top N using round-robin across diversify_by groups.
    Each group contributes its top combos in order.
    """
    valid_cols = [c for c in diversify_by if c in df.columns]
    if not valid_cols:
        return _df_to_picks(df.head(top_n))

    # Group, keeping each group sorted by rank
    groups: dict[tuple, pd.DataFrame] = {}
    for key, group_df in df.groupby(valid_cols):
        if not isinstance(key, tuple):
            key = (key,)
        groups[key] = group_df

    # Round-robin
    picks: list[dict[str, Any]] = []
    group_iters = {k: iter(g.iterrows()) for k, g in groups.items()}
    seen_combo_ids: set[str] = set()

    while len(picks) < top_n and group_iters:
        exhausted = []
        for key, it in group_iters.items():
            if len(picks) >= top_n:
                break
            try:
                _, row = next(it)
                cid = row.get("combo_id", f"{row['bot']}:{row['symbol']}:{row['timeframe']}")
                if cid not in seen_combo_ids:
                    seen_combo_ids.add(cid)
                    picks.append(_row_to_pick(row))
            except StopIteration:
                exhausted.append(key)

        for key in exhausted:
            del group_iters[key]

    return picks


def _df_to_picks(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert DataFrame rows to pick dicts."""
    return [_row_to_pick(row) for _, row in df.iterrows()]


def _row_to_pick(row: pd.Series) -> dict[str, Any]:
    """Convert a single row to a pick dict."""
    metrics = {}
    for col in ["sharpe", "max_drawdown", "win_rate", "total_trades", "pnl",
                "sortino", "profit_factor", "avg_trade_pnl"]:
        if col in row.index and pd.notna(row[col]):
            metrics[col] = float(row[col]) if isinstance(row[col], (int, float)) else row[col]

    return {
        "bot": row.get("bot", ""),
        "symbol": row.get("symbol", ""),
        "timeframe": row.get("timeframe", ""),
        "score": float(row.get("sharpe", 0)),
        "metrics": metrics,
    }

# =============================================================================
# F) Broken Bot Detection
# =============================================================================


def detect_broken_bots(
    results_df: pd.DataFrame,
    zero_trade_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Detect bots that generate 0 trades across combos (likely broken or disabled).

    Args:
        results_df: Raw sweep results DataFrame.
        zero_trade_threshold: Flag bot if >= this fraction of combos have 0 trades.

    Returns:
        Dict with 'broken_bots' list and summary stats.
    """
    if results_df.empty or "bot" not in results_df.columns:
        return {"broken_bots": [], "total_bots": 0}

    # Filter to successful runs only
    if "success" in results_df.columns:
        df = results_df[results_df["success"] == True]  # noqa: E712
    else:
        df = results_df

    # Analyze per-bot trade counts
    bot_stats = df.groupby("bot").agg({
        "total_trades": ["sum", "count"],
    }).reset_index()
    bot_stats.columns = ["bot", "total_trades_sum", "combos_attempted"]

    # Count combos with 0 trades per bot
    zero_trade_counts = (
        df[df["total_trades"] == 0]
        .groupby("bot")
        .size()
        .reset_index(name="zero_trade_combos")
    )

    bot_stats = bot_stats.merge(zero_trade_counts, on="bot", how="left")
    bot_stats["zero_trade_combos"] = bot_stats["zero_trade_combos"].fillna(0).astype(int)

    # Calculate zero trade ratio
    bot_stats["zero_trade_ratio"] = (
        bot_stats["zero_trade_combos"] / bot_stats["combos_attempted"]
    )

    # Flag as broken if ratio >= threshold
    broken = bot_stats[bot_stats["zero_trade_ratio"] >= zero_trade_threshold]

    broken_bots = []
    for _, row in broken.iterrows():
        broken_bots.append({
            "bot": row["bot"],
            "combos_attempted": int(row["combos_attempted"]),
            "zero_trade_combos": int(row["zero_trade_combos"]),
            "zero_trade_ratio": float(row["zero_trade_ratio"]),
            "rule_triggered": f"zero_trade_ratio >= {zero_trade_threshold}",
            "suggested_action": (
                "INVESTIGATE" if row["zero_trade_ratio"] < 0.8
                else "REMOVE_FROM_ELITE_8"
            ),
        })

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "zero_trade_threshold": zero_trade_threshold,
        "total_bots": len(bot_stats),
        "broken_bots_count": len(broken_bots),
        "broken_bots": broken_bots,
    }


# =============================================================================
# G) Curated Allowlist Generation
# =============================================================================


def generate_curated_allowlist(
    ranked_df: pd.DataFrame,
    output_path: Path,
    broken_bots: list[str] | None = None,
    max_per_symbol: int = 3,
    max_per_bot: int = 5,
    max_per_timeframe: int | None = None,
) -> dict[str, Any]:
    """
    Generate curated allowlist grouped by symbol -> timeframe -> bots.

    Args:
        ranked_df: Filtered and ranked DataFrame.
        output_path: Where to write the allowlist JSON.
        broken_bots: List of bot names to exclude.
        max_per_symbol: Max combos per symbol.
        max_per_bot: Max combos per bot across all symbols.
        max_per_timeframe: Max combos per timeframe across all symbols (None = unlimited).

    Returns:
        The generated allowlist structure.
    """
    if broken_bots is None:
        broken_bots = []

    # Filter out broken bots
    df = ranked_df[~ranked_df["bot"].isin(broken_bots)].copy()

    # Apply per-bot and per-timeframe limits (global across all symbols)
    bot_counts: dict[str, int] = {}
    tf_counts: dict[str, int] = {}
    selected_rows = []

    for _, row in df.iterrows():
        bot = row["bot"]
        tf = row.get("timeframe", "")
        if bot_counts.get(bot, 0) >= max_per_bot:
            continue
        if max_per_timeframe is not None and tf_counts.get(tf, 0) >= max_per_timeframe:
            continue
        selected_rows.append(row)
        bot_counts[bot] = bot_counts.get(bot, 0) + 1
        tf_counts[tf] = tf_counts.get(tf, 0) + 1

    if not selected_rows:
        allowlist: dict[str, Any] = {
            "schema_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "filters": {
                "excluded_bots": broken_bots,
                "max_per_symbol": max_per_symbol,
                "max_per_bot": max_per_bot,
                "max_per_timeframe": max_per_timeframe,
            },
            "symbols": {},
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(allowlist, f, indent=2)
        return allowlist

    selected_df = pd.DataFrame(selected_rows)

    # Group by symbol -> timeframe
    symbols_dict: dict[str, Any] = {}

    for symbol in selected_df["symbol"].unique():
        symbol_df = selected_df[selected_df["symbol"] == symbol]

        # Apply per-symbol limit
        symbol_df = symbol_df.head(max_per_symbol)

        timeframes_dict: dict[str, list[dict[str, Any]]] = {}

        for timeframe in symbol_df["timeframe"].unique():
            tf_df = symbol_df[symbol_df["timeframe"] == timeframe]

            bots_list = []
            for _, row in tf_df.iterrows():
                bots_list.append({
                    "bot": row["bot"],
                    "sharpe": float(row.get("sharpe", 0)),
                    "total_trades": int(row.get("total_trades", 0)),
                    "win_rate": float(row.get("win_rate", 0)),
                    "pnl": float(row.get("pnl", 0)),
                })

            if bots_list:
                timeframes_dict[timeframe] = bots_list

        if timeframes_dict:
            symbols_dict[symbol] = timeframes_dict

    allowlist = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "filters": {
            "excluded_bots": broken_bots,
            "max_per_symbol": max_per_symbol,
            "max_per_bot": max_per_bot,
            "max_per_timeframe": max_per_timeframe,
        },
        "symbols": symbols_dict,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(allowlist, f, indent=2)

    return allowlist


# =============================================================================
# H) Disk-Based Symbol Discovery
# =============================================================================


def discover_symbols_from_disk(data_dir: Path) -> list[str]:
    """
    Discover symbols by scanning parquet/bars/ directory for instrument_symbol=* partitions.

    Args:
        data_dir: Root data directory (contains parquet/bars/).

    Returns:
        List of discovered storage symbols (not necessarily canonical).
    """
    bars_dir = data_dir / "parquet" / "bars"
    if not bars_dir.exists():
        logger.warning("Bars directory not found: %s", bars_dir)
        return []

    symbols = []
    try:
        for item in bars_dir.iterdir():
            if item.is_dir() and item.name.startswith("instrument_symbol="):
                storage_symbol = item.name.replace("instrument_symbol=", "")
                symbols.append(storage_symbol)
    except Exception as e:
        logger.error("Failed to discover symbols from disk: %s", e)
        return []

    return sorted(symbols)
