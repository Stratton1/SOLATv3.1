# Phase 070-H: Go-Live Checklist

**Created**: 2026-02-14
**Branch**: release/v3.1.0-alpha1

---

## Completed Phases

### 070-A: Test Suite Green
- [x] 714 tests collected
- [x] 714 passing, 0 failing, 0 skipped
- [x] Test output saved: `results/test_results_070a.txt`

### 070-B: IG Live Epic Mapping
- [x] 22/28 instruments have `live_epic` in seed data
- [x] 6 missing: NATGAS, COPPER, BTCUSD, ETHUSD, LTCUSD, XRPUSD (non-blocking)
- [x] FX: DEMO=MINI, LIVE=TODAY (verified pattern)
- [x] Indices/Commodities: same epic for DEMO and LIVE
- [x] Verification script: `engine/scripts/verify_live_epics.py`
- [ ] **PENDING**: Run `--verify-api` against LIVE account when credentials available

### 070-C: Historical Data Quality
- [x] 33/37 instruments passed quality checks
- [x] 4 with gap warnings (ASX200, DAX, FTSE100, HSI — expected for limited-hours indices)
- [x] 0 OHLC violations, 0 duplicates, 0 zero-close bars
- [x] 1,143,771 total bars across 37 instruments
- [x] Report saved: `results/data_quality_070c.txt`

### 070-D: Grand Sweep Backtests
- [x] 180 combos tested (9 bots x 10 FX pairs x 2 TFs)
- [x] 180/180 successful, 0 failed
- [x] Completed in 1284s (~21 min)
- [x] Results saved to `engine/data/sweep_results/sweep_live_20260214_025719/`

**Top 10 by Sharpe (min 10 trades)**:

| Rank | Bot | Symbol | TF | Sharpe | Win% | Trades |
|------|-----|--------|----|--------|------|--------|
| 1 | CloudTwist | USDJPY | 4h | 28.50 | 66.7% | 21 |
| 2 | KijunBouncer | AUDUSD | 4h | 23.98 | 63.6% | 22 |
| 3 | CloudTwist | EURUSD | 4h | 22.64 | 68.8% | 16 |
| 4 | KijunBouncer | USDJPY | 4h | 21.88 | 61.1% | 18 |
| 5 | ChikouKaizen | USDJPY | 4h | 20.37 | 38.0% | 50 |
| 6 | CloudTwist | AUDUSD | 4h | 19.82 | 59.1% | 22 |
| 7 | TKCrossSniper | AUDUSD | 4h | 18.31 | 57.1% | 14 |
| 8 | TKCrossSniper | USDJPY | 4h | 16.94 | 54.5% | 11 |
| 9 | TrendSurfer | USDCAD | 1h | 15.42 | 47.2% | 53 |
| 10 | CloudTwist | EURJPY | 4h | 14.82 | 54.2% | 24 |

**Key Findings**:
- 4h timeframe dramatically outperforms 1h (avg Sharpe -0.75 vs -3.60)
- CloudTwist is best bot overall (avg Sharpe 3.1 across all combos)
- USDJPY and AUDUSD are top-performing symbols
- 2 bots flagged as broken: ChikouConfirmer (0 trades on all), ReversalHunter (0 trades on all)

---

### 070-E: Walk-Forward Validation
- [x] Walk-forward on top 3 combos (12 ROLLING windows each, 180d IS / 45d OOS / 45d step)
- [x] CloudTwist/EURUSD/4h: OOS Sharpe 28.34, 70% folds profitable, consistency 0.87 — **PRIMARY**
- [x] KijunBouncer/AUDUSD/4h: OOS Sharpe 23.08, 75% folds profitable, consistency 0.32 — **SECONDARY**
- [x] CloudTwist/USDJPY/4h: OOS Sharpe 13.50, 62.5% folds profitable, consistency 0.24 — **TERTIARY**
- [x] All 3 combos APPROVED (OOS Sharpe >= 1.0)
- [x] Live trading plan updated with approved combos: `configs/live_trading_plan.json`
- [x] Report saved: `results/walk_forward_070e.txt`
- [x] Artefacts: `engine/data/artefacts/walk_forward/wf-{c7eab272,e44b3be1,3f15c92b}/`

---

## Remaining Phases

### 070-F: Paper Trading (24-48h)
- [ ] Configure PAPER mode in `.env`
- [ ] Enable autopilot with approved combos
- [ ] Monitor for 24-48 hours
- [ ] Verify signals match backtest expectations
- [ ] Document results

### 070-G: Risk Controls Audit
- [x] Risk config documented: `configs/risk_config_live.json`
- [x] Emergency procedures documented: `docs/EMERGENCY_PROCEDURES.md`
- [x] Live trading plan created with 3 approved combos: `configs/live_trading_plan.json`
- [x] Risk engine has 9 checks: size cap, dealing rules max, step rounding, min size, concurrent positions, daily loss, trade frequency, symbol exposure, SL requirement
- [x] Kill switch has: activate/reset/check_can_trade/save_state/restore_state
- [x] Kill switch lifecycle tested: activate -> persist -> restore -> block -> reset -> allow
- [x] Credential redaction verified: headers (CST, X-Security-Token, Authorization, X-IG-API-KEY), body (password, identifier, apiKey, token, secret), URLs
- [x] No credential leaks in log files (0 matches for sensitive patterns)

### 070-H: Go-Live Readiness
- [x] All test artifacts collected
- [x] Walk-forward validation complete (070-E)
- [ ] Paper trading validated (070-F)
- [ ] IG LIVE credentials tested
- [ ] Multi-gate confirmation flow tested
- [ ] Final sign-off

---

## Pre-Launch Day Commands

```bash
# 1. Start engine in LIVE mode
export SOLAT_MODE=LIVE
export LIVE_TRADING_ENABLED=true
pnpm dev:engine

# 2. Verify health
curl http://127.0.0.1:8765/health | jq .

# 3. Check blockers
curl http://127.0.0.1:8765/execution/status | jq '.blockers'

# 4. Arm execution
curl -X POST http://127.0.0.1:8765/execution/arm

# 5. Enable autopilot
curl -X POST http://127.0.0.1:8765/autopilot/enable

# 6. Keep kill switch command ready
curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate -d '{"reason":"emergency"}'
```
