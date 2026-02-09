# Market Data Streaming

## Overview

SOLAT Engine provides real-time market data via IG Markets Lightstreamer integration. The system supports automatic fallback between streaming and polling modes with gap healing on reconnection.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MarketDataController                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐  │
│  │   Streaming     │◄──►│    Polling      │◄──►│  Backfill   │  │
│  │ (Lightstreamer) │    │ (REST Fallback) │    │   Service   │  │
│  └─────────────────┘    └─────────────────┘    └─────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    MarketDataPublisher                          │
│  - Quote throttling (10/sec per symbol)                         │
│  - Bar persistence to Parquet                                   │
│  - WebSocket broadcasting                                       │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### MarketDataController

The central orchestrator for market data (`market_data/controller.py`):

- **Mode switching**: Automatic fallback from stream to poll on errors
- **Recovery**: Automatic stream recovery after poll period
- **Backfill**: Gap healing when reconnecting
- **Health monitoring**: Tracks connection status and staleness

Configuration:
```python
# Default settings
poll_fallback_duration_s = 60.0   # How long to poll before attempting stream
backfill_on_reconnect = True      # Enable gap healing
stream_health_timeout_s = 30.0    # Time before marking stream as unhealthy
```

### LightstreamerClient

Real-time streaming via IG's Lightstreamer API (`market_data/streaming.py`):

**Protocol**:
- Uses HTTP streaming (long-polling) for TLCP protocol
- Subscribes to `MARKET:{epic}` items for L1 prices
- Fields: `BID`, `OFFER`, `UPDATE_TIME`, `MARKET_STATE`

**Reconnection**:
- Exponential backoff with jitter: `min(1s × 2^attempts, 60s) + random(0, 10%)`
- Maximum 10 reconnect attempts before stopping
- Automatic session re-establishment

**Message Format**:
```
U,<subscription_id>,<item_index>|<BID>|<OFFER>|<UPDATE_TIME>|<MARKET_STATE>
```

### PollingMarketSource

REST-based fallback (`market_data/polling.py`):

- Polls `/markets/{epic}` endpoint for quotes
- Configurable poll interval (default 500ms)
- Used when streaming unavailable or unstable

### BackfillService

Gap healing on reconnection (`market_data/backfill.py`):

```python
async def backfill_symbol(
    symbol: str,
    minutes: int = 5,              # Gap window to fill
    timeframe: SupportedTimeframe | None = None
) -> int:  # Returns bars fetched
```

Automatically triggered when:
1. Stream reconnects after disconnection
2. Mode switches from poll to stream

### MarketDataPublisher

Broadcasting and throttling (`market_data/publisher.py`):

**Quote Throttling**:
- Maximum 10 updates/second per symbol
- Intermediate quotes are dropped (latest wins)
- Different symbols throttled independently

**Bar Persistence**:
- Optional real-time bar persistence to Parquet
- Configurable via `set_persistence(enabled, parquet_store)`

**Broadcasting**:
- Publishes to EventBus for internal subscribers
- Broadcasts to WebSocket clients

## Quote Models

### Quote

```python
@dataclass
class Quote:
    symbol: str              # Canonical symbol (EURUSD)
    epic: str               # IG epic (CS.D.EURUSD.MINI.IP)
    bid: float
    ask: float
    mid: float              # Computed: (bid + ask) / 2
    spread: float           # Computed: ask - bid
    ts_utc: datetime
    update_time: str | None # From IG (HH:MM:SS)
```

### MarketStreamStatus

```python
@dataclass
class MarketStreamStatus:
    connected: bool
    mode: MarketDataMode     # STREAM | POLL
    stale: bool              # No ticks for > threshold
    stale_threshold_s: float
    last_tick_ts: datetime | None
    subscriptions: list[str]
    reconnect_attempts: int
    last_error: str | None
```

## Event Types

Market data events published to EventBus:

| Event | Description |
|-------|-------------|
| `QUOTE_RECEIVED` | New quote for a symbol |
| `BAR_RECEIVED` | New bar completed |
| `BROKER_CONNECTED` | Market data connected |
| `BROKER_DISCONNECTED` | Market data disconnected |

## Throttling & Compression

### Quote Throttling

```
Input:  100 quotes/sec for EURUSD
Output: 10 quotes/sec (throttled to max rate)
```

