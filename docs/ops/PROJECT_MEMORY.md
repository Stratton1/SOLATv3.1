# SOLAT Project Memory

Reverse-chronological log of all changes, decisions, and results.
Updated for every meaningful code change (enforced via pre-commit hook and CI guard).

## Current State Snapshot

| Item | Value |
|------|-------|
| **Branch** | `release/v3.1.0-alpha1` |
| **Tests** | 924 passing, 0 failing |
| **Phases complete** | 001-069 (foundations through terminal UI), 070 A-D+G (go-live hardening), 072 (tuning pipeline), Platform Outputs, CLI Fix + Sizing, Smoke-test fixes (A-C) |
| **Phases pending** | Phase D (paper trading 48h), Phase E (go-live checklist) |
| **Grand Sweep** | 180 combos (9 bots x 10 FX x 2 TFs), 21 min, all successful |
| **Top performer** | CloudTwist/USDJPY/4h — Sharpe 28.5, 66.7% win rate |
| **Broken bots** | ChikouConfirmer (0 trades), ReversalHunter (0 trades on 2024 data) |
| **Key docs** | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LIVE_RUNBOOK.md`, `engine/docs/ops/TUNING_PIPELINE_V1.md` |

---


## 2026-02-16T21:43:42Z — Spread-bet normalization, bootstrap rate-limiting, paper trading endpoints

**What changed**
- Phase A: Fix spread-bet quote pricing — derive scaling_factor from pip_size for .TODAY./.IFD. epics across /quotes, polling, streaming, controller. Phase B: Staggered enrichment with backoff + retry-failed endpoint (failures 19→3). Phase C: Add /execution/preflight, /paper-start, /paper-stop composite endpoints. 924 tests passing, smoke-tested against IG DEMO.

---

## 2026-02-15T06:45:00Z — Spread-bet-only account lock + epic migration to IG TODAY/IFD style

**What changed**
- Enforced IG account selection by required account type with strict mode defaults:
 - Enforced IG account selection by required account type with strict-mode support:
  - added `IG_REQUIRED_ACCOUNT_TYPE` (default `SPREADBET`)
  - added `IG_STRICT_ACCOUNT_TYPE` (default `false`)
  - login now selects/switches to matching account via `PUT /session`; if switching is not supported by IG on this account context, it logs a warning and continues unless strict mode is enabled
- Updated execution broker connect/balance refresh to use the selected IG account (not simply first account in list)
- Added catalogue epic synchronization method to migrate existing symbols from stale CFD/MINI epics to seed-defined spread-bet epics when spread-bet mode is active
- Updated terminal catalogue dependency to auto-bootstrap if empty and auto-apply spread-bet epic sync for IG terminal routes
- Updated catalogue bootstrap/enrichment to prefer spread-bet-style epics (`.TODAY.` / `.IFD.`) and use live-style seed epics in spread-bet mode (even in demo environment)
- Added explicit spread-bet crypto seed epics (`BCHUSD/ETHUSD/LTCUSD/XRPUSD`) to keep crypto tabs populated with IG spread-bet symbols
- Added new `.env.example` keys for account-type enforcement

**Files**
- `engine/solat_engine/config.py`
- `engine/solat_engine/broker/ig/client.py`
- `engine/solat_engine/execution/router.py`
- `engine/solat_engine/catalog/seed.py`
- `engine/solat_engine/catalog/store.py`
- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/solat_engine/api/catalog_routes.py`
- `.env.example`

