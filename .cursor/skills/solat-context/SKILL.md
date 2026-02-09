---
name: solat-context
description: Prints a Session Primer summary for SOLAT and reminds the agent to read ROADMAP/ARCHITECTURE before making breaking changes. Use when starting a session, onboarding, or before large/architectural changes.
---

# SOLAT Session Primer

When this skill is invoked, perform the following in order.

## 1. Output the Session Primer (15–25 lines)

Copy the following summary into your response so both you and the user share the same context. Adjust the "Current focus" line if the user has stated a specific task.

```markdown
## SOLAT Session Primer

- **Project:** SOLAT v3.1 — desktop trading terminal (Tauri + React + Python FastAPI sidecar), IG broker, Elite 8 strategies, backtest-first.
- **Layout:** Engine = `engine/solat_engine/` (api, broker/ig, data, backtest, strategies, execution, market_data). UI = `apps/desktop/src/` (components, hooks, screens). Docs = `docs/`.
- **Invariants:** UI never talks to IG; engine binds localhost only; no secrets in repo/logs; backtests deterministic (no lookahead); strategy logic in engine only; respect phase discipline.
- **Canonical docs:** ARCHITECTURE.md (design, flows), ROADMAP.md (phases, next), SECURITY.md (secrets, kill switch), CONVENTIONS.md (style, artefacts). Agent list: docs/AGENTS/AGENTS-INVENTORY.md.
- **Phase state:** Foundations through market data backend done; Terminal UI (charting, overlays, markers) in progress. "What's next?" → anchor to ROADMAP.md.
- **Current focus:** [User's stated task or "general development".]
```

## 2. Remind before breaking changes

After the primer, add this line:

**Before making any architectural change, new endpoint, or schema change:** read `docs/ROADMAP.md` and `docs/ARCHITECTURE.md` (or the relevant section) and confirm the change aligns with the current phase and data flow. If in doubt, propose the change and ask for confirmation before implementing.

## 3. Optional: read docs now

If the user says they are about to make breaking or architectural changes, or if the session will touch engine API, execution, or data formats, suggest:

- "Should I read docs/ARCHITECTURE.md and docs/ROADMAP.md now so the next edits stay aligned?"

Then proceed only with what the user requests. This skill does not run tools by itself; it instructs you to output the primer and reminder.
