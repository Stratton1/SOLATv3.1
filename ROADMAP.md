# SOLAT Project Roadmap

**Version:** 3.1.0
**Status:** Finalizing for LIVE trading.

This document outlines the development roadmap for SOLAT, from the immediate tasks required to go live with v3.1 to future feature enhancements and architectural goals.

---

## 🎯 Current Milestone: v3.1 Go-Live

**Objective:** To safely and successfully deploy the SOLAT v3.1 trading engine to a live environment with the IG broker. This milestone is focused on testing, validation, and risk management.

### Recent Progress (Feb 12, 2026)
- ✅ **Mission Control Overhaul:** Modular status page with real-time infrastructure (CPU/Mem/Disk) and broker metrics (Latency/Rate-limits).
- ✅ **Risk Observability:** Integrated Safety Gates monitor to clearly visualize blockers for LIVE execution.
- ✅ **Diagnostic Pulse:** Real-time in-memory log tail endpoint for high-priority event tracking.

### PHASE 1: FIX TEST SUITE (Infrastructure Hardening) ✅
**Priority:** CRITICAL | **Status:** Completed (Feb 12, 2026)

*Tasks:*
- [x] 1.1 Create test fixture helper module with `app.dependency_overrides` pattern.
- [x] 1.2 Migrate `test_ig_endpoints.py` to new DI pattern.
- [x] 1.3 Migrate `test_execution_*.py` to new DI pattern.
- [x] 1.4 Migrate `test_market_data_*.py` to new DI pattern.
- [x] 1.5 Migrate `test_catalog.py` to new DI pattern.
- [x] 1.6 Run full test suite: `pytest --tb=short`.
- [x] 1.7 Achieve 100% pass rate (710 tests verified).

### PHASE 2: COMPLETE IG LIVE EPIC MAPPING 🗺️
**Priority:** HIGH | **Status:** Substantially Complete (Feb 12, 2026)

*Tasks:*
- [x] 2.1 Document all LIVE vs DEMO epic differences (See `docs/IG_EPIC_MAPPING.md`).
- [x] 2.2 Add remaining `live_epic` values to `seed.py` (Forex, Indices, Commodities mapped).
- [x] 2.3 Update catalog bootstrap to use `live_epic` when `SOLAT_MODE=LIVE`.
- [ ] 2.4 Test catalog bootstrap with real LIVE account (Requires credentials).
- [ ] 2.5 Verify all 10 forex pairs have correct LIVE epics on-platform.

### PHASE 3: VALIDATE HISTORICAL DATA QUALITY ✅
**Priority:** MEDIUM | **Status:** Completed (Feb 12, 2026)

*Tasks:*
- [x] 3.1 Run data quality checker: `python scripts/check_data_quality.py --timeframe 1h`.
- [x] 3.2 Review any OHLC validation errors (Verified Index gaps are session-based).
- [x] 3.3 Check for excessive gaps in major pairs (Integrity confirmed).
- [x] 3.4 Verify date ranges are consistent (2020-2025).
- [x] 3.5 Spot-check 3 random instruments manually.

### PHASE 4: RUN FULL BACKTEST SUITE ✅
**Priority:** HIGH | **Status:** Completed (Feb 12, 2026)

*Tasks:*
- [x] 4.1 Start engine: `pnpm dev:engine`.
- [x] 4.2 Run single bot backtest on EURUSD (Sanity check passed).
- [x] 4.3 Run all 8 Elite bots on EURUSD 1h (2023-2024).
- [x] 4.4 Run Grand Sweep: All bots × Top 10 Live pairs × 1h/4h timeframe.
- [x] 4.5 Review top performers (80+ combos ranked).
- [x] 4.6 Identify best 3 bot/symbol combinations for WFO.

### PHASE 5: WALK-FORWARD OPTIMIZATION ✅
**Priority:** MEDIUM | **Status:** Completed (Feb 12, 2026)

*Tasks:*
- [x] 5.1 Verify walk-forward bug fix works (Regression test passed).
- [x] 5.2 Configure and run walk-forward on top 3 bot/symbol combinations.
- [x] 5.3 Analyze out-of-sample performance degradation (EURJPY KijunBouncer identified as most consistent).
- [x] 5.4 Select final bot/symbol/params for LIVE (`KijunBouncer/EURJPY/1h`).

### PHASE 6: PAPER TRADING VALIDATION 📝
**Priority:** HIGH | **Status:** Next Step

*Tasks:*
- [ ] 6.1 Configure engine for PAPER mode with LIVE data feed.
- [ ] 6.2 Run selected bot for 24-48 hours.
- [ ] 6.3 Monitor via WebSocket events and logs.
- [ ] 6.4 Verify order generation matches backtest signals.
- [ ] 6.5 Check for any API errors or connectivity issues.
- [ ] 6.6 Review paper trades against backtest expectations.

### PHASE 7: RISK CONTROLS & KILL SWITCH ✅
**Priority:** CRITICAL | **Status:** Hardened & Verified (Feb 12, 2026)

*Tasks:*
- [x] 7.1 Audit kill switch implementation (Refactored for parallel liquidation).
- [x] 7.2 Configure and document all risk parameters (`MAX_DAILY_LOSS_PCT`, etc.).
- [x] 7.3 Test kill switch activation manually (Stress test passed).
- [x] 7.4 Verify kill switch blocks new orders and closes positions (Verified).
- [x] 7.5 Document kill switch reset procedure.

### PHASE 8: GO-LIVE CHECKLIST ✅
**Priority:** CRITICAL | **Status:** Not Started

*Pre-Launch Tasks:*
- [ ] 8.1 All tests passing.
- [ ] 8.2 Backtest results reviewed and documented.
- [ ] 8.3 Walk-forward validation complete.
- [ ] 8.4 Paper trading successful (48h minimum).
- [ ] 8.5 Risk parameters configured and verified.
- [ ] 8.6 Kill switch tested and working.
- [ ] 8.7 IG LIVE credentials verified.
- [ ] 8.8 Starting capital decided and funded.

---

## 🚀 Future Milestones (Post v3.1)

### v3.2 - Stability & Observability
- ✅ **Status Overhaul:** Comprehensive dashboard for system/broker health.
- [ ] **Real-time Performance Metrics:** Equity curve and daily P/L visualization.
- [ ] **Advanced Monitoring:** Sentry integration and Prometheus metrics.

### v3.3 - Broker & Strategy Expansion
- [ ] **Multi-Broker Support:** Generic broker interface.
- [ ] **Strategy SDK:** Simplified bot creation framework.

---

## 🚨 Emergency Procedures
1. **Activate kill switch**: `curl -X POST http://127.0.0.1:8765/execution/kill-switch`
2. **Check IG platform directly**: Manually close positions if necessary.
3. **Stop engine**: `Ctrl+C` or `kill <PID>`.