**Verification**
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` passed (8 tests)
- `pnpm --filter solat-desktop build` passed
- Lint diagnostics clean for modified files

---


## 2026-02-15T06:27:00Z — Adaptive 403 backfill + universe history scoring + sparse UX cleanup

**What changed**
- Implemented adaptive `/bars` fallback logic for IG 403-limited windows:
  - bounded retry attempts,
  - 403-aware window step-down (smaller spans instead of widening),
  - per symbol/timeframe 403 cooloff cache to prevent retry storms
- Kept and tightened 1m-derived fallback path for sparse higher timeframes (aggregate 1m into requested TF and persist alongside native bars)
- Added `/universe` history capability fields (timeframe-aware): `history_row_count`, `history_score`, `history_supported`
- Updated market browser crypto tab ranking to prioritize higher history score and show quick `Hxx` score hints
- Replaced stale sparse status text in chart panel with explicit guidance:
  - `IG history limited for <symbol> <tf> (try 1h/4h or another crypto in MKT)`
- Added contract regression tests:
  - `/bars` telemetry fields
  - bounded 403 fallback behavior
  - `/universe` includes history capability fields

**Files**
- `engine/solat_engine/api/ig_terminal_routes.py`
- `engine/tests/test_desktop_api_contract.py`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/components/workspace/MarketBrowser.tsx`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`

**Verification**
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` passed (8 tests)
- `pnpm --filter solat-desktop build` passed
- Live probe after changes:
  - `BCHUSD 5m`: 355 bars (44.38%) `cache+ig_fallback`
  - `BCHUSD 15m`: 171 bars (21.38%) `cache+ig_fallback`
  - `ETHUSD 15m`: 80 bars (10%) `cache`
- Lint diagnostics clean for modified files

---

## 2026-02-15T06:28:00Z — Sparse crypto history hardening (1m-derived fallback) + removed synthetic chart candles

**What changed**
- Reworked IG sparse-history remediation in `/bars` route to also fetch `1m` bars and derive requested higher timeframe (`5m/15m/1h/4h`) via deterministic aggregation when native higher-TF history is thin
- Persisted both fetched `1m` and derived timeframe bars to parquet during fallback to improve subsequent chart requests
- Removed UI synthetic gap-fill candles from `ChartPanel` (the flat horizontal artifacts), restoring chart display to real bars only

**Observed runtime evidence**
- Engine boot logs show repeated IG historical `403` responses during aggressive crypto backfill windows, which explains incomplete history despite fallback attempts
- FX symbols continue to return full coverage while several crypto symbols remain sparse under current IG constraints

**Files**
- `engine/solat_engine/api/ig_terminal_routes.py`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`

**Verification**
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` passed (6 tests)
- `pnpm --filter solat-desktop build` passed
- Lint clean for touched files

---

## 2026-02-15T06:22:00Z — Crypto sparse-history explanation hardening + UI gap-fill display

**What changed**
- Confirmed via live probes that `/bars` telemetry is active and indicates low IG coverage on crypto CFDs (e.g. `BCHUSD/ETHUSD/LTCUSD` at ~10–20%) while FX symbols return full coverage
- Added chart-rendering-only gap-fill for sparse IG series: synthetic flat candles are inserted between missing intervals so timeline appears continuous without mutating engine truth
- Added status hint for sparse data mode (`ig sparse data (display gap-fill on)`) so users can distinguish broker sparsity from app failure

**Files**
- `apps/desktop/src/components/workspace/ChartPanel.tsx`

**Verification**
- `pnpm --filter solat-desktop build` passed
- Lint clean on modified file
- Live endpoint probes:
  - `EURUSD/USDJPY 15m`: `800/800` (`100%`)
  - `BCHUSD/LTCUSD/ETHUSD 15m`: low coverage with `cache+ig_fallback`

---

## 2026-02-15T06:15:00Z — Sparse IG bars backfill remediation + chart coverage telemetry

**What changed**
- Updated normalized engine `/bars` route to treat sparse cache as backfill-worthy (not just empty cache), using timeframe-aware minimum expected bars
- Added progressive IG date-range fallback loop (up to 3 widening passes) to hydrate cache when initial history is too thin for requested chart windows
- Added bars response telemetry fields (`requested_limit`, `coverage_pct`, `source`) so desktop can observe whether data came from cache or IG fallback
- Wired desktop bars types + hook state to consume coverage/source metadata
- Added chart panel status coverage display (`cov loaded/requested`, percent, source) and bars-based initial x-range to reduce apparent compression from non-candle traces

