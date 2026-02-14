#!/usr/bin/env python3
"""
SOLAT Sweep Artefact Reset Utility.

Safely archives (or deletes) old sweep/backtest/tuning/portfolio artefacts
to prepare for a fresh Grand Sweep run.

PROTECTED (never touched):
  - data/parquet/  (OHLCV bars + manifests)
  - .env, credentials files
  - data/logs/  (application logs)

Usage:
    # Dry run — see what would be archived
    python3 scripts/reset_sweep_artefacts.py --dry-run

    # Archive sweep artefacts (default, safe)
    python3 scripts/reset_sweep_artefacts.py --mode archive --yes

    # Archive everything (sweeps + tuning + portfolio + docs)
    python3 scripts/reset_sweep_artefacts.py --mode archive --yes \
        --include-tuning --include-portfolio --include-docs

    # Delete mode (requires explicit --yes)
    python3 scripts/reset_sweep_artefacts.py --mode delete --yes
"""

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ENGINE_ROOT.parent
DEFAULT_DATA_DIR = ENGINE_ROOT / "data"

# Directories that are ALWAYS protected — refuse to touch
PROTECTED_DIRS = {
    "parquet",   # OHLCV bars + manifests
    "logs",      # Application logs
}

PROTECTED_FILES = {
    ".env",
    "autopilot_v3.1_deployment.json",  # Active deployment config
}


def resolve_targets(
    data_dir: Path,
    include_tuning: bool = False,
    include_portfolio: bool = False,
    include_docs: bool = False,
) -> dict[str, list[Path]]:
    """
    Resolve all targets to archive/delete.

    Returns dict with categories as keys and list of paths as values.
    """
    targets: dict[str, list[Path]] = {
        "sweep_results": [],
        "backtests": [],
        "artefacts": [],
        "proposals": [],
        "log_files": [],
        "top_level_files": [],
    }

    # Sweep results
    sweep_dir = data_dir / "sweep_results"
    if sweep_dir.exists():
        for child in sweep_dir.iterdir():
            targets["sweep_results"].append(child)

    # Backtests
    backtests_dir = data_dir / "backtests"
    if backtests_dir.exists():
        for child in backtests_dir.iterdir():
            targets["backtests"].append(child)

    # Artefacts (walk-forward outputs etc.)
    artefacts_dir = data_dir / "artefacts"
    if artefacts_dir.exists():
        for child in artefacts_dir.iterdir():
            targets["artefacts"].append(child)

    # Proposals
    proposals_dir = data_dir / "proposals"
    if proposals_dir.exists():
        for child in proposals_dir.iterdir():
            targets["proposals"].append(child)

    # Log files in data root
    for log_file in data_dir.glob("*.log"):
        targets["log_files"].append(log_file)

    # Top-level JSON files (allowlist, optimized_variants)
    for name in ("allowlist.json", "optimized_variants.json"):
        f = data_dir / name
        if f.exists():
            targets["top_level_files"].append(f)

    # Optional: Tuning
    if include_tuning:
        targets["tuning"] = []
        tuning_dir = data_dir / "tuning"
        if tuning_dir.exists():
            for child in tuning_dir.iterdir():
                targets["tuning"].append(child)

    # Optional: Portfolio
    if include_portfolio:
        targets["portfolio"] = []
        portfolio_dir = data_dir / "portfolio"
        if portfolio_dir.exists():
            for child in portfolio_dir.iterdir():
                targets["portfolio"].append(child)

    # Optional: Hall-of-fame docs
    if include_docs:
        targets["docs"] = []
        docs_dir = REPO_ROOT / "docs"
        if docs_dir.exists():
            for pattern in ("GRAND_SWEEP_*.md",):
                for f in docs_dir.glob(pattern):
                    targets["docs"].append(f)

    return targets


def count_targets(targets: dict[str, list[Path]]) -> tuple[int, int]:
    """Count total files and directories in targets."""
    total_files = 0
    total_dirs = 0
    for paths in targets.values():
        for p in paths:
            if p.is_dir():
                total_dirs += 1
                total_files += sum(1 for _ in p.rglob("*") if _.is_file())
            elif p.is_file():
                total_files += 1
    return total_files, total_dirs


def is_protected(path: Path, data_dir: Path) -> bool:
    """Check if a path is in a protected location."""
    try:
        rel = path.relative_to(data_dir)
        parts = rel.parts
        if parts and parts[0] in PROTECTED_DIRS:
            return True
    except ValueError:
        pass

    if path.name in PROTECTED_FILES:
        return True

    return False


def print_targets(targets: dict[str, list[Path]], data_dir: Path) -> None:
    """Print a summary of what would be affected."""
    total_files, total_dirs = count_targets(targets)

    print(f"\nTargets: {total_files} files in {total_dirs} directories\n")

    for category, paths in targets.items():
        if not paths:
            continue
        print(f"  [{category}]")
        for p in sorted(paths):
            try:
                rel = p.relative_to(REPO_ROOT)
            except ValueError:
                rel = p
            kind = "dir" if p.is_dir() else "file"
            size = ""
            if p.is_dir():
                file_count = sum(1 for _ in p.rglob("*") if _.is_file())
                size = f" ({file_count} files)"
            elif p.is_file():
                size_bytes = p.stat().st_size
                if size_bytes > 1024 * 1024:
                    size = f" ({size_bytes / 1024 / 1024:.1f} MB)"
                elif size_bytes > 1024:
                    size = f" ({size_bytes / 1024:.1f} KB)"
            print(f"    {rel} [{kind}]{size}")
        print()


