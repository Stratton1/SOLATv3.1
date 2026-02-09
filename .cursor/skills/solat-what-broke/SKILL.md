---
name: solat-what-broke
description: Decision tree for failures: engine vs UI vs env vs IG. Maps common errors to likely cause and next steps. Use when it doesn't work, connection failed, or build failed.
---

# SOLAT "What Broke?" Debug Agent (11.2)

When the user says **"It doesn't work"**, **"Connection failed"**, **"Build failed"**, or similar, use this **decision tree** to narrow scope and suggest **likely cause and next steps**. Ask for failing command and error message if not provided.

## Failing command

- **./scripts/dev.sh** — Both engine and UI start; if one fails, check which process (engine on 8765 or Tauri on 1420).
- **pnpm dev:engine** — Engine only; UI not started.
- **pnpm dev:ui** or **pnpm --filter solat-desktop tauri dev** — UI only; needs engine on 8765 for full behaviour.
- **pnpm test:engine** — Engine tests; failures are in engine/tests or engine code.
- **pnpm typecheck** — Desktop TypeScript; failures in apps/desktop/src.
- **Tauri build** — Rust + frontend build; check Rust toolchain, projectPath, dependencies.

## Error → likely cause and next steps

| Error / symptom | Likely cause | Next steps |
|-----------------|--------------|------------|
| Connection refused 8765, UI can't reach engine | Engine not running or wrong port | Run pnpm dev:engine; check SOLAT_PORT in .env; ensure nothing else uses 8765. |
| 401 from IG API | Credentials or session | Check .env: IG_API_KEY, IG_USERNAME, IG_PASSWORD; use demo first; check IG account type (demo vs live). |
| WebSocket disconnect, UI loses connection | Engine crashed or CORS | Check engine log for traceback; ensure CORS in main.py allows Tauri dev origin (localhost:1420, 127.0.0.1:8765). |
| Build failed (engine) | Dependency or Python | cd engine; uv pip install -e ".[dev]"; check Python 3.11+; run uv run pytest. |
| Build failed (desktop) | Dependency or Node/Rust | pnpm install from root; pnpm --filter solat-desktop typecheck; check Node 18+; rustup for Tauri. |
| Tauri build failed | Rust, projectPath, or signing | Check apps/desktop path; rustc --version; read Tauri error for missing deps or code signing. |
| Rate limit / 429 from IG | Too many requests | Respect IG rate limits; check broker/ig rate_limit; back off and retry. |
| Tests fail (engine) | Regressed code or fixture | Run uv run pytest -v in engine/; read failure for module; fix test or implementation. |

## Output format

1. **Likely cause:** One or two sentences (e.g. "Engine not running on 8765").
2. **Next steps:** Ordered list (e.g. 1. Start engine with pnpm dev:engine. 2. Check .env for SOLAT_PORT. 3. Read engine log if it exits.).
3. **Optional:** Ask for error message or last command if user did not provide it.
