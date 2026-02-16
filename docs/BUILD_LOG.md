# Build Log

Chronological record of major implementation prompts.

---


## Spread-bet-only lock + epic alignment

**Date**: 2026-02-15  
**Tests**: `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` (8 passed); `pnpm --filter solat-desktop build` (pass)

### Summary

Locked IG account selection toward spread-betting by default and added strict account-type enforcement support. Added account switching during login (with safe fallback when IG rejects account switching), account-aware execution state selection, terminal-side catalogue auto-bootstrap, and epic migration to spread-bet style epics (`TODAY/IFD`) so chart instruments align with IG spread-bet markets.

### Files Changed

- `engine/solat_engine/config.py`
- `engine/solat_engine/broker/ig/client.py`
- `engine/solat_engine/execution/router.py`
- `engine/solat_engine/catalog/seed.py`
- `engine/solat_engine/catalog/store.py`
- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/solat_engine/api/catalog_routes.py`
- `.env.example`
- `docs/ops/PROJECT_MEMORY.md`

---

## Adaptive 403 fallback + history-aware market ranking

**Date**: 2026-02-15  
**Tests**: `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` (8 passed); `pnpm --filter solat-desktop build` (pass)

### Summary

Implemented adaptive crypto history retrieval behavior in normalized `/bars` so IG 403-denied windows are handled with bounded retries, smaller backfill spans, and per-symbol cooloff. Added universe-level history capability metadata and crypto-tab sorting by history score to surface better symbols first. Updated chart sparse-data copy to remove stale gap-fill wording and provide actionable timeframe/symbol guidance.

### Files Changed

- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/tests/test_desktop_api_contract.py`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/components/workspace/MarketBrowser.tsx`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `docs/ops/PROJECT_MEMORY.md`

---

## Sparse crypto remediation update (1m-derived fallback) + gap-fill rollback

**Date**: 2026-02-15  
**Tests**: `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` (6 passed); `pnpm --filter solat-desktop build` (pass)

### Summary

Enhanced `/bars` fallback to fetch `1m` and derive higher timeframes when native crypto history is sparse, then persist both to cache for later requests. Removed UI synthetic candle gap-fill because it introduced misleading horizontal artifacts; chart now renders only real bars. Runtime logs confirm repeated IG historical `403` responses on crypto windows, consistent with account/instrument historical allowance limits.

### Files Changed

- `engine/solat_engine/api/ig_terminal_routes.py`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `docs/ops/PROJECT_MEMORY.md`

---

## Crypto sparse-history handling (UI gap-fill + diagnostics)

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass)

### Summary

Confirmed that low candle density on selected crypto CFDs is coming from IG historical coverage on this account/instrument set (while FX remains full). Added chart-level display gap-fill for sparse datasets to keep timeline continuity and reduce clustered-candle visuals. Added explicit sparse-data status hint in panel footer.

### Files Changed

- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `docs/ops/PROJECT_MEMORY.md`

---

## Sparse IG bars backfill + chart coverage telemetry

**Date**: 2026-02-15  
**Tests**: `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` (6 passed); `pnpm --filter solat-desktop build` (pass)

### Summary

Implemented sparse-history remediation in normalized `/bars` by backfilling from IG when cache coverage is below a timeframe-aware threshold, not only when empty. Added progressive date-range fallback passes for broader history hydration, and exposed response telemetry (`requested_limit`, `coverage_pct`, `source`) consumed by desktop status UI. Added bars-based initial x-range handling to improve first render framing.

### Files Changed

- `engine/solat_engine/api/ig_terminal_routes.py`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/hooks/useBars.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `docs/ops/PROJECT_MEMORY.md`

---

## Chart full-day window fix (lookback migration)

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass)

### Summary

Fixed chart sessions loading with too few candles by introducing timeframe-based minimum lookback bars and migrating persisted workspace panels that had undersized `lookbackBars`. `ChartPanel` now enforces this minimum when fetching bars, improving default 15m/1h/4h history coverage without manual zoom/pan.

### Files Changed

- `apps/desktop/src/lib/workspace.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `docs/ops/PROJECT_MEMORY.md`