**Files**
- `engine/solat_engine/api/ig_terminal_routes.py`
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/hooks/useBars.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`

**Verification**
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` passed (6 tests)
- `pnpm --filter solat-desktop build` passed
- `GET /bars` probe on currently running engine still showed old shape (`requested_limit` absent), indicating runtime process restart required to pick up new route code

---

## 2026-02-15T06:03:00Z — Chart bars window fix (full-day coverage on timeframe switch)

**What changed**
- Fixed truncated chart history caused by persisted low `lookbackBars` values in workspace state
- Added timeframe-aware minimum lookback floors (`1m`/`5m`/`15m`/`1h`/`4h`/`1d`) in workspace model
- Added workspace migration to auto-upgrade existing panels to a safe minimum lookback window
- Updated `ChartPanel` to enforce minimum bars at request time, so `/bars` receives enough history for full-session/day context

**Files**
- `apps/desktop/src/lib/workspace.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`

**Verification**
- `pnpm --filter solat-desktop build` passed
- No lints in touched files

---

## 2026-02-15T05:57:00Z — Chart header overlap fix (zoom/timescale controls)

**What changed**
- Removed quick crypto symbol strip from chart header to reduce control density (market switching remains via IG-style `MKT` browser tabs)
- Added dedicated compact `MKT` trigger styling to reduce width in right-side control cluster
- Tuned panel header flex behavior (`panel-header-left` min-width + `panel-header-right` non-shrinking) so zoom presets and badges no longer overlap

**Files**
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/styles.css`

**Verification**
- `pnpm --filter solat-desktop build` passed
- No lints in touched files (`ChartPanel.tsx`, `styles.css`)

---

## 2026-02-15T05:46:00Z — IG data-path root-cause fix + IG-style market tabs

**What changed**
- Fixed root cause for chart no-data from IG history fetcher: corrected IG `/prices` REST path format to use query params (`/prices/{epic}?resolution=...&max=...`), replacing invalid path-style requests returning 404
- Fixed `/universe` runtime crash by removing invalid catalogue field access and mapping response fields from actual model attributes
- Added IG-first bars fallback in normalized `/bars` route: when local cache is empty, fetch recent bars from IG, persist to parquet, then return normalized bars payload
- Added fallback-throttle on bars backfill failures (60s block per symbol/timeframe) to avoid rapid repeated IG calls on temporary errors
- Added IG-style market browser to chart header (asset tabs: FX / Indices / Commodities / Crypto / Shares) with click-to-load symbol behavior
- Added symbol canonicalization + workspace migration: uppercase normalization and legacy `BTCUSD` workspace value remap to `BCHUSD`
- Corrected crypto seed/catalogue mapping from non-working `BTCUSD -> CS.D.BCHXBT.CFD.IP` to tradable `BCHUSD -> CS.D.BCHUSD.CFD.IP`

**Files**
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

**Verification**
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py -q` passed (`6 passed`)
- `pnpm --filter solat-desktop build` passed
- In-process endpoint checks:
  - `/universe` returns `200`
  - `/bars?symbol=ETHUSD&tf=15m&limit=20` returns bars
  - `/bars?symbol=XRPUSD&tf=15m&limit=20` returns bars
  - `/bars?symbol=BCHUSD&tf=15m&limit=20` returns bars

---

## 2026-02-15T18:05:00Z — Chart symbol-switch hotfix + demo verification

**What changed**
- Fixed chart symbol selector interaction by removing the backdrop interceptor and using outside-click detection via ref
- Normalized symbol updates to uppercase in `ChartPanel` so mixed-case symbols do not break bars/quotes requests
- Added quick crypto symbol buttons in chart header as a fallback switch path
- Fixed `useBars` debug calls to `globalThis.fetch` to avoid TypeScript shadowing/compile failure
- Hardened IG terminal symbol lookup map to uppercase keys for normalized route resolution

