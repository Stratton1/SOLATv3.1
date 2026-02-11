#!/usr/bin/env python3
"""
Validate sweep/backtest artefact files against schema contracts.

Usage:
    python3 scripts/validate_artefacts.py <artefact_dir>

Exit codes:
    0 — all validations passed
    1 — one or more validations failed
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

SCHEMA_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")

REQUIRED_RANKED_COLUMNS = {"rank", "bot", "symbol", "timeframe", "sharpe"}


def validate_json_file(path: Path, name: str, checks: list[tuple[str, bool]]) -> list[str]:
    """Validate a JSON file and return list of error messages."""
    errors: list[str] = []
    if not path.exists():
        return [f"{name}: file not found at {path}"]

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"{name}: failed to read — {e}"]

    for desc, passed in checks:
        if not passed:
            errors.append(f"{name}: {desc}")

    return errors


def validate_top_picks(artefact_dir: Path) -> list[str]:
    """Validate top_picks.json."""
    path = artefact_dir / "top_picks.json"
    if not path.exists():
        return []  # optional file

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"top_picks.json: failed to read — {e}"]

    errors: list[str] = []

    sv = data.get("schema_version")
    if sv is None:
        errors.append("top_picks.json: missing 'schema_version'")
    elif not SCHEMA_VERSION_PATTERN.match(str(sv)):
        errors.append(f"top_picks.json: invalid schema_version '{sv}'")

    picks = data.get("picks")
    if picks is None:
        errors.append("top_picks.json: missing 'picks' key")
    elif not isinstance(picks, list):
        errors.append("top_picks.json: 'picks' is not a list")
    elif picks:
        first = picks[0]
        for key in ("bot", "symbol", "timeframe", "score"):
            if key not in first:
                errors.append(f"top_picks.json: first pick missing '{key}'")

    return errors


def validate_curated_allowlist(artefact_dir: Path) -> list[str]:
    """Validate curated_allowlist.json."""
    path = artefact_dir / "curated_allowlist.json"
    if not path.exists():
        return []

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"curated_allowlist.json: failed to read — {e}"]

    errors: list[str] = []

    sv = data.get("schema_version")
    if sv is None:
        errors.append("curated_allowlist.json: missing 'schema_version'")
    elif not SCHEMA_VERSION_PATTERN.match(str(sv)):
        errors.append(f"curated_allowlist.json: invalid schema_version '{sv}'")

    symbols = data.get("symbols")
    if symbols is None:
        errors.append("curated_allowlist.json: missing 'symbols' key")
    elif not isinstance(symbols, dict):
        errors.append("curated_allowlist.json: 'symbols' is not a dict")

    return errors


def validate_disabled_bots(artefact_dir: Path) -> list[str]:
    """Validate disabled_bots.json."""
    path = artefact_dir / "disabled_bots.json"
    if not path.exists():
        return []

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"disabled_bots.json: failed to read — {e}"]

    errors: list[str] = []

    sv = data.get("schema_version")
    if sv is None:
        errors.append("disabled_bots.json: missing 'schema_version'")
    elif not SCHEMA_VERSION_PATTERN.match(str(sv)):
        errors.append(f"disabled_bots.json: invalid schema_version '{sv}'")

    bots = data.get("broken_bots")
    if bots is None:
        errors.append("disabled_bots.json: missing 'broken_bots' key")
    elif not isinstance(bots, list):
        errors.append("disabled_bots.json: 'broken_bots' is not a list")

    return errors


def validate_ranked_csv(artefact_dir: Path) -> list[str]:
    """Validate ranked.csv."""
    path = artefact_dir / "ranked.csv"
    if not path.exists():
        return []

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return [f"ranked.csv: failed to read — {e}"]

    errors: list[str] = []
    missing = REQUIRED_RANKED_COLUMNS - set(df.columns)
    if missing:
        errors.append(f"ranked.csv: missing columns {sorted(missing)}")

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/validate_artefacts.py <artefact_dir>", file=sys.stderr)
        return 1

    artefact_dir = Path(sys.argv[1])
    if not artefact_dir.is_dir():
        print(f"Error: {artefact_dir} is not a directory", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    files_found = 0

    for validator in (
        validate_top_picks,
        validate_curated_allowlist,
        validate_disabled_bots,
        validate_ranked_csv,
    ):
        errors = validator(artefact_dir)
        all_errors.extend(errors)
        # Count found files
        name = validator.__name__.replace("validate_", "")
        if name == "ranked_csv":
            check_path = artefact_dir / "ranked.csv"
        elif name == "top_picks":
            check_path = artefact_dir / "top_picks.json"
        elif name == "curated_allowlist":
            check_path = artefact_dir / "curated_allowlist.json"
        else:
            check_path = artefact_dir / "disabled_bots.json"
        if check_path.exists():
            files_found += 1

    if files_found == 0:
        print(f"Warning: no artefact files found in {artefact_dir}", file=sys.stderr)
        return 0

    if all_errors:
        print(f"FAILED: {len(all_errors)} validation error(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"OK: {files_found} artefact file(s) validated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