---

## Chart header overlap fix (zoom/timescale controls)

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass)

### Summary

Fixed chart header crowding where the market control overlapped timescale/zoom controls. Removed the quick symbol strip, switched the market trigger to compact `MKT`, and tightened left/right header flex rules so right-side zoom + status controls remain stable and non-overlapping.

### Files Changed

- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/styles.css`
- `docs/ops/PROJECT_MEMORY.md`

---

## IG chart data root-cause fix + market tabs

**Date**: 2026-02-15  
**Tests**: `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` (6 passed); `pnpm --filter solat-desktop build` (pass)

### Summary

Resolved chart no-data behavior by fixing IG historical endpoint usage in the engine fetcher (`/prices/{epic}` with query params), adding IG-on-demand bars fallback in normalized `/bars`, and fixing `/universe` response mapping crash. Added IG-style market category tabs in chart header and tightened symbol normalization/workspace migration so symbol switching is deterministic. Updated crypto mapping to `BCHUSD` for an actually tradable IG instrument in this setup.

### Files Changed

- `engine/solat_engine/data/ig_history.py`
- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/solat_engine/catalog/seed.py`
- `engine/solat_engine/catalog/data/instruments.json`
- `engine/tests/test_desktop_api_contract.py`
- `apps/desktop/src/components/workspace/MarketBrowser.tsx` (new)
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/styles.css`
- `apps/desktop/src/lib/workspace.ts`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/hooks/useCatalogue.ts`
- `docs/ops/PROJECT_MEMORY.md`

---

## Chart symbol-switch hotfix + demo verification

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass)

### Summary

Fixed chart symbol switching reliability by removing the dropdown backdrop click blocker, normalizing symbol updates to uppercase, and adding quick crypto symbol buttons as a fallback path. Also fixed a TypeScript regression in `useBars` debug calls and hardened engine symbol map normalization for route lookup consistency.

### Files Changed

- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/hooks/useBars.ts`
- `engine/solat_engine/api/ig_terminal_routes.py`
- `docs/ops/PROJECT_MEMORY.md`

---

## Hardening pass: contract + anti-flicker + route centralization

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass); `cd engine && python3 -m pytest tests/test_desktop_api_contract.py tests/test_sweep_report.py -q` (73 passed)

### Summary

Added a deterministic desktop API contract doc and contract tests, centralized route strings behind a shared `ROUTES` map, removed dead legacy market hooks, and stabilized engine-online UX by moving screen consumers to shared connection context plus health-state hysteresis.

### Files Changed

- `docs/ops/DESKTOP_API_CONTRACT.md`
- `engine/tests/test_desktop_api_contract.py`
- `apps/desktop/src/lib/routes.ts`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/hooks/useEngineHealth.ts`
- `apps/desktop/src/screens/IntroScreen.tsx`
- `apps/desktop/src/screens/PlaygroundScreen.tsx`
- `apps/desktop/src/screens/AllowlistScreen.tsx`
- `apps/desktop/src/screens/BotsScreen.tsx`
- `apps/desktop/src/screens/DashboardScreen.tsx`
- `apps/desktop/src/hooks/useBrokerStatus.ts`
- `apps/desktop/src/components/status/BrokerConnectivityCard.tsx`
- `apps/desktop/src/hooks/useMarketStatus.ts` (deleted)
- `apps/desktop/src/hooks/useMarketSubscription.ts` (deleted)

---

## Desktop normalized-route follow-up sweep

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass)

### Summary

Completed a desktop-only follow-up migration so remaining route callers use the normalized IG terminal surface. Removed legacy UI dependence on market subscribe/status and IG status/login routes by mapping all affected flows to `/universe`, `/quotes`, and `/account`.

### Files Changed

- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/components/DemoChecklist.tsx`
- `apps/desktop/src/hooks/useBrokerStatus.ts`
- `apps/desktop/src/components/status/BrokerConnectivityCard.tsx`

---

## IG normalized terminal integration pass

**Date**: 2026-02-15  
**Tests**: `pnpm --filter solat-desktop build` (pass); `cd engine && python3 -m pytest tests/test_sweep_report.py -q` (67 passed)

### Summary

Implemented a shared app-level engine connection store to prevent route-driven WS churn, added canonical IG-style routes for account/quotes/bars/orders/positions, normalized WS event emission, added chart left-pan history prepend behavior, and wired parallel sweep output to canonical report generation.

### Files Changed

- `apps/desktop/src/App.tsx`
- `apps/desktop/src/context/EngineConnectionContext.tsx`
- `apps/desktop/src/hooks/useWsEvents.ts`
- `apps/desktop/src/hooks/useBars.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/lib/engineClient.ts`
- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/solat_engine/broker/ig/client.py`
- `engine/solat_engine/main.py`
- `engine/solat_engine/backtest/parallel_sweep.py`
- `docs/ig_integration.md`

---

## UI shell/screens refactor batch

**Date**: 2026-02-15
**Tests**: not run

### Summary

Updated desktop shell and status/backtest screens
Added new terminal screens and shared UI components
Adjusted Plotly wrapper and app/sidebar wiring

### Files Changed

- `apps/desktop/index.html`
- `apps/desktop/public/solat.svg`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/InfoTip.tsx`
- `apps/desktop/src/components/PlotlyChart.tsx`
- `apps/desktop/src/components/Sidebar.tsx`
- `apps/desktop/src/components/StatusScreen.tsx`
- `apps/desktop/src/components/StatusStrip.tsx`
- `apps/desktop/src/components/backtest/BacktestWizard.tsx`
- `apps/desktop/src/components/ui/EmptyState.tsx`
- `apps/desktop/src/components/ui/Modal.tsx`
- `apps/desktop/src/components/ui/Panel.tsx`
- `apps/desktop/src/components/ui/Popover.tsx`
- `apps/desktop/src/components/ui/SummaryBar.tsx`
- `apps/desktop/src/components/ui/Tooltip.tsx`
- `apps/desktop/src/components/ui/index.ts`
- `apps/desktop/src/screens/AllowlistScreen.tsx`
- `apps/desktop/src/screens/BacktestsScreen.tsx`
- `apps/desktop/src/screens/BlotterScreen.tsx`
- `apps/desktop/src/screens/BotsScreen.tsx`
- `apps/desktop/src/screens/OptimizationScreen.tsx`
- `apps/desktop/src/screens/PlaygroundScreen.tsx`

---

## Phase 4: Home page overhaul

**Date**: 2026-02-15

### Summary

Two-column layout with brand left and getting started tiles right, larger logo 72px, new tagline, full-click tile buttons with hover effects, responsive stacking below 900px, no-scroll discipline

---

## Phase 3: Dashboard overhaul

**Date**: 2026-02-15

### Summary

Replace mini chart with Control panel (Test Engine, Connect Broker, Sync History, Start DEMO), fix balance showing Not Connected instead of ---, equity curve always renders chart frame with annotation when empty, compact KPI row

---

## Phase 2: Chart overhaul

**Date**: 2026-02-15

### Summary

Fix pan snap-back (stabilized shapes, dynamic uirevision), increase bars 500->2000, signal markers with white outline and dynamic offset, SL/TP shaded zones with outcome hit markers, zoom buttons (1D/1W/1M/3M/ALL), remove 6-chart layout, add focus mode, live/HIST badge, toolbar rationalized with overflow menu, drawing tools in overflow

---

## Phase 1: Remove debug fetch calls

**Date**: 2026-02-15

### Summary

Removed DEBUG_INGEST_URL constant and 4 debug fetch blocks from useWsEvents.ts that fire failed HTTP requests to non-running debug server on every WS event

---

## Merge main into release branch

**Date**: 2026-02-14
**Tests**: merge completed; conflicts resolved

### Summary

Merged origin/main into release/v3.1.0-alpha1 with release-preferred conflict resolution
Retained release branch canonical docs layout and restored expected deletions

### Files Changed

- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/hooks/useSignals.ts`
- `apps/desktop/src/screens/LibraryScreen.tsx`