**Files**
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/hooks/useBars.ts`
- `engine/solat_engine/api/ig_terminal_routes.py`

**Verification**
- `pnpm --filter solat-desktop build` passed
- Engine checks:
  - `/config` => `mode=DEMO`
  - `/execution/status` => `mode=DEMO`, `connected=true`
  - `/account` => account status returned
  - `/bars?symbol=USDJPY&tf=15m&limit=50` => bars returned

---

## 2026-02-15T17:35:00Z — Hardening pass: desktop contract, route centralization, anti-flicker connectivity

**What changed**
- Added explicit desktop contract document for normalized API usage (`/health`, `/config`, `/universe`, `/quotes`, `/bars`, `/account`, `/positions`, `/orders/market`)
- Added engine-side contract regression tests (`engine/tests/test_desktop_api_contract.py`) validating OpenAPI paths and minimum response fields without live IG dependency
- Centralized desktop route strings through `ROUTES` contract and runtime contract assertion in `engineClient`
- Removed orphaned legacy hooks (`useMarketStatus`, `useMarketSubscription`) and marked legacy client methods as `@deprecated`
- Eliminated page-scoped health hook usage in key screens by switching to app-level `EngineConnectionContext`
- Added connection hysteresis in `useEngineHealth` (failure threshold + grace window) to avoid transient offline flashes during navigation/poll blips

**Files**
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

**Verification**
- `pnpm --filter solat-desktop build` passed
- `cd engine && python3 -m pytest tests/test_desktop_api_contract.py tests/test_sweep_report.py -q` passed (`73 passed`)

---

## 2026-02-15T17:05:00Z — Desktop follow-up migration to normalized routes

**What changed**
- Migrated remaining desktop route callers away from legacy `market/*`, `ig/*`, and catalog instrument routes
- Updated `engineClient` to use normalized `/universe`, `/quotes`, `/account` mappings
- Reworked chart panel to use normalized quote polling fallback (no legacy subscribe/status calls)
- Replaced DEMO checklist run-once action with normalized market order endpoint
- Reworked broker status/test flows to use normalized account endpoint instead of legacy IG status/login endpoints

**Files**
- `apps/desktop/src/lib/engineClient.ts`
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/components/DemoChecklist.tsx`
- `apps/desktop/src/hooks/useBrokerStatus.ts`
- `apps/desktop/src/components/status/BrokerConnectivityCard.tsx`

**Verification**
- Tests: `pnpm --filter solat-desktop build`
- Results: pass

---

## 2026-02-15T16:35:00Z — IG normalized routes + shared WS store + chart history prepend

**What changed**
- Added app-level engine connection provider so desktop uses one shared health/WS stream
- Refactored WS event hook to consume shared stream instead of opening per-panel sockets
- Added canonical IG-style API surface (`/account`, `/positions`, `/orders`, `/universe`, `/quotes`, `/bars`, `/orders/*`, `/positions/*`)
- Added IG client support for working-order placement and position amendment
- Normalized WS forwarding to `quote_update`, `bar_update`, `order_event`, `position_event`
- Added left-pan history expansion in chart hooks/panel with prepend + dedupe behavior
- Ensured parallel sweep writes canonical sweep report sidecars via shared reporting module
- Added integration documentation: `docs/ig_integration.md`

**Files**
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

**Verification**
- Tests: `pnpm --filter solat-desktop build`; `cd engine && python3 -m pytest tests/test_sweep_report.py -q`
- Results: desktop build passed; `tests/test_sweep_report.py` passed (67/67)

---

## 2026-02-15T02:27:56Z — UI shell/screens refactor batch

**What changed**
- Updated desktop shell and status/backtest screens
- Added new terminal screens and shared UI components
- Adjusted Plotly wrapper and app/sidebar wiring

**Files**
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

**Verification**
- Tests: `not run`
- Results: not run

---

## 2026-02-15T02:26:44Z — Phase 4: Home page overhaul

**What changed**
- Two-column layout with brand left and getting started tiles right, larger logo 72px, new tagline, full-click tile buttons with hover effects, responsive stacking below 900px, no-scroll discipline

---

## 2026-02-15T02:26:32Z — Phase 3: Dashboard overhaul

**What changed**
- Replace mini chart with Control panel (Test Engine, Connect Broker, Sync History, Start DEMO), fix balance showing Not Connected instead of ---, equity curve always renders chart frame with annotation when empty, compact KPI row

---

## 2026-02-15T02:26:18Z — Phase 2: Chart overhaul

**What changed**
- Fix pan snap-back (stabilized shapes, dynamic uirevision), increase bars 500->2000, signal markers with white outline and dynamic offset, SL/TP shaded zones with outcome hit markers, zoom buttons (1D/1W/1M/3M/ALL), remove 6-chart layout, add focus mode, live/HIST badge, toolbar rationalized with overflow menu, drawing tools in overflow

---

## 2026-02-15T02:26:07Z — Phase 1: Remove debug fetch calls

**What changed**
- Removed DEBUG_INGEST_URL constant and 4 debug fetch blocks from useWsEvents.ts that fire failed HTTP requests to non-running debug server on every WS event

---

## 2026-02-14T23:57:49Z — Merge main into release branch

**What changed**
- Merged origin/main into release/v3.1.0-alpha1 with release-preferred conflict resolution
- Retained release branch canonical docs layout and restored expected deletions

**Files**
- `apps/desktop/src/components/workspace/ChartPanel.tsx`
- `apps/desktop/src/hooks/useSignals.ts`
- `apps/desktop/src/screens/LibraryScreen.tsx`

**Verification**
- Tests: `git merge --no-ff -X ours origin/main`
- Results: merge completed; conflicts resolved

---
## 2026-02-14T23:45:00Z — Backtest CLI Fix + Valid Sizing + Range Mode CLI

**Goal**
- Fix `run_backtest.py` crash from datetime slicing (breaking change from Platform Outputs prompt)
- Fix Symbol: None in reports
- Eliminate mass order rejections from sizing explosion
- Add `--range-mode max_available` to CLI
- Run controlled smoke sweep benchmark

**What changed**
- Fixed `run_backtest.py`: added `fmt_dt()` helper for datetime/string handling
- Added Section G (Extended) to CLI report: trades_per_day, equity_peak, missing_bar_pct
- Fixed `Symbol: None` — engine now passes `symbol=` to `compute_metrics_summary()` for single-symbol backtests
- Added `max_size=100.0` clamp to `calculate_position_size()` — prevents sizing explosion
- Changed CLI default to `FIXED_SIZE` with 1.0 lots (was RISK_PER_TRADE which exploded)
- Fixed `bars_per_day` not being passed from engine to metrics — now computed from timeframe
- Added `--range-mode` CLI flag with `fixed_window`/`max_available` choices
- Added `--fixed-size` default of 1.0 (was None)
- Added 8 new tests: 4 sizing safety + 4 CLI report helpers
- Added Project Memory + Build Log update rule to CLAUDE.md
- Created smoke sweep benchmark script

**Test results**: 847 passing, 0 failing (was 839)

**Files changed**:
- `engine/scripts/run_backtest.py` — fmt_dt(), G section, range-mode, fixed-size defaults
- `engine/solat_engine/backtest/sizing.py` — max_size clamp in calculate_position_size()
- `engine/solat_engine/backtest/engine.py` — symbol pass-through, bars_per_day computation
- `engine/tests/test_platform_contracts.py` — 8 new tests (sizing safety + CLI helpers)
- `CLAUDE.md` — project memory/build log rule added

---

## 2026-02-14T23:30:00Z — "Finished Platform" Outputs + Validation + Speed

**Goal**
- Document what the platform produces at every pipeline stage
- Add contract tests ensuring scoring/WF fields stay populated
- Add flexible `max_available` range mode for backtests
- Speed up sweeps with ParquetStore caching

**What changed**
- Created `engine/docs/ops/PLATFORM_END_STATE.md` — documents all 8 pipeline stages
- Created `engine/docs/ops/REQUIRED_BACKTEST_OUTPUTS.md` — authoritative field checklists
- Added `duration_days` field to MetricsSummary, populated in `compute_metrics_summary()`
- Fixed `missing_bar_pct` population (was always 0.0, now computed from expected vs actual bars)
- Added `RangeMode` enum (`fixed_window`/`max_available`) + optional start/end to `BacktestRequest`
- Added `get_available_range()` to ParquetStore (reads manifests)
- Engine resolves max_available dates from manifests before running backtest
- Added `GET /data/available-range` endpoint
- Added DataFrame LRU cache (maxsize=20) to `ParquetStore._read_partition_df()`
- Added cache invalidation on writes and partition clears
- Created 20 contract tests in `engine/tests/test_platform_contracts.py`

**Verification**
- Tests: `cd engine && python3 -m pytest tests/ -v`
- Results: 839 passed, 0 failed (819 existing + 20 new)

**Decisions**
- Cache uses FIFO eviction (dict insertion order) rather than LRU for simplicity
- max_available resolves to widest range across all requested symbols
- missing_bar_pct uses 5/7 trading day approximation for FX

**Next steps**
- Run a sweep with cache to measure speed improvement
- Consider indicator-level caching for further sweep acceleration

---

## 2026-02-14T22:00:00Z — Project Memory + Sweep Reset (Bootstrap)

**Goal**
- Establish an enforced project memory logging system and a safe sweep artefact reset utility

**What changed**
- Created `docs/ops/PROJECT_MEMORY.md` (this file)
- Created `scripts/update_project_memory.py` — stdlib-only helper to prepend entries to both log files
- Created `.githooks/pre-commit` — blocks commits that change code without updating logs
- Created `scripts/install_githooks.sh` — configures `core.hooksPath`
- Created `.github/workflows/log_guard.yml` — CI guard with same enforcement
- Created `engine/scripts/reset_sweep_artefacts.py` — safe archive/delete utility for sweep artefacts
- Created `engine/docs/ops/RESET_SWEEP_ARTEFACTS.md` — reset procedure documentation

**Verification**
- Tests: `cd engine && python3 -m pytest tests/ -v`
- Results: 819 passed, 0 failed

**Next steps**
- Install hooks: `bash scripts/install_githooks.sh`
- Run next Grand Sweep from clean slate: `pnpm reset:sweeps && python3 engine/scripts/run_grand_sweep.py`

---

## 2026-02-14T21:00:00Z — PROMPT 072: Tuning Pipeline

**Goal**
- Build complete Sweep -> Tune Variants -> Walk-Forward -> Score -> Portfolio pipeline

**What changed**
- Created `engine/solat_engine/data/ohlcv_validator.py` — OHLCV data quality checks
- Created `engine/solat_engine/optimization/search_space.py` — per-bot Optuna search spaces + param conversion
- Created `engine/solat_engine/optimization/scoring.py` — hard gates + weighted 0-100 scorer
- Created `engine/solat_engine/optimization/portfolio_builder.py` — diversified portfolio builder with currency/bot/TF caps
- Created `engine/solat_engine/optimization/tuner.py` — 2-stage Optuna param tuner
- Created `engine/scripts/run_tuning.py` — tuning CLI (--smoke, --bot/--symbol/--timeframe, --sweep-results)
- Created `engine/scripts/build_portfolio.py` — portfolio builder CLI with --apply-allowlist
- Created `engine/docs/ops/TUNING_PIPELINE_V1.md` — full pipeline documentation
- Modified `engine/solat_engine/backtest/models.py` — params_override on BacktestRequest + extended MetricsSummary
- Modified `engine/solat_engine/backtest/engine.py` — threads params through strategy factory (lazy import)
- Modified `engine/solat_engine/backtest/parallel_sweep.py` — 13th arg element for params passthrough
- Modified `engine/solat_engine/backtest/metrics.py` — computes trades_per_day, equity_peak, best/worst 5
- Modified `engine/solat_engine/optimization/models.py` — AllowlistEntry extended with variant_id, score, evidence
- Created `engine/tests/test_tuning_pipeline.py` — 70 tests across 9 test classes

**Verification**
- Tests: `cd engine && python3 -m pytest tests/ -v`
- Results: 819 passed (749 existing + 70 new), 0 failed

**Decisions / Rationale**
- Lazy import of `dict_to_params` in engine.py to avoid circular import chain
- Scoring threshold `< 2.0` for decimal/percentage detection (handles 100% returns correctly)
- Tuner uses direct BacktestEngineV1 calls (not async WalkForwardEngine) to avoid complexity

**Next steps**
- Run smoke tuning: `python3 scripts/run_tuning.py --smoke`
- Run full Grand Sweep + tune + portfolio build

---

## 2026-02-13T00:00:00Z — Phase 070 Go-Live Hardening (A-D, G)

**Goal**
- Harden engine for live trading: A-F metrics output, chaos tests, risk audit

**What changed**
- Phase 070-A: Extended MetricsSummary with 50+ A-F category fields
- Phase 070-B: Chaos testing framework (tier1-tier4 tests)
- Phase 070-C: Risk engine audit and safety guard improvements
- Phase 070-D: Emergency procedures and kill switch persistence
- Phase 070-E: Walk-forward validation (OOS Sharpe for CloudTwist = 7.87)
- Phase 070-G: Risk audit complete (26 risk tests passing)

**Verification**
- Tests: `cd engine && python3 -m pytest tests/ -v`
- Results: 749 passed, 0 failed

---

// File: apps/desktop/src/lib/engineClient.ts
export class EngineClient {
  // ... other methods and properties ...

  async placeOrder(order: any): Promise<any> {
    // existing placeOrder implementation
  }

  // Back-compat shim for older UI code paths.
  // Prefer calling `quickSync(days)` directly where possible.
  async triggerQuickSync(request: { days: number }): Promise<any> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const self: any = this as any;
    if (typeof self.quickSync === "function") {
      return await self.quickSync(request.days);
    }
    return await this.requestJson("POST", "/data/quick-sync", request);
  }

  // Back-compat shim for older UI code paths.
  // If the engine exposes a kill-switch endpoint, this will toggle it on.
  async activateKillSwitch(reason: string = "manual"): Promise<any> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const self: any = this as any;
    if (typeof self.setKillSwitch === "function") {
      return await self.setKillSwitch({ enabled: true, reason });
    }
    if (typeof self.killSwitch === "function") {
      return await self.killSwitch(true, reason);
    }
    return await this.requestJson("POST", "/execution/kill-switch", { enabled: true, reason });
  }

  private async requestJson(method: string, path: string, body?: any): Promise<any> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const opts: RequestInit = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const self: any = this as any;
    if (typeof self.request === "function") return await self.request(path, opts);
    if (typeof self.fetchJson === "function") return await self.fetchJson(path, opts);

    const baseUrl: string = (self.baseUrl || "").toString();
    const res = await fetch(`${baseUrl}${path}`, opts);
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    const txt = await res.text();
    return txt ? JSON.parse(txt) : {};
  }
}

// File: apps/desktop/src/components/OrderTicket.tsx
import { useState } from "react";
// ... other imports ...

function OrderTicket() {
  // ... other state and hooks ...

  // Removed: const [riskPct, setRiskPct] = useState<number | "">("");

  // ... rest of component ...
}

// File: apps/desktop/src/components/StatusStrip.tsx
import React, { useState } from "react";

function StatusStrip() {
  const [isSyncing] = useState(false);
  const [syncProgress] = useState(0);

  // ... rest of component ...
}
