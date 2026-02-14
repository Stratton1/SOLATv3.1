#!/usr/bin/env python3
"""
Validate SOLAT documentation layout invariants.

Checks:
1) Canonical docs must exist in docs/
2) Deprecated root docs must not exist
3) Tracked markdown/prompt/skill/rule files must not reference removed root doc paths
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DOCS = (
    Path("docs/ROADMAP.md"),
    Path("docs/BUILD_LOG.md"),
)

FORBIDDEN_ROOT_DOCS = (
    Path("ROADMAP.md"),
    Path("BUILD_LOG.md"),
    Path("NEXT_STEPS.md"),
    Path("finish_phased_plan.md"),
    Path("LIVE_READINESS_ROADMAP.md"),
)

# root-name -> canonical path
ROOT_TO_CANONICAL = {
    "ROADMAP.md": "docs/ROADMAP.md",
    "BUILD_LOG.md": "docs/BUILD_LOG.md",
    "NEXT_STEPS.md": "docs/ops/NEXT_STEPS.md",
    "finish_phased_plan.md": "docs/plans/frontend-overhaul-completion-plan.md",
    # Removed empty file; no replacement reference should remain.
    "LIVE_READINESS_ROADMAP.md": "",
}

SCAN_SUFFIXES = {".md", ".mdc", ".txt"}

# Historical notes may intentionally mention legacy root filenames.
REFERENCE_ALLOWLIST = {
    "docs/BUILD_LOG.md",
    "docs/ops/PROJECT_MEMORY.md",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    files: list[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = Path(line.strip())
        if path.suffix in SCAN_SUFFIXES:
            files.append(path)
    return files


def check_layout() -> list[str]:
    errors: list[str] = []

    for rel in REQUIRED_DOCS:
        if not (REPO_ROOT / rel).exists():
            errors.append(f"Missing required canonical doc: {rel}")

    for rel in FORBIDDEN_ROOT_DOCS:
        if (REPO_ROOT / rel).exists():
            errors.append(f"Deprecated root doc still present: {rel}")

    for rel in tracked_files():
        rel_str = rel.as_posix()
        if rel_str in REFERENCE_ALLOWLIST:
            continue

        abs_path = REPO_ROOT / rel
        if not abs_path.exists():
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")

        for line_no, line in enumerate(text.splitlines(), start=1):
            for root_name, canonical in ROOT_TO_CANONICAL.items():
                if root_name not in line:
                    continue

                # Accept if canonical path is explicitly used in the same line.
                if canonical and canonical in line:
                    continue

                errors.append(
                    f"Stale root doc reference in {rel_str}:{line_no}: {line.strip()}"
                )

    return errors


def main() -> int:
    errors = check_layout()
    if not errors:
        print("Docs layout check passed.")
        return 0

    print("Docs layout check failed:")
    for err in errors:
        print(f"- {err}")

    print("\nFix guidance:")
    print("- Keep canonical roadmap/build log in docs/: docs/ROADMAP.md, docs/BUILD_LOG.md")
    print("- Remove deprecated root docs listed in this check")
    print("- Update stale references to canonical docs paths")
    return 1


if __name__ == "__main__":
    sys.exit(main())