---
## Backtest CLI Fix + Valid Sizing + Range Mode CLI

**Date**: 2026-02-14
**Tests**: 839 existing + 8 new = 847 passing

### Summary

Fixed `run_backtest.py` crash from datetime slicing (`ds[:10]` on datetime objects), fixed Symbol: None in reports, eliminated mass order rejections by adding `max_size` clamp to sizing and defaulting CLI to `FIXED_SIZE`, fixed `bars_per_day` not being passed from engine to metrics (caused wrong duration_days/missing_bar_pct), added `--range-mode max_available` to CLI, and added project memory/build log enforcement to CLAUDE.md.

### Modified Files (5)

- `engine/scripts/run_backtest.py` — `fmt_dt()` helper, G section in report, `--range-mode` flag, fixed-size default
- `engine/solat_engine/backtest/sizing.py` — `max_size=100.0` clamp in `calculate_position_size()`
- `engine/solat_engine/backtest/engine.py` — symbol pass-through to metrics, `bars_per_day` computed from timeframe
- `engine/tests/test_platform_contracts.py` — 8 new tests (4 sizing safety + 4 CLI report helpers)
- `CLAUDE.md` — added Project Memory & Build Log rule

### New Files (1)

- `engine/scripts/smoke_sweep_benchmark.py` — cache ON/OFF benchmark script

---

## "Finished Platform" Outputs + Validation + Speed

**Date**: 2026-02-14
**Tests**: 819 existing + 20 new = 839 passing

### Summary

Added authoritative platform documentation (`PLATFORM_END_STATE.md`, `REQUIRED_BACKTEST_OUTPUTS.md`), contract tests for scoring/WF field completeness, `duration_days` and `missing_bar_pct` population in MetricsSummary, `RangeMode.MAX_AVAILABLE` for backtests without explicit dates, `GET /data/available-range` endpoint, and ParquetStore DataFrame LRU cache for sweep speed-up.

### New Files (3)

- `engine/docs/ops/PLATFORM_END_STATE.md` — documents all 8 pipeline stages
- `engine/docs/ops/REQUIRED_BACKTEST_OUTPUTS.md` — authoritative field checklists with scoring mapping
- `engine/tests/test_platform_contracts.py` — 20 contract tests (5 classes)

### Modified Files (5)

- `engine/solat_engine/backtest/models.py` — `duration_days` field, `RangeMode` enum, optional start/end, validator
- `engine/solat_engine/backtest/metrics.py` — populate `duration_days` + `missing_bar_pct`
- `engine/solat_engine/backtest/engine.py` — resolve `max_available` range from manifests
- `engine/solat_engine/data/parquet_store.py` — `get_available_range()`, DataFrame LRU cache, cache invalidation
- `engine/solat_engine/api/data_routes.py` — `GET /data/available-range` endpoint

---

## Project Memory + Sweep Reset Utility

**Date**: 2026-02-14
**Tests**: 819 passing (no changes to engine code)

### Summary

Established an enforced project memory logging system and a safe sweep artefact reset utility. Created `docs/ops/PROJECT_MEMORY.md` as the canonical reverse-chronological log, `scripts/update_project_memory.py` as the entry helper, pre-commit hook + CI guard for enforcement, and `engine/scripts/reset_sweep_artefacts.py` for safely archiving old sweep/tuning/portfolio artefacts before a fresh Grand Sweep.

### New Files

- `docs/ops/PROJECT_MEMORY.md` — reverse-chronological project log with current state snapshot
- `scripts/update_project_memory.py` — stdlib-only helper to prepend entries to both log files
- `.githooks/pre-commit` — blocks commits changing code without log updates
- `scripts/install_githooks.sh` — configures git hooks path
- `.github/workflows/log_guard.yml` — CI guard for PRs/pushes
- `engine/scripts/reset_sweep_artefacts.py` — archive/delete utility for sweep artefacts
- `engine/docs/ops/RESET_SWEEP_ARTEFACTS.md` — reset procedure documentation