def archive_targets(
    targets: dict[str, list[Path]],
    archive_dir: Path,
    data_dir: Path,
) -> dict[str, list[str]]:
    """Move targets to archive directory. Returns manifest of moved paths."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, list[str]] = {}

    for category, paths in targets.items():
        moved: list[str] = []
        for p in paths:
            if is_protected(p, data_dir):
                print(f"  SKIP (protected): {p}")
                continue

            try:
                rel = p.relative_to(REPO_ROOT)
            except ValueError:
                rel = p

            dest = archive_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            if p.is_dir():
                shutil.move(str(p), str(dest))
            elif p.is_file():
                shutil.move(str(p), str(dest))

            moved.append(str(rel))

        if moved:
            manifest[category] = moved

    return manifest


def delete_targets(
    targets: dict[str, list[Path]],
    data_dir: Path,
) -> dict[str, list[str]]:
    """Delete targets. Returns manifest of deleted paths."""
    manifest: dict[str, list[str]] = {}

    for category, paths in targets.items():
        deleted: list[str] = []
        for p in paths:
            if is_protected(p, data_dir):
                print(f"  SKIP (protected): {p}")
                continue

            try:
                rel = p.relative_to(REPO_ROOT)
            except ValueError:
                rel = p

            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()

            deleted.append(str(rel))

        if deleted:
            manifest[category] = deleted

    return manifest


def write_manifest(manifest: dict, archive_dir: Path, mode: str) -> Path:
    """Write ARCHIVE_MANIFEST.json to the archive directory."""
    manifest_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": mode,
        "archive_dir": str(archive_dir),
        "items": manifest,
        "total_items": sum(len(v) for v in manifest.values()),
    }

    manifest_path = archive_dir / "ARCHIVE_MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_data, indent=2, default=str))
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOLAT Sweep Artefact Reset Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode", choices=["archive", "delete"], default="archive",
        help="archive (default) moves to _archive/; delete removes permanently",
    )
    parser.add_argument("--include-tuning", action="store_true", help="Also reset data/tuning/*")
    parser.add_argument("--include-portfolio", action="store_true", help="Also reset data/portfolio/*")
    parser.add_argument("--include-docs", action="store_true", help="Also archive hall-of-fame docs")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, no changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--archive-dir", type=str, help="Override archive directory path")
    parser.add_argument("--data-dir", type=str, help="Override data directory path")

    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    if not data_dir.exists():
        print(f"Data directory does not exist: {data_dir}")
        sys.exit(1)

    # Resolve archive directory
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    if args.archive_dir:
        archive_dir = Path(args.archive_dir)
    else:
        archive_dir = data_dir / "_archive" / ts

    # Resolve targets
    targets = resolve_targets(
        data_dir,
        include_tuning=args.include_tuning,
        include_portfolio=args.include_portfolio,
        include_docs=args.include_docs,
    )

    total_files, total_dirs = count_targets(targets)
    if total_files == 0 and total_dirs == 0:
        print("Nothing to reset. All target directories are empty or missing.")
        return

    # Print header
    print(f"\n{'='*60}")
    print(f"  SOLAT SWEEP ARTEFACT RESET")
    print(f"  Mode: {args.mode.upper()}")
    if args.dry_run:
        print(f"  ** DRY RUN — no changes will be made **")
    print(f"{'='*60}")

    # Show protected
    print(f"\n  PROTECTED (never touched):")
    print(f"    data/parquet/  (OHLCV bars + manifests)")
    print(f"    data/logs/     (application logs)")
    print(f"    .env           (credentials)")

    # Show targets
    print_targets(targets, data_dir)

    if args.dry_run:
        print("Dry run complete. No changes made.")
        return

    # Confirmation
    if not args.yes:
        if args.mode == "delete":
            prompt = f"PERMANENTLY DELETE {total_files} files? This cannot be undone. [yes/NO]: "
        else:
            prompt = f"Archive {total_files} files to {archive_dir.relative_to(REPO_ROOT)}? [yes/NO]: "

        response = input(prompt).strip().lower()
        if response != "yes":
            print("Cancelled.")
            return

    # Execute
    if args.mode == "archive":
        print(f"\nArchiving to: {archive_dir.relative_to(REPO_ROOT)}")
        manifest = archive_targets(targets, archive_dir, data_dir)
        manifest_path = write_manifest(manifest, archive_dir, "archive")
        print(f"\nManifest: {manifest_path.relative_to(REPO_ROOT)}")
    else:
        print(f"\nDeleting targets...")
        manifest = delete_targets(targets, data_dir)
        # Write manifest as deletion record
        record_dir = data_dir / "_archive" / f"deleted_{ts}"
        manifest_path = write_manifest(manifest, record_dir, "delete")
        print(f"\nDeletion record: {manifest_path.relative_to(REPO_ROOT)}")

    total_moved = sum(len(v) for v in manifest.values())
    print(f"\n{'='*60}")
    print(f"  RESET COMPLETE: {total_moved} items {'archived' if args.mode == 'archive' else 'deleted'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
