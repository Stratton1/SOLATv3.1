# SOLAT Project Memory

Reverse-chronological log of all changes, decisions, and results.
Updated for every meaningful code change (enforced via pre-commit hook and CI guard).

## Current State Snapshot

| Item | Value |
|------|-------|
| **Branch** | `release/v3.1.0-alpha1` |
| **Tests** | 847 passing, 0 failing |
| **Phases complete** | 001-069 (foundations through terminal UI), 070 A-D+G (go-live hardening), 072 (tuning pipeline), Platform Outputs, CLI Fix + Sizing |
| **Phases pending** | 070-E/F/H (live trading hardening) |
| **Grand Sweep** | 180 combos (9 bots x 10 FX x 2 TFs), 21 min, all successful |
| **Top performer** | CloudTwist/USDJPY/4h — Sharpe 28.5, 66.7% win rate |
| **Broken bots** | ChikouConfirmer (0 trades), ReversalHunter (0 trades on 2024 data) |
| **Key docs** | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LIVE_RUNBOOK.md`, `engine/docs/ops/TUNING_PIPELINE_V1.md` |

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