---

## PROMPT 072 — Tuning Pipeline

**Date**: 2026-02-14
**Tests**: 749 existing + 70 new = 819 passing

### Summary

Built a complete Sweep -> Tune Variants -> Walk-Forward -> Score -> Portfolio pipeline. Created scoring system (hard gates + weighted 0-100), per-bot Optuna search spaces, 2-stage param tuner, diversified portfolio builder with currency/bot/TF caps, CLI scripts for tuning and portfolio construction, and comprehensive tests.

### New Files (9)

- `engine/solat_engine/data/ohlcv_validator.py` — OHLCV data quality checks
- `engine/solat_engine/optimization/search_space.py` — per-bot search spaces + param conversion
- `engine/solat_engine/optimization/scoring.py` — hard gates + weighted 0-100 scorer
- `engine/solat_engine/optimization/portfolio_builder.py` — diversified portfolio builder
- `engine/solat_engine/optimization/tuner.py` — 2-stage Optuna param tuner
- `engine/scripts/run_tuning.py` — tuning CLI
- `engine/scripts/build_portfolio.py` — portfolio builder CLI
- `engine/docs/ops/TUNING_PIPELINE_V1.md` — pipeline documentation
- `engine/tests/test_tuning_pipeline.py` — 70 tests across 9 test classes

### Modified Files (5)

- `engine/solat_engine/backtest/models.py` — params_override + extended MetricsSummary
- `engine/solat_engine/backtest/engine.py` — threads params through strategy factory
- `engine/solat_engine/backtest/parallel_sweep.py` — 13th arg for params passthrough
- `engine/solat_engine/backtest/metrics.py` — trades_per_day, equity_peak, best/worst 5
- `engine/solat_engine/optimization/models.py` — AllowlistEntry extended with variant_id, score, evidence

---

## PROMPT 021 HARDENING — Desktop Error UX & Validation Tests

**Date**: 2026-02-11
**Tests**: 650 existing + 1 new validation test = 651 passing

### Summary

Improved Desktop UI error rendering to use structured error fields (`error_type`, `error_message`) with "Try Again" buttons. Added validation tests for backtest input errors (invalid bots, symbols, timeframes). Enhanced `BacktestRunViewer` to display `results.errors` for failed runs.

### Modified Files (3) + New Files (1)

| File | Changes |
|------|---------|
| `apps/desktop/src/components/backtest/BacktestWizard.tsx` | Enhanced failed status display with `error_type` heading, `error_message` detail, and "Try Again" button that resets wizard |
| `apps/desktop/src/components/backtest/BacktestRunViewer.tsx` | Added failed backtest section (distinct from loading errors) that displays `results.errors` array when `ok: false` |
| `engine/tests/test_backtest_data_errors.py` | **New**: Validation test for bot names (symbols/timeframes accepted but treated as "no data") |

### Key Decisions

- **Structured error display**: UI now shows `error_type` as heading and `error_message` as detail, making diagnostics actionable
- **Retry UX**: Both wizard failure states provide "Try Again" button to reset and restart
- **Distinction between loading vs backtest errors**: BacktestRunViewer differentiates "failed to fetch results" (HTTP error) from "backtest failed" (ok: false with errors)
- **Lenient validation**: Engine validates bots (statically known) but accepts any symbols/timeframes (just returns "no data" warning for unknown ones)

### Impact

- ✅ Users see clear, structured error messages instead of generic "Backtest failed"
- ✅ Quick retry flow for transient errors
- ✅ Failed backtest runs show specific error details from results
- ✅ 651 tests pass (zero regressions)

---

## PROMPT 021 FIX — Backtest Event Loop & Error Diagnostics

**Date**: 2026-02-11
**Tests**: 648 existing + 1 new event-loop safety test = 649 passing

### Summary

Fixed critical "no running event loop" bug when running backtests from the Desktop UI. Root cause: `asyncio.create_task()` was called from `run_in_executor` thread pool workers, which have no event loop. Added structured error diagnostics (`error_type`, `error_message`) for failed backtests and sweeps.

