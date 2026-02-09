# SOLAT v3.1 - LIVE READINESS ROADMAP

**Generated:** 2026-02-05
**Status:** Preparing for LIVE trading with IG broker
**Historical Data:** 37 instruments, 1.5GB (2020-2025)

---

## 📊 CURRENT STATE

| Component | Status | Notes |
|-----------|--------|-------|
| Historical Data | ✅ Complete | 37 instruments from histdata.com |
| IG LIVE Login | ✅ Working | Account WVK88, Spread bet |
| Elite 8 Bots | ✅ Reviewed | 8 Ichimoku strategies ready |
| Backtest Engine | ⚠️ Bug Fixed | `combined_metrics` fix applied |
| Test Suite | ❌ Broken | 43 errors, 14 failures (DI refactor) |
| Walk-Forward | ⚠️ Bug Fixed | Ready for validation |
| Paper Trading | ❓ Untested | Needs validation |
| Risk Controls | ❓ Unknown | Needs audit |

---

## PHASE 1: FIX TEST SUITE 🔧
**Priority:** HIGH | **Effort:** 2-3 hours

### Tasks:
- [ ] 1.1 Create test fixture helper module with `app.dependency_overrides` pattern
- [ ] 1.2 Migrate `test_ig_endpoints.py` to new DI pattern
- [ ] 1.3 Migrate `test_execution_*.py` to new DI pattern
- [ ] 1.4 Migrate `test_market_data_*.py` to new DI pattern
- [ ] 1.5 Migrate `test_catalog.py` to new DI pattern
- [ ] 1.6 Run full test suite: `pytest --tb=short`
- [ ] 1.7 Verify all tests pass

### Files to Update:
```
tests/
├── conftest.py          # Add shared fixtures
├── test_ig_endpoints.py
├── test_ig_client.py
├── test_catalog.py
├── test_data_endpoints.py  # ✅ Already fixed
└── ...
```

---

## PHASE 2: COMPLETE IG LIVE EPIC MAPPING 🗺️
**Priority:** HIGH | **Effort:** 1-2 hours

### Tasks:
- [ ] 2.1 Document all LIVE vs DEMO epic differences
- [ ] 2.2 Add remaining `live_epic` values to seed.py (currently only 3 pairs done)
- [ ] 2.3 Update catalog bootstrap to use `live_epic` when `IG_ACC_TYPE=LIVE`
- [ ] 2.4 Test catalog bootstrap with LIVE account
- [ ] 2.5 Verify all 10 forex pairs have correct LIVE epics

### Known Epic Patterns:
| Symbol | DEMO Epic | LIVE Epic |
|--------|-----------|-----------|
| EURUSD | CS.D.EURUSD.MINI.IP | CS.D.EURUSD.TODAY.IP |
| GBPUSD | CS.D.GBPUSD.MINI.IP | CS.D.GBPUSD.TODAY.IP |
| USDJPY | CS.D.USDJPY.MINI.IP | CS.D.USDJPY.TODAY.IP |
| ... | ... | ... |

---

## PHASE 3: VALIDATE HISTORICAL DATA QUALITY 📈
**Priority:** MEDIUM | **Effort:** 30 min

### Tasks:
- [ ] 3.1 Run data quality checker: `python scripts/check_data_quality.py --timeframe 1h`
- [ ] 3.2 Review any OHLC validation errors
- [ ] 3.3 Check for excessive gaps in major pairs
- [ ] 3.4 Verify date ranges are consistent (2020-2025)
- [ ] 3.5 Spot-check 3 random instruments manually

### Expected Output:
- 37/37 instruments should pass quality checks
- ~50M+ total bars across all timeframes
- No invalid OHLC values

---

## PHASE 4: RUN FULL BACKTEST SUITE 🧪
**Priority:** HIGH | **Effort:** 1-2 hours

### Tasks:
- [ ] 4.1 Start engine: `uvicorn solat_engine.main:app --port 8765`
- [ ] 4.2 Run single bot backtest on EURUSD (sanity check)
- [ ] 4.3 Run all 8 Elite bots on EURUSD 1h (2023-2024)
- [ ] 4.4 Run Grand Sweep: All bots × Top 5 pairs × 1h timeframe
- [ ] 4.5 Review top performers (Sharpe > 1.5, Win Rate > 50%)
- [ ] 4.6 Identify best 2-3 bot/symbol combinations for LIVE

### API Calls:
```bash
# Single backtest
curl -X POST http://127.0.0.1:8765/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["EURUSD"],
    "timeframe": "1h",
    "start": "2023-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z",
    "bots": ["TKCrossSniper", "MomentumRider"],
    "initial_cash": 10000
  }'

# Grand Sweep
curl -X POST http://127.0.0.1:8765/backtest/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "bots": ["TKCrossSniper", "KumoBreaker", "MomentumRider", "TrendSurfer"],
    "symbols": ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "AUDUSD"],
    "timeframes": ["1h"],
    "start": "2023-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z"
  }'
```

---

## PHASE 5: WALK-FORWARD OPTIMIZATION 🔄
**Priority:** MEDIUM | **Effort:** 2-3 hours

