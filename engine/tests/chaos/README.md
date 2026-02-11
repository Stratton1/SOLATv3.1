# Chaos Testing Suite

## Purpose

The chaos testing suite validates that the SOLAT trading system handles critical failures gracefully before deploying to LIVE trading. CloudTwist achieved **7.87 OOS Sharpe** in walk-forward testing, making it a strong LIVE candidate, but we must ensure it degrades safely under real-world failure conditions.

**Without chaos testing, we risk:**
- Orders executed but not logged (audit trail lost)
- Positions open on broker but not tracked locally (risk limits bypassed)
- Kill switch state lost on restart (emergency stop ineffective)
- Account balance never updated (overleveraged positions approved)

## Test Organization

Tests are organized by severity tier:

### Tier 1: Data Corruption (BLOCKER for LIVE)
**Location**: `tier1_data_corruption/`

Silent failures that corrupt data or audit trails. **Must pass before LIVE trading.**

- **test_disk_full.py** - Disk full during ledger/snapshot writes
- **test_partial_writes.py** - Write succeeds but flush fails
- **test_stale_balance.py** - Risk checks with outdated account balance
- **test_ledger_corruption.py** - Recovery from corrupted JSONL entries

### Tier 2: State Inconsistency
**Location**: `tier2_state_inconsistency/`

State drift between local and broker systems.

- **test_partial_close.py** - Partial position closes (broker confirms less than requested)
- **test_duplicate_fills.py** - Idempotency and cache overflow scenarios
- **test_reconciliation_failures.py** - Broker timeouts during reconciliation
- **test_balance_refresh.py** - Account balance updates after fills

### Tier 3: Operational Blindness
**Location**: `tier3_operational_blindness/` (future)

Monitoring gaps and stale health checks.

- Health endpoint returning stale data
- Silent WebSocket disconnects
- Stream reconnection without backfill

### Tier 4: Recovery Scenarios
**Location**: `tier4_recovery/`

Restart and state restoration.

- **test_kill_switch_persistence.py** - Kill switch state across restarts
- **test_snapshot_flush.py** - Snapshot memory leak verification

## Running Tests

### All Chaos Tests
```bash
cd engine && python3 -m pytest tests/chaos/ -v -m chaos
```

### By Tier (Priority)
```bash
# Tier 1: Data corruption (MUST PASS before LIVE)
python3 -m pytest tests/chaos/tier1_data_corruption/ -v -m tier1

# Tier 2: State inconsistency
python3 -m pytest tests/chaos/tier2_state_inconsistency/ -v -m tier2

# Tier 4: Recovery scenarios
python3 -m pytest tests/chaos/tier4_recovery/ -v -m tier4
```

### Individual Test Files
```bash
# Single tier 1 test
python3 -m pytest tests/chaos/tier1_data_corruption/test_disk_full.py -v

# Single test function
python3 -m pytest tests/chaos/tier1_data_corruption/test_disk_full.py::test_ledger_write_fails__orders_rejected -v
```

### Exclude Chaos Tests (Normal Testing)
```bash
# Run all tests EXCEPT chaos
python3 -m pytest tests/ -v -m "not chaos"
```

## Writing Chaos Tests

### Pattern: SCENARIO → SETUP → INJECT CHAOS → VERIFICATION

All chaos tests follow this structure:

```python
import pytest
from tests.chaos.fixtures.disk_chaos import DiskChaos

@pytest.mark.chaos
@pytest.mark.tier1
def test_ledger_write_fails__orders_rejected():
    """
    SCENARIO: Disk full during ledger write
    EXPECTED: Order rejected, broker NOT called, ledger readable
    FAILURE MODE: Order submitted despite ledger failure (audit trail lost)
    """
    # SETUP: Create router, mock broker
    router = ExecutionRouter(...)
    mock_broker = AsyncMock()

    # INJECT CHAOS: Simulate disk full after 100 bytes
    with DiskChaos.disk_full_on_write(100):
        # VERIFICATION: Order should be rejected
        result = await router.submit_order_intent(intent)

        assert result.status == "REJECTED"
        assert "disk space" in result.reason.lower()
        mock_broker.submit_order.assert_not_called()  # Broker never called
```

### Key Principles

1. **Explicit failure modes**: Document what could go wrong in docstring
2. **Graceful degradation**: System should reject operations safely, not corrupt data
3. **No silent failures**: All errors must be logged or returned to caller
4. **Reproducible**: Use `seed_random` fixture for deterministic chaos
5. **Fast**: Use mocks, avoid real I/O or network calls

## Fixture Libraries

### BrokerChaos (`fixtures/broker_chaos.py`)
Simulates broker-side failures:
- `intermittent_timeout()` - Random broker timeouts
- `partial_fill()` - Partial order fills
- `duplicate_confirmation()` - Same deal_id for different orders
- `stale_position_list()` - Outdated position data
- `rate_limit_429()` - Rate limiting responses

### DiskChaos (`fixtures/disk_chaos.py`)
Simulates disk-related failures:
- `disk_full_on_write()` - OSError ENOSPC after N bytes
- `partial_write_on_flush()` - Write succeeds, flush fails
- `directory_disappears()` - Directory deleted mid-operation
- `corrupt_file_content()` - Byte-level corruption injection

### NetworkChaos (`fixtures/network_chaos.py`)
Simulates network failures (respx-based):
- `connection_refused()` - Connection errors
- `timeout_after_delay()` - ReadTimeout simulation
- `rate_limit_429()` - 429 with Retry-After header
- `intermittent_500()` - Random 500 errors
- `stale_data_response()` - Outdated API responses

## Success Criteria

Before LIVE trading, the system must:

1. **Zero Tier 1 failures** - No data corruption scenarios
2. **Graceful Tier 2 degradation** - State inconsistencies handled safely
3. **No regressions** - Existing 651 tests still pass
4. **Total test count**: 663 tests passing (651 existing + 12 chaos)

## Manual Verification (Post-Test)

After chaos tests pass, manually verify:

1. **Disk full recovery**
   ```bash
   # Fill up /tmp, start backtest, verify clear error message
   df -h /tmp
   ```

2. **Kill switch persistence**
   ```bash
   # Activate kill switch, restart engine, verify still active
   curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate
   # Restart engine
   curl http://127.0.0.1:8765/execution/kill-switch/status
   ```

3. **Partial close handling**
   - In DEMO mode: Submit large position
   - Manually close half via IG dashboard
   - Verify reconciliation detects drift and updates local state

4. **Balance refresh trigger**
   - Connect to engine, wait 10 minutes without trading
   - Submit order, verify balance refresh logged before risk check

## Known Limitations

- Chaos fixtures use mocking, not real failure injection (e.g., no actual disk full)
- Network chaos requires respx (HTTP-level), won't catch TCP-level issues
- Some failure modes require manual testing (e.g., OS-level resource limits)

## Next Steps

After chaos testing completes:

1. **Health Report Panel** - UI showing engine health, connection status, data quality
2. **Automated Alerts** - Desktop notifications for critical events
3. **Data Explorer** - Browse historical bars, backtests, sweep results
4. **Application Packaging** - Tauri bundler for macOS .app distribution