### Modified Files (5)

| File | Changes |
|------|---------|
| `engine/solat_engine/api/backtest_routes.py` | Fixed async progress callbacks in `_run_backtest_job` and `_run_sweep_job` using `loop.call_soon_threadsafe(loop.create_task, ...)` with try/except wrapper; added `error_type`/`error_message` fields to `StatusResponse` and `SweepStatusResponse`; improved failed task cleanup |
| `apps/desktop/src/lib/engineClient.ts` | Added `error_type?` and `error_message?` to `BacktestStatusResponse` |
| `apps/desktop/src/hooks/useBacktestRunner.ts` | Hook now surfaces structured errors from failed backtests to UI (`error_type: error_message`) |
| `engine/tests/test_backtest_endpoints.py` | Added `TestNoRunningEventLoopFix::test_backtest_completes_without_event_loop_error` to verify fix |
| `engine/tests/test_sweep_failure.py` | New test for sweep validation errors |

### Key Decisions

- **Thread-safe progress marshaling**: Capture `loop` before entering executor, use `loop.call_soon_threadsafe(loop.create_task, coro)` to schedule async callbacks from worker threads
- **Best-effort progress**: Wrapped in `try/except RuntimeError` so progress reporting never crashes the backtest
- **Structured error payloads**: Backtest and sweep status responses now include `error_type` (exception class) and `error_message` for actionable diagnostics
- **Failed task cleanup**: Tasks that raise exceptions are removed from active job maps to prevent repeated 500 errors

### Impact

- ✅ Backtests run from UI without "no running event loop" crashes
- ✅ Failed runs show structured error details instead of generic 500
- ✅ 649 tests pass (zero regressions)

---

## PROMPT 020 — Close the Loop

**Date**: 2026-02-09
**Tests**: 562 existing + ~27 new (recommendation + autopilot)

### Summary

Wired the optimisation pipeline end-to-end: WFO results → recommended set → allowlist → DEMO autopilot execution.

### New Files (12)
| File | Purpose |
|------|---------|
| `engine/solat_engine/optimization/recommended_set.py` | RecommendedSet model + manager |
| `engine/solat_engine/api/recommendation_routes.py` | REST endpoints for recommendations |
| `engine/solat_engine/autopilot/__init__.py` | Package init |
| `engine/solat_engine/autopilot/service.py` | AutopilotService (event-driven loop) |
| `engine/solat_engine/api/autopilot_routes.py` | REST endpoints for autopilot |
| `engine/tests/test_recommendation_routes.py` | Recommendation tests (~12) |
| `engine/tests/test_autopilot.py` | Autopilot tests (~15) |
| `apps/desktop/src/hooks/useRecommendations.ts` | Recommendations data hook |
| `apps/desktop/src/hooks/useAutopilot.ts` | Autopilot state hook |
| `apps/desktop/src/hooks/useFlashOnChange.ts` | Numeric flash utility |
| `docs/DEMO_AUTOPILOT.md` | Autopilot documentation |
| `docs/BUILD_LOG.md` | This file |

### Modified Files (11)
| File | Changes |
|------|---------|
| `engine/solat_engine/runtime/event_bus.py` | +5 EventType values |
| `engine/solat_engine/main.py` | Register routers, init autopilot, WS forwarding, shutdown |
| `engine/tests/conftest.py` | Reset new singletons |
| `apps/desktop/src/lib/engineClient.ts` | +5 types, +9 methods |
| `apps/desktop/src/screens/OptimizationScreen.tsx` | Recommendations card + grouped combos |
| `apps/desktop/src/components/StatusScreen.tsx` | Autopilot card + memo'd sub-components + flash |
| `apps/desktop/src/screens/BlotterScreen.tsx` | Enhanced empty states mentioning autopilot |
| `apps/desktop/src/screens/BacktestsScreen.tsx` | Enhanced empty state CTA |
| `apps/desktop/src/styles.css` | Recommendation, autopilot, flash animation styles |
| `docs/ROADMAP.md` | Added PROMPT 020 section |

