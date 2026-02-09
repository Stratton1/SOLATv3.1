# GO-LIVE CHECKLIST: DEMO VALIDATION WORKFLOW

Step-by-step checklist to validate SOLATv3.1 is ready for first supervised LIVE trade.

**Complete EVERY step in order. Do not skip. When in doubt, STOP.**

---

## Quick Reference

| Step | What | Command/Action | Expected |
|------|------|----------------|----------|
| 1 | Engine health | `curl localhost:8765/health` | `status: healthy` |
| 2 | IG connectivity | Test IG Login button | `ok: true` |
| 3 | Data available | Settings → Data section | Shows bars count > 0 |
| 4 | Chart loads | Terminal → select symbol | Candlestick chart displays |
| 5 | Backtest runs | Backtests → Run sweep | Completes with results |
| 6 | DEMO order | Manual paper trade | Order confirmed |
| 7 | Gates check | Settings → Execution Safety | Blockers listed |

---

## Phase 1: Environment Verification

### 1.1 Engine Startup

```bash
cd /path/to/SOLATv3.1/engine
source .venv/bin/activate
python -m solat_engine.main
```

- [ ] Engine starts without errors
- [ ] Logs show "Starting SOLAT Engine v3.x"
- [ ] Port 8765 is accessible

### 1.2 Health Check

```bash
curl http://localhost:8765/health
```

Expected:
```json
{
  "status": "healthy",
  "version": "3.1.x",
  "uptime_seconds": X
}
```

- [ ] `status` is `"healthy"` or `"ok"`
- [ ] Version matches expected release

### 1.3 Desktop App Launch

```bash
cd /path/to/SOLATv3.1/apps/desktop
npm run tauri dev
```

- [ ] App window opens without crash
- [ ] Header shows connection status (green dot)
- [ ] No white screen on any tab

---

## Phase 2: IG Connectivity

### 2.1 Verify Credentials Configured

In Settings screen:
- [ ] "IG Configured" shows "Yes"

If No:
1. Set environment variables in `.env`:
   ```
   IG_API_KEY=your_api_key
   IG_USERNAME=your_username
   IG_PASSWORD=your_password
   ```
2. Restart engine

### 2.2 Test IG Login

1. Click **Test IG Login** button
2. Wait for result

- [ ] Result shows `ok: true`
- [ ] Account ID displayed
- [ ] Mode shows `DEMO` (for first validation)

### 2.3 Market Data Subscription

In Terminal screen:
1. Select a symbol (e.g., EURUSD)
2. Click "Subscribe" or wait for auto-subscribe

- [ ] Bid/Ask prices appear
- [ ] Prices update periodically
- [ ] No "Connection lost" errors

---

## Phase 3: Historical Data

### 3.1 Check Data Summary

In Settings → Historical Data section:

- [ ] "Symbols Stored" > 0
- [ ] "Total Bars" > 0

If no data:
1. Configure sync days (default: 30)
2. Click **Quick Sync (All Symbols)**
3. Wait for sync to complete

### 3.2 Verify Data for Key Symbols

Check these symbols have data:
- [ ] EURUSD - 1m bars
- [ ] GBPUSD - 1m bars
- [ ] USDJPY - 1m bars

### 3.3 Chart Display Test

In Terminal:
1. Select EURUSD
2. Select 1h timeframe

- [ ] Candlestick chart renders
- [ ] Chart has recent candles (not blank)
- [ ] Ichimoku cloud overlays work (if enabled)

---

## Phase 4: Backtest Validation

### 4.1 Single Backtest Run

In Backtests screen:
1. Select 1 symbol (EURUSD)
2. Select 1 bot (e.g., ichimoku_cloud_basic)
3. Select timeframe (1h)
4. Click **Run Backtest**

- [ ] Progress bar shows completion
- [ ] Results display (even if 0 trades)
- [ ] No error messages

### 4.2 Multi-Symbol Backtest

1. Select 3+ symbols
2. Select all 8 Elite bots
3. Select 1h timeframe
4. Run backtest