### Tasks:
- [ ] 5.1 Verify walk-forward bug fix works (`combined_metrics`)
- [ ] 5.2 Configure walk-forward parameters:
  - In-sample: 6 months
  - Out-of-sample: 2 months
  - Windows: 4-6 rolling periods
- [ ] 5.3 Run walk-forward on top 3 bot/symbol combinations
- [ ] 5.4 Analyze out-of-sample performance degradation
- [ ] 5.5 Select final bot/symbol/params for LIVE

### Acceptance Criteria:
- Out-of-sample Sharpe should be >60% of in-sample Sharpe
- Win rate should remain >45% out-of-sample
- Max drawdown should not exceed 2x in-sample

---

## PHASE 6: PAPER TRADING VALIDATION 📝
**Priority:** HIGH | **Effort:** 1-2 days

### Tasks:
- [ ] 6.1 Configure engine for PAPER mode with LIVE data feed
- [ ] 6.2 Run selected bot for 24-48 hours
- [ ] 6.3 Monitor via WebSocket events
- [ ] 6.4 Verify order generation matches backtest signals
- [ ] 6.5 Check for any API errors or connectivity issues
- [ ] 6.6 Review paper trades against backtest expectations

### Monitoring:
```bash
# Watch WebSocket events
websocat ws://127.0.0.1:8765/ws

# Check execution status
curl http://127.0.0.1:8765/execution/status
```

---

## PHASE 7: RISK CONTROLS & KILL SWITCH ⚠️
**Priority:** CRITICAL | **Effort:** 1-2 hours

### Tasks:
- [ ] 7.1 Audit kill switch implementation
- [ ] 7.2 Configure daily loss limit (e.g., 2% of account)
- [ ] 7.3 Configure max position size
- [ ] 7.4 Configure max concurrent positions
- [ ] 7.5 Test kill switch activation manually
- [ ] 7.6 Verify kill switch blocks new orders
- [ ] 7.7 Document kill switch reset procedure

### Risk Parameters to Set:
```python
risk_config = RiskConfig(
    sizing_method=SizingMethod.RISK_PER_TRADE,
    risk_per_trade_pct=0.5,  # 0.5% per trade
    max_open_positions=3,
    max_exposure_per_symbol=10000,  # £10k max per symbol
    max_total_exposure=30000,  # £30k total
)
```

### Kill Switch Triggers:
- Daily loss > 2% of account
- Single trade loss > 1% of account
- API connection loss > 5 minutes
- Unusual spread detected (>3x normal)

---

## PHASE 8: GO-LIVE CHECKLIST ✅
**Priority:** CRITICAL | **Effort:** 1 hour

### Pre-Launch:
- [ ] 8.1 All tests passing
- [ ] 8.2 Backtest results reviewed and documented
- [ ] 8.3 Walk-forward validation complete
- [ ] 8.4 Paper trading successful (24h minimum)
- [ ] 8.5 Risk parameters configured
- [ ] 8.6 Kill switch tested and working
- [ ] 8.7 IG LIVE credentials verified
- [ ] 8.8 Starting capital decided (recommend: £1,000-5,000 initial)

### Launch Day:
- [ ] 8.9 Set `SOLAT_MODE=LIVE` in .env
- [ ] 8.10 Start with MINIMUM position sizes (0.1 lots)
- [ ] 8.11 Monitor first 3 trades closely
- [ ] 8.12 Keep kill switch easily accessible
- [ ] 8.13 Document any issues immediately

### Post-Launch (Week 1):
- [ ] 8.14 Daily performance review
- [ ] 8.15 Compare LIVE vs backtest metrics
- [ ] 8.16 Adjust position sizes if stable
- [ ] 8.17 Weekly report generation

---

## 📅 SUGGESTED TIMELINE

| Day | Phase | Focus |
|-----|-------|-------|
| 1 | 1, 2 | Fix tests, Complete IG epics |
| 2 | 3, 4 | Data quality, Run backtests |
| 3 | 5 | Walk-forward optimization |
| 4-5 | 6 | Paper trading (48h) |
| 6 | 7, 8 | Risk controls, Final checklist |
| 7 | GO LIVE | Start with minimum sizes |

---

## 🚨 CRITICAL REMINDERS

1. **NEVER skip paper trading** - Even 24h reveals issues
2. **Start with minimum position sizes** - Scale up after 1 week
3. **Keep kill switch tested** - Test it monthly
4. **Monitor daily** - At least first 2 weeks
5. **Document everything** - Helps debug issues later

---

## 📞 EMERGENCY PROCEDURES

### If things go wrong:
1. **Activate kill switch**: `curl -X POST http://127.0.0.1:8765/execution/kill-switch`
2. **Check IG platform directly** - Manual close if needed
3. **Stop engine**: `Ctrl+C` or kill process
4. **Review logs**: `tail -f engine/logs/solat.log`

### IG Support:
- UK: 0800 409 6789
- International: +44 20 7896 0011
- Platform: https://www.ig.com/uk

---

*Generated by SOLAT v3.1 - Automated Trading System*
