---
name: solat-roadmap-phase
description: Reports phase status, next steps, and ROADMAP/BUILD_LOG updates. Use when the user asks what's next, should I build X, or when editing docs/ROADMAP.md. Inserts dated entries at top of BUILD_LOG.md (reverse chronological).
---

# SOLAT ROADMAP & Phase Agent (1.2)

When the user asks **"what's next?"**, **"should I build X?"**, or when editing [docs/ROADMAP.md](docs/ROADMAP.md), perform the following. Output phase status, next suggested tasks, ROADMAP edit suggestions, and (when applicable) a new build_log entry or the updated BUILD_LOG.md snippet.

## Phases (from ROADMAP)

- **001–009** Foundations — monorepo, engine, domain, Tauri, health/WS, CI, docs
- **010–019** IG Connectivity — REST client, auth, catalogue, rate limit, streaming placeholder
- **020–029** Data Layer — Parquet, aggregation, quality, IG history, sync
- **030–039** Backtest Engine — deterministic engine, broker sim, portfolio, metrics, sweep
- **040–049** Elite 8 Strategies — indicators, Elite 8 bots, reason codes
- **050–059** Live Execution — router, risk, kill switch, reconciliation, ledger
- **060–069** Terminal UI — charting, overlays, markers, blotter, backtest runner, settings
- **070–079** Hardening — chaos testing, health report, packaging, code signing
- **080+** Live Trading — live credentials, safeguards, A/B, monitoring, DR

## Current implementation state

Read [docs/ROADMAP.md](docs/ROADMAP.md) for the phase overview table and deliverables. Cross-check with code: engine/solat_engine/, apps/desktop/src/. Do not assume future phases are done; anchor "what's next?" to the last completed phase and ROADMAP.

## When suggesting or applying ROADMAP/phase changes

1. **Tick deliverables** — For each phase, tick only deliverables that exist in code (e.g. api/, backtest/, execution/, strategies/, market_data/, data/, catalog/, broker/ig/).
2. **BUILD_LOG.md** — Insert a **dated entry at the top** of [BUILD_LOG.md](BUILD_LOG.md) (repo root), reverse chronological. Format: **Date** | **Phase or task** | **What changed** (ROADMAP tick, deliverable completed, or "next steps" decision). Place new entry immediately below the "Agent inserts new entries" comment.

## Optional: "log this" / "update build log"

When the user says "log this" or "update build log", write only the BUILD_LOG entry (insert at top of Entries section); do not change ROADMAP.

## Output

1. **Phase status** — Table or list of phases with completion state (from ROADMAP).
2. **Next tasks** — Suggested next steps from ROADMAP (e.g. Terminal UI frontend deliverables, Hardening).
3. **ROADMAP edit suggestions** — If deliverables in code are not ticked, suggest which boxes to check; if phase is complete, suggest updating the phase overview table.
4. **Build_log** — When you propose or apply a phase-related change, provide the exact BUILD_LOG.md snippet to insert (newest first) or perform the edit.

## Phase discipline

Do not build later-phase features prematurely. If the user asks to build something that belongs to a later phase (e.g. live-only before hardening), propose the correct next step from the current phase and stop.
