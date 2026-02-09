---
name: solat-dependency-upgrade
description: Suggests order of operations and verification steps for upgrading Python or JS dependencies. Use when upgrading FastAPI, React, or updating deps.
---

# SOLAT Dependency Upgrade Agent (11.3)

When the user says **"Upgrade FastAPI"**, **"Upgrade React"**, or **"Update deps"**, output **order of operations** and **verification steps** so upgrades don't break types or behaviour.

## Engine (Python)

- **Files:** [engine/pyproject.toml](engine/pyproject.toml), engine/uv.lock.
- **Order:** Upgrade one layer at a time (e.g. FastAPI first, then httpx, then pydantic) to isolate breakage. Or upgrade all and fix in one pass if scope is small.
- **After upgrade:** Run `uv pip install -e ".[dev]"` in engine/; run `uv run ruff check .`; `uv run mypy solat_engine`; `uv run pytest -v`.
- **Breaking changes:** Check CHANGELOG or release notes for major deps (FastAPI, pydantic, httpx); update imports or API usage if needed.
- **Pin:** Lockfile (uv.lock) should be committed; pin versions in pyproject.toml only if you need to hold a specific version.

## Desktop (Node/React)

- **Files:** [apps/desktop/package.json](apps/desktop/package.json), pnpm-lock.yaml.
- **Order:** Upgrade React/vite/tauri in a sensible order (e.g. React first, then Vite, then Tauri CLI).
- **After upgrade:** From root, `pnpm install`; `pnpm --filter solat-desktop typecheck`; `pnpm --filter solat-desktop build`; run Tauri dev to verify.
- **Breaking changes:** Check CHANGELOG for React, Vite, Tauri; update types or config if needed.
- **Pin:** pnpm-lock.yaml is the source of truth; use pnpm add/upgrade and commit lockfile.

## Output format

1. **Package(s) to upgrade:** Name and (optional) target version.
2. **Order of operations:** Step-by-step (e.g. 1. Edit pyproject.toml. 2. uv pip install -e ".[dev]". 3. Run tests and mypy.).
3. **Verification:** Commands to run (ruff, mypy, pytest, typecheck, build, dev).
4. **Optional:** Link to CHANGELOG or migration guide for major upgrades.
