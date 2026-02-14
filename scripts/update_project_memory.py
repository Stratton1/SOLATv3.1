#!/usr/bin/env python3
"""
SOLAT Project Memory Updater.

Prepends structured entries to docs/ops/PROJECT_MEMORY.md and docs/BUILD_LOG.md.
Stdlib-only — no engine dependencies required.

Usage:
    python3 scripts/update_project_memory.py \
        --title "PROMPT 072 — Tuning Pipeline" \
        --goal "Build sweep->tune->score->portfolio pipeline" \
        --summary "Created 8 new files implementing 4-stage pipeline" \
        --files "engine/solat_engine/optimization/scoring.py,engine/solat_engine/optimization/tuner.py" \
        --tests "cd engine && python3 -m pytest tests/ -v" \
        --results "819 passed, 0 failed" \
        --followups "Run smoke tuning, validate portfolio constraints" \
        --issues "None"

    # CI check mode
    python3 scripts/update_project_memory.py --check
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_MEMORY_PATH = REPO_ROOT / "docs" / "ops" / "PROJECT_MEMORY.md"
BUILD_LOG_PATH = REPO_ROOT / "docs" / "BUILD_LOG.md"

# Files that count as "code changes" requiring log updates
CODE_PATTERNS = [
    r"^engine/",
    r"^apps/",
    r"^scripts/",
    r"^\.github/",
    r"^Cargo\.toml$",
    r"^package\.json$",
    r"^pnpm-lock\.yaml$",
    r"^pyproject\.toml$",
    r"^uv\.lock$",
    r"^requirements.*\.txt$",
]

LOG_FILES = {
    "docs/ops/PROJECT_MEMORY.md",
    "docs/BUILD_LOG.md",
}


def is_code_file(path: str) -> bool:
    """Check if a file path matches code change patterns."""
    return any(re.match(p, path) for p in CODE_PATTERNS)


def check_mode() -> int:
    """
    CI check mode: verify that if code files changed, log files also changed.

    Compares staged files (for pre-commit) or HEAD vs HEAD~1 (for CI).
    Returns 0 if OK, 1 if logs need updating.
    """
    # Try staged files first (pre-commit context)
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        changed = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        changed = []

    # Fall back to HEAD~1..HEAD (CI context)
    if not changed:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            changed = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            changed = []

    if not changed:
        print("OK: No changed files detected.")
        return 0

    has_code = any(is_code_file(f) for f in changed)
    has_log = any(f in LOG_FILES for f in changed)

    if has_code and not has_log:
        print("FAIL: Code files changed without updating project logs.")
        print()
        print("Changed code files:")
        for f in changed:
            if is_code_file(f):
                print(f"  - {f}")
        print()
        print("Fix: Update the logs before committing:")
        print("  python3 scripts/update_project_memory.py --title 'Your change title' --summary 'What changed'")
        return 1

    print("OK: Log files are up to date.")
    return 0


def format_memory_entry(args: argparse.Namespace) -> str:
    """Format a PROJECT_MEMORY.md entry."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"## {ts} — {args.title}", ""]

    if args.goal:
        lines.append("**Goal**")
        lines.append(f"- {args.goal}")
        lines.append("")

    if args.summary:
        lines.append("**What changed**")
        for item in args.summary:
            lines.append(f"- {item}")
        lines.append("")

    if args.files:
        lines.append("**Files**")
        for f in args.files.split(","):
            lines.append(f"- `{f.strip()}`")
        lines.append("")

    if args.tests or args.results:
        lines.append("**Verification**")
        if args.tests:
            lines.append(f"- Tests: `{args.tests}`")
        if args.results:
            lines.append(f"- Results: {args.results}")
        lines.append("")

    if args.followups:
        lines.append("**Next steps**")
        for item in args.followups:
            lines.append(f"- {item}")
        lines.append("")

    if args.issues:
        lines.append("**Risks / Known Issues**")
        for item in args.issues:
            lines.append(f"- {item}")
        lines.append("")

    if args.commit:
        lines.append(f"**Commit**: `{args.commit}`")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def format_build_log_entry(args: argparse.Namespace) -> str:
    """Format a BUILD_LOG.md entry (shorter than PROJECT_MEMORY)."""
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [f"## {args.title}", ""]
    lines.append(f"**Date**: {date}")

    if args.results:
        lines.append(f"**Tests**: {args.results}")

    lines.append("")
    lines.append("### Summary")
    lines.append("")

    if args.summary:
        for item in args.summary:
            lines.append(item)
    else:
        lines.append("(No summary provided)")

    lines.append("")

    if args.files:
        lines.append("### Files Changed")
        lines.append("")
        for f in args.files.split(","):
            lines.append(f"- `{f.strip()}`")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def prepend_to_memory(entry: str) -> None:
    """Prepend entry to PROJECT_MEMORY.md after the header/snapshot section."""
    PROJECT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not PROJECT_MEMORY_PATH.exists():
        PROJECT_MEMORY_PATH.write_text(
            "# SOLAT Project Memory\n\n"
            "Reverse-chronological log of all changes, decisions, and results.\n\n"
            "---\n\n"
        )

    content = PROJECT_MEMORY_PATH.read_text()

    # Find insertion point: after the "---" that follows the header/snapshot
    # Look for the first "---" line after the title
    marker = "\n---\n"
    idx = content.find(marker)
    if idx >= 0:
        insert_at = idx + len(marker) + 1  # After the --- and newline
        new_content = content[:insert_at] + "\n" + entry + content[insert_at:]
    else:
        # No marker found, append after content
        new_content = content + "\n" + entry

    PROJECT_MEMORY_PATH.write_text(new_content)
    print(f"Updated: {PROJECT_MEMORY_PATH.relative_to(REPO_ROOT)}")