### Key Decisions
- **Event-driven autopilot**: Subscribes to `BAR_RECEIVED` rather than polling, keeping latency low
- **Bounded deques**: Bar buffers use `maxlen` to prevent memory growth
- **LIVE fail-closed**: Both service-level and route-level checks block LIVE mode
- **Supersede semantics**: Applying a new recommended set marks previous as "superseded"

---

## PROMPT 012 — Stabilization pass (tests + settings + docs truth)

**Date**: 2026-02-08
**Tests**: Verified all 495 engine tests pass (15/15 execution endpoint tests green)

### Summary

Stabilization pass completed for desktop error handling, Tauri plugin config safety, and documentation alignment. Added "Copy Error Details" in ErrorBoundary, fixed Tauri v2 plugin config null-object mismatches, and updated phase documentation to match delivered UI components.

---

## PROMPT 010 complete — LIVE Trading Gating + Account Lock + Reconciliation v2

**Date**: 2026-02-01
**Tests**: Added 42 comprehensive tests in `test_live_gates.py`

### Summary

Implemented multi-layer LIVE safety gates, order state machine lifecycle controls, UI live-confirmation workflow, and reconciliation reporting endpoints. ExecutionRouter now enforces gate checks on arm and routing in LIVE mode.

---

## Phase 008 started — Workspace + Multi-chart + Strategy config + Backtest viewer

**Date**: 2026-02-01

### Summary

Prompt 008 scope initiated: workspace persistence, multi-panel layout presets, strategy config UX, backtest viewer/compare workflow, and UI performance hardening.

---

## Phase 007 complete — Terminal UI v1 (Desktop)

**Date**: 2026-02-01

### Summary

Delivered end-to-end terminal UI flow with route navigation, typed engine client integration, candlestick chart overlays/signals, WebSocket event handling, and supporting data hooks.

---

## Phase 006 complete — Realtime market data backend + overlays/signals endpoints

**Date**: 2026-02-01

### Summary

Implemented quote/bar models, polling + streaming scaffolding, deterministic bar builder, EventBus publishing, market subscribe/status routes, chart overlays/signals endpoints, and realtime bar persistence support with tests.

---

## Phase 005 complete — Live execution v1 (IG DEMO) + reconciliation + safety gates

**Date**: 2026-02-01

### Summary

Implemented execution state models, signal-to-order routing, risk caps, kill switch, reconciliation sync, append-only audit ledger, and execution control endpoints with desktop integration and test coverage.

---

## Phase 004 complete — Backtest engine v1 + Elite 8 runtime + sweep runner

**Date**: 2026-02-01

### Summary

Delivered deterministic bar-driven backtest runtime with broker simulator, portfolio accounting, metrics, artefacts, WS progress events, and batch sweep APIs, plus Elite 8 strategies and indicators.

---

## Phase 003 complete — Historical data layer (IG -> Parquet) + aggregation + quality + sync jobs

**Date**: 2026-02-01

### Summary

Built chunked IG history fetch, Parquet upsert/dedupe store, deterministic aggregation chain, quality checks/reports, and async sync jobs with progress events and APIs.

---

## Phase 002 complete — IG REST auth + instrument catalogue

**Date**: 2026-02-01

### Summary

Implemented AsyncIGClient session handling with rate limiting/redaction, IG account/search/status endpoints, and a bootstrap-able local instrument catalog with enrichment support and tests.

---

## Phase 001 complete — Repo foundations + engine/UI boot path

**Date**: 2026-02-01

### Summary

Established monorepo structure, engine health/config/ws baseline, logging/settings primitives, core domain/interfaces/runtime scaffolding, CI, and a working Tauri desktop shell.

---

## ROADMAP updated — phase status aligned to reality

**Date**: 2026-02-01

### Summary

Updated phase completion tracking in roadmap to reflect implemented modules and actual in-progress state.

---

## README updated — capabilities + config expanded

**Date**: 2026-02-01

### Summary

Expanded README feature set, quick-start/run commands, configuration table coverage, and current-status narrative to match delivered functionality.

---
