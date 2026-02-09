---
name: solat-ci-pipeline
description: Suggests CI YAML snippet or command alignment for new CI job or fix. Use when adding CI job, fixing CI, or editing workflows or root scripts.
---

# SOLAT CI Pipeline Agent (8.1 skill)

When the user says **"Add CI job"**, **"Fix CI"**, or when editing workflows or root scripts, output **YAML snippet** or **command alignment** so CI stays in sync with package.json and pyproject.toml.

## Current layout

- **Engine:** [.github/workflows/ci.yml](.github/workflows/ci.yml) job `test-engine` — checkout, setup uv, Python 3.11, `uv pip install -e ".[dev]"` in engine/, ruff check, mypy, pytest.
- **UI:** job `check-ui` — pnpm install, typecheck (and optionally lint) for solat-desktop.
- **Build:** job `build-tauri` — pnpm install, Tauri build; projectPath ./apps/desktop; matrix macos-latest.

## Adding a CI step

- **New engine check:** Add step in test-engine with working-directory: ./engine; use same uv/venv; run command that matches engine/pyproject.toml or README.
- **New UI check:** Add step in check-ui or new job; pnpm install once; run pnpm --filter solat-desktop <script>.
- **New platform:** Add to build-tauri strategy.matrix.platform (e.g. windows-latest, ubuntu-latest) when Tauri supports it.

## Fixing CI

- **Command not found:** Ensure working-directory and run match (e.g. engine vs root, uv run vs pnpm).
- **Cache:** Use pnpm/action-setup cache and optionally rust-cache for Tauri; avoid caching engine .venv across OS if matrix multiplies.
- **Secrets:** Never log or expose GITHUB_TOKEN beyond Tauri action needs.

Output: YAML snippet for the new step or job, or list of command/working-directory alignments to fix.