def prepend_to_build_log(entry: str) -> None:
    """Prepend entry to BUILD_LOG.md after the header."""
    BUILD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not BUILD_LOG_PATH.exists():
        BUILD_LOG_PATH.write_text(
            "# Build Log\n\n"
            "Chronological record of major implementation prompts.\n\n"
            "---\n\n"
        )

    content = BUILD_LOG_PATH.read_text()

    # Find insertion point: after the first "---" line
    marker = "\n---\n"
    idx = content.find(marker)
    if idx >= 0:
        insert_at = idx + len(marker) + 1
        new_content = content[:insert_at] + "\n" + entry + content[insert_at:]
    else:
        new_content = content + "\n" + entry

    BUILD_LOG_PATH.write_text(new_content)
    print(f"Updated: {BUILD_LOG_PATH.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOLAT Project Memory Updater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--title", type=str, help="Entry title (required unless --check)")
    parser.add_argument("--goal", type=str, help="What was requested/attempted")
    parser.add_argument("--summary", type=str, nargs="+", help="What changed (multiple items)")
    parser.add_argument("--files", type=str, help="Comma-separated changed file paths")
    parser.add_argument("--tests", type=str, help="Test command(s) used")
    parser.add_argument("--results", type=str, help="Test results summary")
    parser.add_argument("--followups", type=str, nargs="+", help="Next steps")
    parser.add_argument("--issues", type=str, nargs="+", help="Known issues/risks")
    parser.add_argument("--commit", type=str, help="Git commit hash")
    parser.add_argument(
        "--check", action="store_true",
        help="CI mode: check if logs need updating (exit 0=ok, 1=needs update)",
    )

    args = parser.parse_args()

    if args.check:
        sys.exit(check_mode())

    if not args.title:
        parser.error("--title is required (unless using --check)")

    # Generate and prepend entries
    memory_entry = format_memory_entry(args)
    build_entry = format_build_log_entry(args)

    prepend_to_memory(memory_entry)
    prepend_to_build_log(build_entry)

    print("\nDone. Remember to stage the updated log files before committing:")
    print(f"  git add {PROJECT_MEMORY_PATH.relative_to(REPO_ROOT)} {BUILD_LOG_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
