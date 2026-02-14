#!/usr/bin/env python3
"""
Generate canonical OHLCV symbol/timeframe inventory documentation.

Output:
    docs/explainer/OHLCV_SYMBOL_TIMEFRAME_INVENTORY.md
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - env/setup error path
    print(
        "ERROR: pyarrow is required to inspect parquet schema. "
        "Install engine dependencies first.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = REPO_ROOT / "engine" / "data" / "parquet" / "manifests"
ENGINE_DATA_DIR = REPO_ROOT / "engine" / "data"
OUTPUT_DIR = REPO_ROOT / "docs" / "explainer"
OUTPUT_PATH = OUTPUT_DIR / "OHLCV_SYMBOL_TIMEFRAME_INVENTORY.md"

TIMEFRAME_ORDER = ["1m", "5m", "15m", "30m", "1h", "4h"]
TIMEFRAME_RANK = {tf: idx for idx, tf in enumerate(TIMEFRAME_ORDER)}


@dataclass(frozen=True)
class InventoryRow:
    symbol: str
    timeframe: str
    data_source: str
    source_run_id: str
    start_utc: str
    end_utc: str
    row_count: int
    volume_included: bool
    volume_null_count: int | None
    parquet_path: str
    manifest_last_updated_utc: str


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def fmt_ts(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.isoformat().replace("+00:00", "Z")


def source_from_run_id(run_id: str) -> str:
    if run_id.startswith("histdata_import_"):
        return "histdata.com import (via engine/scripts/import_histdata.py)"
    if run_id == "auto_derive":
        return "auto-derived from 1m (via auto_derive_timeframe)"
    return "unknown/manual"


def tf_sort_key(timeframe: str) -> tuple[int, str]:
    return (TIMEFRAME_RANK.get(timeframe, len(TIMEFRAME_ORDER)), timeframe)


def collect_rows() -> tuple[list[InventoryRow], int]:
    if not MANIFESTS_DIR.exists():
        raise SystemExit(f"ERROR: manifests directory not found: {MANIFESTS_DIR}")

    parse_errors: list[str] = []
    missing_parquet: list[str] = []
    pair_seen: set[tuple[str, str]] = set()
    rows: list[InventoryRow] = []
    manifest_count = 0

    for manifest_path in sorted(MANIFESTS_DIR.glob("*.json")):
        manifest_count += 1
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - malformed file path
            parse_errors.append(f"{manifest_path}: {exc}")
            continue

        symbol = str(data.get("instrument_symbol", "")).strip()
        timeframe = str(data.get("timeframe", "")).strip()
        if not symbol or not timeframe:
            parse_errors.append(f"{manifest_path}: missing instrument_symbol/timeframe")
            continue

        pair = (symbol, timeframe)
        if pair in pair_seen:
            parse_errors.append(f"{manifest_path}: duplicate pair {symbol}/{timeframe}")
            continue
        pair_seen.add(pair)

        run_id = str(data.get("last_run_id") or "")
        files = data.get("file_paths") or []
        parquet_rel = str(files[0]).strip() if files else ""
        parquet_path = ENGINE_DATA_DIR / parquet_rel if parquet_rel else None
        if not parquet_rel or parquet_path is None or not parquet_path.exists():
            missing_parquet.append(
                f"{manifest_path.name}: missing parquet path '{parquet_rel or '<empty>'}'"
            )
            continue

        parquet_file = pq.ParquetFile(parquet_path)
        cols = parquet_file.schema.names
        volume_included = "volume" in cols
        volume_null_count: int | None = None

        if volume_included:
            vol_idx = cols.index("volume")
            md = parquet_file.metadata
            total_null = 0
            saw_stats = False
            for rg_idx in range(md.num_row_groups):
                col_chunk = md.row_group(rg_idx).column(vol_idx)
                stats = col_chunk.statistics
                if stats is not None and stats.null_count is not None:
                    saw_stats = True
                    total_null += int(stats.null_count)
            volume_null_count = total_null if saw_stats else None

        row = InventoryRow(
            symbol=symbol,
            timeframe=timeframe,
            data_source=source_from_run_id(run_id),
            source_run_id=run_id or "",
            start_utc=fmt_ts(parse_ts(data.get("first_available_from"))),
            end_utc=fmt_ts(parse_ts(data.get("last_synced_to"))),
            row_count=int(data.get("row_count", 0)),
            volume_included=volume_included,
            volume_null_count=volume_null_count,
            parquet_path=str(Path("engine/data") / parquet_rel).replace("\\", "/"),
            manifest_last_updated_utc=fmt_ts(parse_ts(data.get("last_updated"))),
        )
        rows.append(row)

    errors: list[str] = []
    if parse_errors:
        errors.extend(["Unparseable/invalid manifests:"] + [f"  - {e}" for e in parse_errors])
    if missing_parquet:
        errors.extend(["Missing parquet paths referenced by manifests:"] + [f"  - {e}" for e in missing_parquet])
    if len(rows) != len(pair_seen):
        errors.append(
            f"Pair uniqueness assertion failed: rows={len(rows)} unique_pairs={len(pair_seen)}"
        )
    if len(rows) != manifest_count:
        errors.append(
            f"Row count assertion failed: rows={len(rows)} manifests={manifest_count}"
        )
    if errors:
        print("ERROR: inventory generation failed validation checks:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        raise SystemExit(1)

    rows.sort(key=lambda r: (r.symbol, tf_sort_key(r.timeframe)))
    return rows, manifest_count


def render_markdown(rows: list[InventoryRow], manifest_count: int) -> str:
    symbols = sorted({r.symbol for r in rows})
    tfs = sorted({r.timeframe for r in rows}, key=tf_sort_key)

    start_dts = [parse_ts(r.start_utc) for r in rows if r.start_utc]
    end_dts = [parse_ts(r.end_utc) for r in rows if r.end_utc]
    global_start = fmt_ts(min(start_dts)) if start_dts else ""
    global_end = fmt_ts(max(end_dts)) if end_dts else ""

    source_counts: dict[str, int] = {}
    for r in rows:
        source_counts[r.data_source] = source_counts.get(r.data_source, 0) + 1

    vol_true = sum(1 for r in rows if r.volume_included)
    vol_false = len(rows) - vol_true

    null_stats_known = [r.volume_null_count for r in rows if r.volume_null_count is not None]
    null_stats_unknown = len(rows) - len(null_stats_known)
    total_volume_nulls = sum(null_stats_known)

    required_tfs = set(TIMEFRAME_ORDER)
    eurusd_tfs = {r.timeframe for r in rows if r.symbol == "EURUSD"}
    eurusd_missing = sorted(required_tfs - eurusd_tfs, key=tf_sort_key)
    known_gap_line = (
        f"- Known gap note: `EURUSD` missing manifests for {', '.join(f'`{tf}`' for tf in eurusd_missing)}."
        if eurusd_missing
        else "- Known gap note: `EURUSD` has all expected timeframe manifests."
    )

    lines: list[str] = []
    lines.append("# OHLCV Symbol-Timeframe Inventory (Parquet)")
    lines.append("")
    lines.append("## What This File Is")
    lines.append(
        "Canonical inventory of every stored OHLCV parquet dataset by `(symbol, timeframe)`."
    )
    lines.append(
        "This is generated directly from `engine/data/parquet/manifests/*.json` and referenced parquet files."
    )
    lines.append("")
    lines.append("## How Source Is Determined")
    lines.append("- `histdata_import_*` -> `histdata.com import (via engine/scripts/import_histdata.py)`")
    lines.append("- `auto_derive` -> `auto-derived from 1m (via auto_derive_timeframe)`")
    lines.append("- Any other value -> `unknown/manual`")
    lines.append("")
    lines.append("## Summary Snapshot")
    lines.append(f"- Total pairs: `{len(rows)}`")
    lines.append(f"- Total symbols: `{len(symbols)}`")
    lines.append(f"- Available timeframes: {', '.join(f'`{tf}`' for tf in tfs)}")
    lines.append(f"- Global date coverage: `{global_start}` -> `{global_end}`")
    lines.append("- Source breakdown counts:")
    for source_name in sorted(source_counts):
        lines.append(f"  - `{source_name}`: `{source_counts[source_name]}`")
    lines.append(
        "- Volume coverage: "
        f"`{vol_true}` with `volume`, `{vol_false}` without `volume`; "
        f"total known volume nulls=`{total_volume_nulls}`, "
        f"unknown-null-count-files=`{null_stats_unknown}`"
    )
    lines.append(known_gap_line)
    lines.append(f"- Manifest files scanned: `{manifest_count}`")
    lines.append("")
    lines.append("## Column Glossary")
    lines.append("- `symbol`: instrument symbol key in storage/manifests.")
    lines.append("- `timeframe`: bar interval key (for example `1m`, `4h`).")
    lines.append("- `data_source`: inferred provenance from `source_run_id`.")
    lines.append("- `source_run_id`: manifest `last_run_id` value.")
    lines.append("- `start_utc` / `end_utc`: manifest availability bounds in normalized UTC ISO format.")
    lines.append("- `row_count`: manifest row count for the parquet partition.")
    lines.append("- `volume_included`: whether parquet schema includes `volume` column.")
    lines.append("- `volume_null_count`: parquet metadata null-count total for `volume` (blank if unavailable).")
    lines.append("- `parquet_path`: repository-relative parquet file path.")
    lines.append("- `manifest_last_updated_utc`: normalized UTC timestamp from manifest `last_updated`.")
    lines.append("")
    lines.append(f"## Complete Inventory ({len(rows)} Pairs)")
    lines.append("")
    lines.append(
        "| symbol | timeframe | data_source | source_run_id | start_utc | end_utc | "
        "row_count | volume_included | volume_null_count | parquet_path | "
        "manifest_last_updated_utc |"
    )
    lines.append(
        "|---|---|---|---|---|---|---:|---|---:|---|---|"
    )
    for r in rows:
        vol_null = "" if r.volume_null_count is None else str(r.volume_null_count)
        lines.append(
            f"| {r.symbol} | {r.timeframe} | {r.data_source} | {r.source_run_id} | "
            f"{r.start_utc} | {r.end_utc} | {r.row_count} | "
            f"{str(r.volume_included).lower()} | {vol_null} | {r.parquet_path} | "
            f"{r.manifest_last_updated_utc} |"
        )
    lines.append("")
    lines.append("## Regeneration")
    lines.append("```bash")
    lines.append("python3 scripts/generate_ohlcv_inventory_doc.py")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    rows, manifest_count = collect_rows()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(rows, manifest_count)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
