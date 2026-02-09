# SOLAT v3.1 - Quality Criteria & Exit Conditions

## Ralph Loop Exit Conditions

The loop terminates when ALL criteria in a phase are met. Each phase must complete before proceeding to the next.

---

## Phase 1: Test Suite ✅

### Exit Criteria
- [ ] `pytest --tb=short` returns exit code 0
- [ ] All 43 previous errors resolved
- [ ] All 14 previous failures resolved
- [ ] No new regressions introduced
- [ ] Test coverage maintained (no decrease)

### Validation Commands
```bash
cd /path/to/engine
pytest --tb=short 2>&1 | tail -20
pytest --cov=solat_engine --cov-report=term-missing 2>&1 | grep "TOTAL"
```

### Quality Signals
- ✅ PASS: "passed" with no "failed" or "error"
- ⚠️ RETRY: Any test failures → fix and re-run
- ❌ FAIL: New modules break that weren't tested before

---

## Phase 2: IG LIVE Epic Mapping ✅

### Exit Criteria
- [ ] All 10 forex pairs have `live_epic` values in seed.py
- [ ] All 8 indices have `live_epic` values (if available)
- [ ] All 6 commodities have `live_epic` values (if available)
- [ ] Catalog bootstrap selects correct epic based on `IG_ACC_TYPE`
- [ ] `GET /catalog/instruments` returns valid epics for LIVE mode

### Validation Commands
```bash
# Check seed.py has live_epic for all FX
grep -c "live_epic=" engine/solat_engine/catalog/seed.py

# Test catalog with LIVE mode
curl http://127.0.0.1:8765/catalog/instruments | jq '.[0:3]'
```

### Quality Signals
- ✅ PASS: All instruments return valid IG epics
- ⚠️ RETRY: Missing epics for critical pairs
- ❌ FAIL: API returns 404 for any major pair

---

## Phase 3: Data Quality ✅

### Exit Criteria
- [ ] All 37 instruments pass quality check
- [ ] No invalid OHLC values
- [ ] No zero close prices
- [ ] Gap detection passes (allowing weekends)
- [ ] Date ranges consistent (2020-2025)

### Validation Commands
```bash
cd engine
python scripts/check_data_quality.py --timeframe 1h 2>&1 | tail -50
```

### Quality Signals
- ✅ PASS: "37/37 instruments passed quality checks"
- ⚠️ RETRY: Minor issues (< 5 instruments with warnings)
- ❌ FAIL: Major data corruption or missing data

---

## Phase 4: Backtest Suite ✅

### Exit Criteria
- [ ] Single bot backtest completes without error
- [ ] All 8 Elite bots run successfully
- [ ] Grand Sweep completes for top 5 pairs
- [ ] At least 2 bots show Sharpe > 1.0
- [ ] No unexpected exceptions in logs

### Validation Commands
```bash
# Single backtest
curl -X POST http://127.0.0.1:8765/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbols":["EURUSD"],"timeframe":"1h","start":"2023-01-01T00:00:00Z","end":"2024-01-01T00:00:00Z","bots":["TKCrossSniper"],"initial_cash":10000}'

# Check results
curl "http://127.0.0.1:8765/backtest/results?run_id=<ID>"
```

### Quality Signals
- ✅ PASS: Backtests complete with positive metrics
- ⚠️ RETRY: API errors or timeouts → check logs
- ❌ FAIL: Engine crashes or data not found

---

## Phase 5: Walk-Forward Optimization ✅

### Exit Criteria
- [ ] Walk-forward runs without `AttributeError`
- [ ] Out-of-sample Sharpe > 60% of in-sample
- [ ] At least 1 bot/symbol combination passes
- [ ] Results saved to artefacts directory

### Validation Commands
```bash
curl -X POST http://127.0.0.1:8765/optimization/walk-forward \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","bot":"TKCrossSniper","timeframe":"1h","in_sample_months":6,"out_sample_months":2,"windows":4}'
```

### Quality Signals
- ✅ PASS: OOS performance degrades gracefully
- ⚠️ RETRY: Extreme OOS degradation (< 30% of IS)
- ❌ FAIL: Exceptions or missing metrics

---

## Phase 6: Paper Trading ✅

### Exit Criteria
- [ ] Engine runs for 24h without crash
- [ ] WebSocket events streaming correctly
- [ ] Orders generated match expected signals
- [ ] No API authentication errors
- [ ] Positions tracked correctly

### Validation Commands
```bash
# Start engine
uvicorn solat_engine.main:app --port 8765 &

# Monitor WebSocket
websocat ws://127.0.0.1:8765/ws | head -100

# Check execution status
curl http://127.0.0.1:8765/execution/status
```

### Quality Signals
- ✅ PASS: 24h stable operation with correct signals
- ⚠️ RETRY: Intermittent disconnections (< 3)
- ❌ FAIL: Crashes or order generation failures

---

## Phase 7: Risk Controls ✅

### Exit Criteria
- [ ] Kill switch activates on daily loss limit
- [ ] Kill switch blocks new orders when active
- [ ] Kill switch can be reset manually
- [ ] Max position size enforced
- [ ] Max concurrent positions enforced

### Validation Commands
```bash
# Activate kill switch
curl -X POST http://127.0.0.1:8765/execution/kill-switch

# Verify orders blocked
curl -X POST http://127.0.0.1:8765/execution/place-order \
  -d '{"symbol":"EURUSD","side":"BUY","size":1}'
# Should return 403 or similar

# Reset kill switch
curl -X DELETE http://127.0.0.1:8765/execution/kill-switch
```

### Quality Signals
- ✅ PASS: All risk controls function correctly
- ⚠️ RETRY: Minor issues in enforcement
- ❌ FAIL: Kill switch doesn't block orders

---

## Phase 8: Go-Live Checklist ✅

### Exit Criteria
- [ ] All Phase 1-7 complete
- [ ] Starting capital decided
- [ ] Position sizes configured (start minimum)
- [ ] Emergency procedures documented
- [ ] First trade monitored successfully

### Final Validation
```bash
# Full system check
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/config
curl http://127.0.0.1:8765/backtest/bots
curl http://127.0.0.1:8765/execution/status
```

### Quality Signals
- ✅ PASS: All systems operational, first trade successful
- ⚠️ RETRY: Minor issues requiring attention
- ❌ FAIL: Critical system not ready

---

## Global Quality Standards

### Code Quality
- No `# type: ignore` without justification
- No `try: except: pass` (silent failures)
- All public functions have docstrings
- Pydantic models for all API I/O

### Performance
- API responses < 200ms (excluding backtest)
- WebSocket latency < 100ms
- Historical data queries < 1s for 10k bars

### Security
- No credentials in code or logs
- CORS restricted to localhost
- Kill switch always accessible

### Observability
- All errors logged with stack traces
- Key events emitted to EventBus
- WebSocket broadcasts for UI updates