The publisher drops intermediate quotes, keeping only the latest:
- First quote in 100ms window: published
- Subsequent quotes in same window: stored as pending (overwritten)
- Pending quote delivered after interval elapses

### Execution Event Compression

The `WSEventThrottler` compresses execution events (`runtime/ws_throttle.py`):

**Never compressed** (critical events):
- `EXECUTION_INTENT_CREATED`
- `EXECUTION_ORDER_SUBMITTED`
- `EXECUTION_ORDER_REJECTED`
- `EXECUTION_ORDER_ACKNOWLEDGED`
- `EXECUTION_KILL_SWITCH_*`

**Compressed** (deduplicated within 2s window):
- `EXECUTION_STATUS` - if content unchanged
- `EXECUTION_POSITIONS_UPDATED` - if positions unchanged

## API Endpoints

### Stream Status

```
GET /diagnostics/stream_health
```

Returns:
```json
{
  "connected": true,
  "mode": "STREAM",
  "stale": false,
  "last_tick_ts": "2024-01-15T12:00:00Z",
  "subscriptions": ["EURUSD", "GBPUSD"],
  "reconnect_attempts": 0
}
```

### WebSocket Messages

Quote updates broadcast to connected clients:

```json
{
  "type": "quote_update",
  "symbol": "EURUSD",
  "bid": 1.1000,
  "ask": 1.1002,
  "mid": 1.1001,
  "ts": "2024-01-15T12:00:00.123Z"
}
```

Bar updates:

```json
{
  "type": "bar_update",
  "symbol": "EURUSD",
  "timeframe": "M1",
  "bar": {
    "ts": "2024-01-15T12:00:00Z",
    "o": 1.1000,
    "h": 1.1005,
    "l": 1.0998,
    "c": 1.1002,
    "v": 150
  }
}
```

## Bounded Caches

### QuoteCache

LRU cache for latest quotes:

```python
class QuoteCache:
    max_symbols: int = 100  # LRU eviction
    quotes: dict[str, Quote]
```

### BoundedLRUCache

Generic bounded cache with TTL:

```python
cache = BoundedLRUCache[str, int](
    max_size=1000,
    ttl_seconds=300.0,  # Optional TTL
)
```

### MemoryBoundedBuffer

Memory-limited buffer for events:

```python
buffer = MemoryBoundedBuffer[Event](
    max_bytes=10 * 1024 * 1024,  # 10MB
    entry_size_estimate=1000,
)
```

## Execution Safety

### IdempotencyGuard

Prevents duplicate order submissions:

```python
guard = IdempotencyGuard(config)
allowed, error = guard.check_and_register(intent_id)
# Returns (False, "Duplicate intent_id (seen 5.0s ago)") if duplicate
```

### CircuitBreaker

Pauses trading after repeated errors:

```python
config = SafetyConfig(
    error_threshold=5,      # Errors before tripping
    error_window_s=60.0,    # Window for error counting
    cooldown_s=120.0,       # Cooldown after tripping
)

breaker = CircuitBreaker(config)
breaker.record_error("Connection timeout")
# After 5 errors in 60s, breaker trips
# is_tripped = True for 120s
```

### SizeValidator (DEMO mode)

Enforces size caps in DEMO mode:

```python
config = SafetyConfig(demo_max_size=1.0)  # Max 1 lot
validator = SizeValidator(config, is_demo=True)
valid, error = validator.validate(5.0)
# Returns (False, "DEMO mode size cap: max 1.0 lots")
```

## Pre-Live Checklist

Run before live trading to verify system readiness:

```bash
python -m solat_engine.prelive_check
```

Checks:
1. Parquet store readable with M1 bars
2. Polling can fetch a quote
3. Execution config is DEMO mode
4. Risk engine smoke test
5. IG credentials configured and authenticated

Exit codes:
- `0`: All checks passed
- `1`: One or more checks failed

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOLAT_MODE` | `DEMO` | Execution mode (DEMO/LIVE) |
| `IG_USERNAME` | - | IG account username |
| `IG_PASSWORD` | - | IG account password |
| `IG_API_KEY` | - | IG API key |
| `IG_ACC_TYPE` | `DEMO` | IG account type |

## Testing

Run streaming tests:

```bash
pytest tests/test_streaming.py -v
pytest tests/test_throttle.py -v
```

Tests use mock IG client for simulation mode testing.
