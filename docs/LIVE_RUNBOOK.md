# LIVE TRADING RUNBOOK

This document provides step-by-step procedures for operating SOLATv3.1 in LIVE trading mode with real money.

**CRITICAL**: LIVE trading involves real financial risk. Follow all procedures exactly. When in doubt, fail closed (do not trade).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Go-Live Checklist](#go-live-checklist)
3. [Enabling LIVE Mode](#enabling-live-mode)
4. [Monitoring](#monitoring)
5. [Incident Response](#incident-response)
6. [Rollback Procedures](#rollback-procedures)
7. [Daily Operations](#daily-operations)
8. [Emergency Contacts](#emergency-contacts)

---

## Prerequisites

### Environment Requirements

- [ ] Production-ready deployment (not development machine)
- [ ] Dedicated trading machine with stable network
- [ ] UPS or battery backup for power continuity
- [ ] Static IP or reliable DNS for broker connection
- [ ] Separate LIVE `.env` file (not shared with development)

### Configuration Requirements

All of these must be set in `.env` before LIVE trading:

```bash
# Master switch - must be explicitly enabled
LIVE_TRADING_ENABLED=true

# Second-factor token (generate a random 32+ character string)
LIVE_ENABLE_TOKEN=<your-unique-secret-token>

# Locked account ID from your broker
LIVE_ACCOUNT_ID=<your-ig-account-id>

# Risk limits (MANDATORY - no defaults for safety)
LIVE_MAX_ORDER_SIZE=0.5
MAX_DAILY_LOSS_PCT=2.0
MAX_CONCURRENT_POSITIONS=3
PER_SYMBOL_EXPOSURE_CAP=5000
MAX_TRADES_PER_HOUR=10

# Session controls
LIVE_CONFIRMATION_TTL_S=600        # 10 minutes
LIVE_PRELIVE_MAX_AGE_S=300         # 5 minutes
```

### Account Requirements

- [ ] IG LIVE account (not Demo)
- [ ] Account ID verified and matches `LIVE_ACCOUNT_ID`
- [ ] Sufficient funds for intended trading
- [ ] API access enabled on IG account
- [ ] Two-factor authentication configured

---

## Go-Live Checklist

### Before First LIVE Session

Complete this checklist before enabling LIVE trading for the first time:

#### Configuration Verification
- [ ] All environment variables set per "Configuration Requirements" above
- [ ] `LIVE_ENABLE_TOKEN` is unique and not shared
- [ ] `LIVE_ACCOUNT_ID` matches your actual IG LIVE account
- [ ] Risk limits set appropriately for your account size
- [ ] Logs configured to write to persistent storage

#### System Verification
- [ ] Engine starts without errors: `python -m solat_engine.main`
- [ ] Pre-live check passes: `GET /execution/prelive/run`
- [ ] Gate status shows correct blockers cleared
- [ ] Broker connection succeeds: `POST /execution/connect`
- [ ] Account verification shows correct account

#### Testing Verification
- [ ] All unit tests pass: `pytest`
- [ ] Demo mode tested successfully (full order cycle)
- [ ] Position reconciliation working correctly
- [ ] Kill switch tested and verified

#### Operational Verification
- [ ] Monitoring dashboards configured
- [ ] Alert thresholds set
- [ ] Emergency contacts identified
- [ ] Rollback procedure understood

---

## Enabling LIVE Mode

### Step-by-Step Procedure

#### 1. Start the Engine

```bash
cd /path/to/SOLATv3.1/engine
source .venv/bin/activate
python -m solat_engine.main
```

Verify startup logs show no errors.

#### 2. Connect to Broker

```bash
curl -X POST http://localhost:8042/execution/connect
```

Expected response:
```json
{
  "ok": true,
  "account_id": "YOUR_ACCOUNT_ID",
  "balance": 10000.00,
  "mode": "DEMO"
}
```

#### 3. Verify Gate Status

```bash
curl http://localhost:8042/execution/gates
```

Review blockers. Common blockers that must be resolved:
- "LIVE_TRADING_ENABLED is not set to true"
- "LIVE_ENABLE_TOKEN is not configured"
- "Pre-live check has never passed"
- "UI LIVE confirmation not completed"

#### 4. Run Pre-Live Check

```bash
curl -X POST http://localhost:8042/execution/prelive/run
```

All checks must pass:
```json
{
  "passed": true,
  "checks": [
    {"name": "Config validation", "passed": true},
    {"name": "Risk settings", "passed": true},
    {"name": "Broker connectivity", "passed": true},
    {"name": "Account verification", "passed": true},
    {"name": "Account lock", "passed": true},
    {"name": "Safety guard", "passed": true},
    {"name": "Kill switch", "passed": true}
  ]
}
```

#### 5. Confirm LIVE Mode (UI or API)

Using UI:
1. Open Desktop app
2. Click "Go LIVE" button
3. Complete multi-step confirmation:
   - Acknowledge warnings
   - Type: "ENABLE LIVE TRADING"
   - Paste your `LIVE_ENABLE_TOKEN`
   - Run pre-live check
   - Confirm account ID
   - Final confirmation

Using API:
```bash
curl -X POST http://localhost:8042/execution/live/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "ENABLE LIVE TRADING",
    "token": "YOUR_LIVE_ENABLE_TOKEN",
    "account_id": "YOUR_ACCOUNT_ID"
  }'
```

#### 6. Arm for LIVE Trading

```bash
curl -X POST http://localhost:8042/execution/arm \
  -H "Content-Type: application/json" \
  -d '{"confirm": true, "live_mode": true}'
```

Expected response:
```json
{
  "ok": true,
  "armed": true,
  "mode": "LIVE",
  "live": true
}
```

You are now armed for LIVE trading. **Real money is at risk.**

---

## Monitoring

### Key Metrics to Monitor

| Metric | Normal Range | Alert Threshold |
|--------|--------------|-----------------|
| Open positions | 0-3 | > MAX_CONCURRENT_POSITIONS |
| Daily P&L % | +/- 1% | Approaching MAX_DAILY_LOSS_PCT |
| Trades/hour | 0-10 | > MAX_TRADES_PER_HOUR |
| Reconciliation drift | 0 | Any drift |
| Circuit breaker | OK | Tripped |
| Kill switch | Inactive | Active |

### Monitoring Endpoints

```bash
# Overall status
curl http://localhost:8042/execution/status

# Gate status
curl http://localhost:8042/execution/gates

# Position reconciliation
curl http://localhost:8042/execution/reconcile/report

# Current positions
curl http://localhost:8042/execution/positions
```

### Log Monitoring

Watch for these log patterns:

```bash
# Critical errors (immediate action required)
grep -E "CRITICAL|ERROR|LIVE.*blocked|Circuit.*tripped|Kill.*switch" logs/solat.log

# Warning signs (investigate)
grep -E "WARNING|drift|mismatch|rejected" logs/solat.log

# LIVE confirmations (audit trail)
grep "LIVE.*confirm" logs/solat.log
```

---

## Incident Response

### Immediate Actions for Any Issue

1. **KILL SWITCH FIRST**
   ```bash
   curl -X POST http://localhost:8042/execution/kill-switch/activate \
     -H "Content-Type: application/json" \
     -d '{"reason": "incident response"}'
   ```

2. **Verify positions closed** (if close_on_kill_switch=true)
   ```bash
   curl http://localhost:8042/execution/positions
   ```

3. **Document the incident**
   - Timestamp
   - What happened
   - Actions taken
   - Current state

### Incident Categories

#### Category 1: Unexpected Orders
**Symptoms**: Orders placed that shouldn't be, wrong size, wrong symbol

**Response**:
1. Activate kill switch
2. Close problematic positions manually on IG platform
3. Revoke LIVE confirmation: `POST /execution/live/revoke`
4. Review logs for cause
5. Do not re-arm until root cause identified

#### Category 2: Connection Loss
**Symptoms**: Broker disconnected, API errors

**Response**:
1. System should auto-disarm on disconnect
2. Check broker status (IG platform, status page)
3. Wait for connectivity restoration
4. Re-verify positions via reconciliation
5. Re-arm only after successful reconcile

#### Category 3: Position Drift
**Symptoms**: Local state differs from broker positions

**Response**:
1. Activate kill switch
2. Run manual reconciliation
3. Verify actual positions on IG platform
4. Investigate cause (partial fills, manual trades)
5. Reset state if needed

#### Category 4: Runaway Losses
**Symptoms**: Daily loss approaching or exceeding limit

**Response**:
1. Kill switch should auto-activate at MAX_DAILY_LOSS_PCT
2. Verify all positions closed
3. Review what caused the losses
4. Do not resume trading same day

---

## Rollback Procedures

### Immediate Rollback (LIVE to DEMO)

```bash
# 1. Disarm
curl -X POST http://localhost:8042/execution/disarm

# 2. Revoke LIVE confirmation
curl -X POST http://localhost:8042/execution/live/revoke

# 3. Verify DEMO mode
curl http://localhost:8042/execution/gates
# Should show mode: "DEMO"
```

### Full System Rollback

If the engine is behaving unexpectedly:

```bash
# 1. Kill switch
curl -X POST http://localhost:8042/execution/kill-switch/activate

# 2. Stop the engine
# (in terminal where engine is running)
Ctrl+C

# 3. Close any remaining positions via IG platform directly

# 4. Restart in DEMO mode
LIVE_TRADING_ENABLED=false python -m solat_engine.main
```

### Data Rollback

Execution ledger files are in `data/ledger/`. If needed:

```bash
# Backup current state
cp -r data/ledger data/ledger.backup.$(date +%Y%m%d_%H%M%S)

# Clear ledger (positions will be re-synced from broker)
rm -rf data/ledger/*
```

---

## Daily Operations

### Pre-Market Checklist

- [ ] Engine running and healthy
- [ ] Broker connected
- [ ] Account balance verified
- [ ] No overnight position drift
- [ ] Risk limits still appropriate
- [ ] LIVE confirmation refreshed (if TTL expired)

### End-of-Day Procedure

1. **Review the day**
   - Total trades executed
   - P&L for the day
   - Any rejected orders or errors

2. **Optional: Disarm overnight**
   ```bash
   curl -X POST http://localhost:8042/execution/disarm
   ```

3. **Verify no open positions** (if flat overnight is policy)
   ```bash
   curl http://localhost:8042/execution/positions
   ```

4. **Log any notable events**

### Weekly Maintenance

- [ ] Review full week's trading logs
- [ ] Check for any recurring errors or warnings
- [ ] Verify reconciliation has no historical drift
- [ ] Update risk limits if needed
- [ ] Rotate LIVE_ENABLE_TOKEN if security concern

---

## Emergency Contacts

| Role | Contact | When to Call |
|------|---------|--------------|
| IG Support | Your IG contact | Broker API issues, manual trade assistance |
| System Admin | [Your name/contact] | Engine issues, deployment problems |

---

## Appendix: Quick Reference

### Essential Commands

```bash
# Status
curl http://localhost:8042/execution/status
curl http://localhost:8042/execution/gates

# Go LIVE
curl -X POST http://localhost:8042/execution/prelive/run
curl -X POST http://localhost:8042/execution/live/confirm -d '...'
curl -X POST http://localhost:8042/execution/arm -d '{"confirm":true,"live_mode":true}'

# Emergency Stop
curl -X POST http://localhost:8042/execution/kill-switch/activate -d '{"reason":"emergency"}'
curl -X POST http://localhost:8042/execution/live/revoke

# Position Management
curl http://localhost:8042/execution/positions
curl http://localhost:8042/execution/reconcile/report
```

### Environment Variable Reference

| Variable | Required for LIVE | Default | Description |
|----------|-------------------|---------|-------------|
| LIVE_TRADING_ENABLED | Yes | false | Master switch |
| LIVE_ENABLE_TOKEN | Yes | None | Second factor token |
| LIVE_ACCOUNT_ID | Yes | None | Locked broker account |
| LIVE_MAX_ORDER_SIZE | Yes | None | Max order size |
| LIVE_CONFIRMATION_TTL_S | No | 600 | UI confirmation TTL |
| LIVE_PRELIVE_MAX_AGE_S | No | 300 | Prelive check max age |
| MAX_DAILY_LOSS_PCT | Yes | 5.0 | Daily loss limit % |
| MAX_CONCURRENT_POSITIONS | Yes | 5 | Max open positions |
| PER_SYMBOL_EXPOSURE_CAP | Yes | 10000 | Per-symbol exposure |
| MAX_TRADES_PER_HOUR | Yes | 20 | Rate limit |

---

**Document Version**: 1.0
**Last Updated**: 2026-02-01
**Applies To**: SOLATv3.1 PROMPT 010
