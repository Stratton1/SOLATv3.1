# SOLAT Engine Security

## Overview

SOLAT Engine handles sensitive broker credentials and financial data. This document outlines security considerations and best practices.

## Credential Management

### IG Markets API Credentials

Credentials are loaded from environment variables:
- `IG_API_KEY`: API key from IG Markets
- `IG_USERNAME`: Account username
- `IG_PASSWORD`: Account password
- `IG_ACCOUNT_ID`: Trading account ID

**Never commit credentials to version control.**

### Environment Files

Use `.env` files for local development (excluded from git):
```bash
# .env (gitignored)
IG_API_KEY=your_api_key
IG_USERNAME=your_username
IG_PASSWORD=your_password
IG_ACCOUNT_ID=your_account_id
```

## API Security

### CORS

CORS is configured to allow only specified origins:
- Development: `http://localhost:*`
- Production: Configured via `ALLOWED_ORIGINS` environment variable

### Rate Limiting

IG API calls are rate-limited to comply with broker limits:
- Per-endpoint rate limiting
- Automatic retry with exponential backoff
- Request queuing

## Backtest Security

### Offline Operation

**Critical**: Backtest operations NEVER make calls to live broker APIs.

The backtest engine:
- Reads historical data from local ParquetStore
- Simulates execution via BrokerSim (no live orders)
- Writes results to local filesystem only
- Has no access to broker credentials during execution

This isolation ensures:
1. No accidental live trades during testing
2. Deterministic, reproducible results
3. Safe parallel execution

### Data Isolation

Each backtest run creates isolated artefacts:
```
backtests/{run_id}/
├── manifest.json
├── equity_curve.parquet
├── trades.parquet
├── orders.parquet
└── metrics.json
```

Run IDs are UUIDs, preventing path traversal.

## Demo vs Live Mode

The engine supports two operational modes:
- **DEMO**: Uses IG demo environment (paper trading)
- **LIVE**: Uses IG production environment (real money)

Mode is controlled via `SOLAT_MODE` environment variable.

**Always test thoroughly in DEMO mode before enabling LIVE mode.**

### IMPORTANT: v1 Live Execution Restrictions

**Phase 005 (Live Execution v1) is DEMO-ONLY.**

The execution router explicitly blocks LIVE mode:
- `ExecutionMode.LIVE` is rejected at connection time
- API returns 400 error: "Only DEMO mode is supported in v1"
- This restriction is enforced in code and cannot be bypassed via config

This ensures:
1. No accidental real-money trades during initial development
2. Thorough testing before any LIVE capability is enabled
3. Clear audit trail showing DEMO-only operation

## Execution Safety Gates (Phase 005)

### Kill Switch

Emergency halt mechanism for live execution:

**Activation Triggers**:
- Manual activation via `/execution/kill-switch/activate`
- Automatic when daily loss limit exceeded
- Network errors causing position uncertainty

**Effects**:
1. Immediately disarms trading (`armed = false`)
2. Blocks all new order submissions
3. Optionally closes all positions (`close_on_kill_switch=true`)
4. Emits WebSocket event for UI notification

**Reset**:
- Manual only via `/execution/kill-switch/reset`
- Requires deliberate action (no auto-reset)
- Logs reset event for audit trail

### Arm/Disarm Gate

Two-stage safety for order submission:

```
Connected → Disarmed → [ARM with confirm=true] → Armed → Can Submit Orders
                 ↑                                  │
                 └────── [DISARM] ──────────────────┘
```

- Must be connected to broker before arming
- Arm requires explicit `confirm: true` in request
- Kill switch prevents arming
- Disarm is immediate (no confirmation needed)

### Risk Engine Limits

Configurable safety limits enforced before every order:

| Limit | Config Key | Default | Action |
|-------|------------|---------|--------|
| Max Position Size | MAX_POSITION_SIZE | 1.0 | Cap to max |
| Max Concurrent | MAX_CONCURRENT_POSITIONS | 5 | Reject |
| Daily Loss | MAX_DAILY_LOSS_PCT | 5% | Reject + kill switch |
| Trade Rate | MAX_TRADES_PER_HOUR | 20 | Reject |
| Symbol Exposure | PER_SYMBOL_EXPOSURE_CAP | 10000 | Reject |
| Stop Loss Required | REQUIRE_SL | false | Reject if missing |

### Position Reconciliation

Broker positions are the source of truth:
- Periodic sync (configurable interval, default 5s)
- Detects drift: positions added/removed/changed externally
- Emits warning events for unexpected changes
- Local store always updated to match broker

### Execution Ledger (Audit Trail)

All execution activity is logged:
- Append-only JSONL file per day
- Records: intents, submissions, fills, rejections
- Includes timestamps, intent IDs, deal references
- No deletion or modification of records
- Periodic compaction to Parquet for analysis

### Token Security

Session tokens from IG API:
- Never logged (even in DEBUG mode)
- Stored in memory only (not persisted)
- Cleared on disconnect
- Rate limiting prevents token exhaustion

## Data Protection

### Parquet Files

Historical bar data is stored locally in Parquet format:
- No encryption at rest (relies on filesystem permissions)
- No PII stored in bar data
- Consider disk encryption for sensitive deployments

### SQLite Catalogue

Metadata catalogue contains:
- Symbol/timeframe tracking
- Gap information
- Quality scores

No credentials or PII stored in catalogue.

## Logging

Logs may contain:
- Timestamps and symbols traded
- Order details (prices, sizes)
- Error messages

Logs do NOT contain:
- API credentials
- Account passwords
- Full API responses with sensitive data

## Recommendations

1. **Use environment variables** for all credentials
2. **Never commit** `.env` files or credentials
3. **Run backtests offline** to prevent accidental trades
4. **Use DEMO mode** for development and testing
5. **Review logs** before sharing to ensure no sensitive data
6. **Rotate credentials** regularly
7. **Monitor API usage** for unusual activity
