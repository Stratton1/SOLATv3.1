# SOLAT Project Memory

Reverse-chronological log of all changes, decisions, and results.
Updated for every meaningful code change (enforced via pre-commit hook and CI guard).

## Current State Snapshot

| Item | Value |
|------|-------|
| **Branch** | `release/v3.1.0-alpha1` |
| **Tests** | 819 passing, 0 failing |
| **Phases complete** | 001-069 (foundations through terminal UI), 070 A-D+G (go-live hardening), 072 (tuning pipeline) |
| **Phases pending** | 070-E/F/H (live trading hardening) |
| **Grand Sweep** | 180 combos (9 bots x 10 FX x 2 TFs), 21 min, all successful |
| **Top performer** | CloudTwist/USDJPY/4h — Sharpe 28.5, 66.7% win rate |
| **Broken bots** | ChikouConfirmer (0 trades), ReversalHunter (0 trades on 2024 data) |
| **Key docs** | `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LIVE_RUNBOOK.md`, `engine/docs/ops/TUNING_PIPELINE_V1.md` |

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