- [ ] Completes within reasonable time
- [ ] Results table populates
- [ ] Can sort by Sharpe/win rate

### 4.3 Grand Sweep Test (Optional)

Run full 8 bots × 28 symbols × 5 timeframes:

- [ ] Starts successfully
- [ ] Progress updates via WebSocket
- [ ] Completes (may take 10-30 minutes)
- [ ] Results stored and viewable

---

## Phase 5: Execution Safety Gates

### 5.1 Gate Status Review

In Settings → Execution Safety:

- [ ] "LIVE Allowed" shows status (usually "No" initially)
- [ ] "Current Mode" shows "DEMO"
- [ ] Blockers list is visible

### 5.2 Expected Blockers (Pre-LIVE)

These blockers are NORMAL before going LIVE:
- [ ] "LIVE_TRADING_ENABLED is not set to true" ✓
- [ ] "Pre-live check has never passed" ✓
- [ ] "UI LIVE confirmation not completed" ✓

### 5.3 DEMO Mode Execution Test

**THIS IS PAPER TRADING ONLY - NO REAL MONEY**

1. Ensure mode is DEMO
2. In Terminal, arm execution (if arm button exists)
3. Wait for a strategy signal OR manually trigger

- [ ] Order intent logged
- [ ] Paper order "submitted"
- [ ] Position appears in positions list
- [ ] Paper P&L updates

### 5.4 Kill Switch Test

1. Activate kill switch
2. Verify all positions closed
3. Verify system disarmed

- [ ] Kill switch activates immediately
- [ ] Positions closed (paper)
- [ ] System refuses new orders while killed

---

## Phase 6: Pre-LIVE Checklist

**Only proceed if ALL above phases complete successfully.**

### 6.1 Documentation Ready

- [ ] `.env` has all LIVE settings prepared (but LIVE_TRADING_ENABLED=false)
- [ ] LIVE_ENABLE_TOKEN generated (32+ char random string)
- [ ] LIVE_ACCOUNT_ID ready from IG

### 6.2 Risk Limits Decided

| Setting | Your Value | Reasoning |
|---------|-----------|-----------|
| LIVE_MAX_ORDER_SIZE | _____ | |
| MAX_DAILY_LOSS_PCT | _____ | |
| MAX_CONCURRENT_POSITIONS | _____ | |
| PER_SYMBOL_EXPOSURE_CAP | _____ | |
| MAX_TRADES_PER_HOUR | _____ | |

### 6.3 Human Oversight Plan

- [ ] Will monitor first LIVE session personally
- [ ] Know how to access IG platform directly
- [ ] Can execute emergency close via IG if needed
- [ ] Have read LIVE_RUNBOOK.md completely

### 6.4 Rollback Plan Understood

If anything goes wrong:
1. Kill switch: `POST /execution/kill-switch/activate`
2. Revoke LIVE: `POST /execution/live/revoke`
3. Stop engine if needed

---

## Sign-Off

**I confirm that:**

- [ ] All Phase 1-6 steps completed successfully
- [ ] I understand LIVE trading involves real money and real risk
- [ ] I have a monitoring plan for the first LIVE session
- [ ] I know how to emergency stop the system

**Operator**: ________________________

**Date**: ________________________

---

## Troubleshooting Quick Reference

### "No data for SYMBOL"
→ Run Quick Sync in Settings
→ Check IG credentials configured
→ Verify symbol exists in catalogue

### Settings screen white/crash
→ Check browser console for errors
→ Restart desktop app
→ Verify engine is running

### Backtest shows 0 trades
→ Normal if strategy didn't trigger in date range
→ Try longer date range
→ Try different symbols/timeframes

### IG Login fails
→ Verify credentials in .env
→ Check IG API status
→ Restart engine after .env changes

### WebSocket disconnects
→ Check engine is running
→ Check port 8765 accessible
→ Restart desktop app

---

**Document Version**: 1.0
**For**: SOLATv3.1
**Last Updated**: 2026-02-04
