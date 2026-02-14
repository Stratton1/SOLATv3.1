# Emergency Procedures

Quick-reference for production incidents. Keep this accessible during LIVE sessions.

## 1. Kill All Trading Immediately

**When**: Unexpected behavior, market chaos, critical bug, or runaway losses.

```bash
# Activate kill switch (closes all positions)
curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate \
  -H "Content-Type: application/json" \
  -d '{"reason":"Emergency stop","close_positions":true}'

# Verify all positions closed
curl http://127.0.0.1:8765/execution/positions

# If positions remain, close manually via IG platform

# Stop engine
pkill -f solat_engine
```

## 2. Engine Crash / Hang

**When**: Engine stops responding or crashes mid-session.

1. Check IG platform directly for open positions
2. Close all SOLAT-opened positions manually on IG
3. Restart engine in DEMO mode to investigate:
   ```bash
   export SOLAT_MODE=DEMO
   pnpm dev:engine
   ```
4. Review logs: `tail -100 engine/logs/latest.log`

## 3. Runaway Losses

**When**: Daily loss exceeds 3% or a single trade moves against you unexpectedly.

1. Kill switch activates automatically at `MAX_DAILY_LOSS_PCT` (2%)
2. If not auto-triggered, activate manually (see section 1)
3. Review all trades on IG platform
4. Identify which bot/symbol caused losses
5. Disable problematic combo in allowlist
6. **Do NOT resume same day** after auto-kill-switch

## 4. IG API Failure

**When**: Connection errors, 401/403 responses, or stream disconnects.

1. Check IG system status: https://status.ig.com
2. If IG is down: wait for restoration, engine will auto-reconnect
3. If credentials expired:
   ```bash
   # Test connection
   curl -X POST http://127.0.0.1:8765/ig/login/test
   ```
4. If API key revoked: regenerate in IG portal, update `.env`

## 5. Position Drift

**When**: Local state doesn't match IG platform positions.

1. Activate kill switch (section 1)
2. Check IG platform for actual positions
3. Reconcile manually: close any positions not in local state
4. After restart, engine runs auto-reconciliation
5. Verify positions match before re-arming

## Key Commands Reference

| Action | Command |
|--------|---------|
| Health check | `curl http://127.0.0.1:8765/health` |
| Execution status | `curl http://127.0.0.1:8765/execution/status` |
| Open positions | `curl http://127.0.0.1:8765/execution/positions` |
| Kill switch ON | `curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate -d '{"reason":"emergency"}'` |
| Kill switch OFF | `curl -X POST http://127.0.0.1:8765/execution/kill-switch/reset` |
| Disarm trading | `curl -X POST http://127.0.0.1:8765/execution/disarm` |
| Autopilot OFF | `curl -X POST http://127.0.0.1:8765/autopilot/disable` |
