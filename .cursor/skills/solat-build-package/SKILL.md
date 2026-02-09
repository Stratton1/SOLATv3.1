---
name: solat-build-package
description: Suggests fix or layout for build failures, add dependency, or add new app. Use when build fails, add dependency, or changing workspace layout.
---

# SOLAT Build & Package Agent (8.3 skill)

When the user says **"Build fails"**, **"Add dependency"**, or **"Add new app"**, output **fix** or **layout suggestion** so pnpm, uv, and Tauri stay consistent.

## Common fixes

- **Build fails (engine):** Ensure engine/.venv exists and `uv pip install -e ".[dev]"` was run; check Python 3.11; run from repo root with working-directory ./engine for CI.
- **Build fails (desktop):** pnpm install from root; run `pnpm --filter solat-desktop typecheck` and `pnpm --filter solat-desktop build`; check Node version (18+).
- **Tauri build fails:** Rust toolchain (rustup); projectPath in CI must be ./apps/desktop; check [apps/desktop/src-tauri/tauri.conf.json](apps/desktop/src-tauri/tauri.conf.json).
- **Add dependency (engine):** Add to [engine/pyproject.toml](engine/pyproject.toml) under dependencies or [project.optional-dependencies] dev; run `uv pip install -e ".[dev]"` in engine/.
- **Add dependency (desktop):** From root, `pnpm --filter solat-desktop add <pkg>` or add to apps/desktop/package.json and pnpm install.
- **Add new app:** Add directory under apps/ with package.json; add to pnpm-workspace.yaml if using "apps/*"; add scripts in root package.json with --filter app-name.

Output: Step-by-step fix or exact commands and file edits. No hardcoded absolute paths.
