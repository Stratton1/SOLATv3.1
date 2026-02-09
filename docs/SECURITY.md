# SOLAT Security Guidelines

## Critical Warnings

### Demo vs Live Trading

```
⚠️  DEMO MODE (default): Paper trading only - no real money at risk
🔴  LIVE MODE: Real money - extreme caution required
```

**Never switch to LIVE mode without:**
1. Extensive demo testing (minimum 30 days recommended)
2. Understanding all risk parameters
3. Setting appropriate position limits
4. Having a tested kill switch

### Kill Switch

SOLAT includes an emergency kill switch that:
- Closes all open positions
- Cancels all pending orders
- Disables new order submission
- Must be manually reset

**Test the kill switch regularly in demo mode.**

## Credential Management

### Never Commit Secrets

The following must **NEVER** be committed to version control:

```
# Bad - these patterns should never appear in commits:
IG_API_KEY=abc123...
IG_PASSWORD=secret...
api_key = "..."
"password": "..."
```

### Environment Variables

Store all credentials in environment variables:

```bash
# .env file (gitignored)
IG_API_KEY=your_actual_key
IG_USERNAME=your_username
IG_PASSWORD=your_password
IG_ACCOUNT_ID=your_account
```

**Use `.env.example` (committed) as a template without real values.**

### Credential Checklist

Before each commit, verify:
- [ ] `.env` is in `.gitignore`
- [ ] No hardcoded credentials in code
- [ ] No credentials in logs
- [ ] No credentials in error messages

## Network Security

### Local-Only Binding

The Python engine binds exclusively to localhost:

```python
# Correct - localhost only
host = "127.0.0.1"
port = 8765

# NEVER do this in production
# host = "0.0.0.0"  # Exposes to network
```

### TLS for Broker Communication

All communication with IG uses HTTPS:
- Demo: `https://demo-api.ig.com`
- Live: `https://api.ig.com`

**Never disable TLS verification.**

### Content Security Policy

The Tauri app enforces CSP:

```json
"csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:8765 ws://127.0.0.1:8765"
```

This prevents:
- Loading external scripts
- Connecting to unauthorized servers
- XSS attacks

## Logging and Audit

### What Gets Logged

```python
# DO log:
logger.info("Order submitted: %s %s %s", order.side, order.quantity, order.symbol)
logger.info("Position opened: %s", position.id)

# DO NOT log:
# logger.debug(f"Request: {request_with_auth_header}")
# logger.info(f"API key: {api_key}")
```

### Redaction

Use the `redact_sensitive()` function for any data that might contain secrets:

```python
from solat_engine.logging import redact_sensitive

# This automatically redacts fields containing:
# password, api_key, secret, token, authorization, etc.
safe_data = redact_sensitive(request_data)
logger.debug("Request: %s", safe_data)
```

### Audit Trail

All trades are logged with:
- Timestamp (UTC)
- Run ID
- Signal that triggered the trade
- Order details
- Fill details
- Reason codes

Audit logs are stored in:
```
data/runs/{run_id}/logs/trades.log
```

## Risk Controls

### Built-in Limits

Configure these in your `.env`:

```bash
# Maximum position size per trade
MAX_POSITION_SIZE=1.0

# Maximum concurrent positions
MAX_CONCURRENT_POSITIONS=5

# Maximum daily loss (triggers kill switch)
MAX_DAILY_LOSS_PCT=2.0

# Maximum trades per hour (rate limiting)
MAX_TRADES_PER_HOUR=10
```

### IG-Specific Limits

Be aware of IG's limits:
- API rate limits (vary by tier)
- Position size limits (per instrument)
- Guaranteed stop requirements
- Margin requirements

## Incident Response

### If Credentials Are Exposed

1. **Immediately** revoke the exposed credentials in IG settings
2. Generate new API keys
3. Rotate all related passwords
4. Audit recent account activity
5. Update credentials in your secure environment

### If Unexpected Trades Occur

1. Activate the **kill switch**
2. Log into IG directly and verify positions
3. Close any unauthorized positions manually
4. Investigate logs for the cause
5. Do not resume trading until root cause is identified

## Deployment Checklist

Before going live:

- [ ] All tests passing
- [ ] Demo mode tested for minimum 30 days
- [ ] Kill switch tested and working
- [ ] Risk limits configured appropriately
- [ ] Audit logging enabled
- [ ] Backup recovery plan documented
- [ ] Emergency contacts documented
- [ ] IG support contact information saved
