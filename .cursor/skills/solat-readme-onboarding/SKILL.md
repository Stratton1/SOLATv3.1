---
name: solat-readme-onboarding
description: Provides ordered onboarding steps for new devs (clone, env, dev.sh, where to find docs). Use when the user asks how do I run this or onboard new dev.
---

# SOLAT README & Onboarding Agent (7.2 skill)

When the user asks **"how do I run this?"** or **"onboard new dev"**, output **ordered steps** so a new developer can get from clone to running app and find key docs.

## Onboarding steps

1. **Clone:** Clone the repo; ensure Python 3.11+, Node 18+, pnpm, and Rust (rustup) are installed.
2. **Env:** Copy [.env.example](.env.example) to `.env`. Optionally fill IG_* for broker features; leave as placeholder for engine-only or UI-only work.
3. **Engine (optional standalone):** `cd engine` then `uv venv` (if needed), `uv pip install -e ".[dev]"`; run `uv run uvicorn solat_engine.main:app --host 127.0.0.1 --port 8765`.
4. **UI (optional standalone):** From repo root, `pnpm install`; run `pnpm dev:ui` (or `pnpm --filter solat-desktop tauri dev`). Requires engine on 8765 for full behaviour.
5. **Full stack:** From repo root, run `./scripts/dev.sh` to start engine and Tauri UI together.
6. **Verify:** Open Tauri window; engine health and WebSocket status should show. Engine docs: http://127.0.0.1:8765/docs.
7. **Docs:** Point to [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ROADMAP.md](docs/ROADMAP.md), [docs/SECURITY.md](docs/SECURITY.md), [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Output

Numbered list of steps (and optional one-line commands). If the user only needs "run this", shorten to: copy .env, run ./scripts/dev.sh, open Tauri window.
