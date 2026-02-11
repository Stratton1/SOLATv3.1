# Build Log

Chronological record of major implementation prompts.

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
