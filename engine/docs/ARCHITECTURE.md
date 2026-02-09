# SOLAT Engine Architecture

## Overview

SOLAT Engine is a deterministic trading backtesting and execution system. It supports both live trading via IG Markets API and offline historical backtesting with configurable spread/slippage/fees.

## Core Components

### Data Layer

```
solat_engine/data/
├── models.py          # HistoricalBar, SupportedTimeframe, quality models
├── parquet_store.py   # Parquet-based bar storage with symbol/timeframe partitioning
├── catalogue_store.py # SQLite metadata for gaps, quality scores
└── aggregation.py     # M1 -> higher timeframe aggregation
```

- **ParquetStore**: Stores historical bars in Parquet format with partitions by symbol/year/month
- **CatalogueStore**: SQLite database tracking data gaps, quality scores, and sync metadata
- **Aggregation**: Converts M1 (1-minute) bars to higher timeframes deterministically

### Backtest Engine

```
solat_engine/backtest/
├── models.py       # BacktestRequest, BacktestResult, TradeRecord, MetricsSummary
├── engine.py       # BacktestEngineV1 - main orchestration
├── broker_sim.py   # BrokerSim - order execution simulation
├── portfolio.py    # Portfolio - position tracking, equity curve
├── sizing.py       # Position sizing (fixed/risk-per-trade)
├── metrics.py      # Sharpe, Sortino, Calmar, drawdown calculations
└── sweep.py        # GrandSweep - batch bot×symbol×timeframe runner
```

#### BacktestEngineV1

The main backtest orchestrator:
1. Loads historical bars from ParquetStore
2. Runs bar-by-bar loop with warmup period
3. Generates signals via Elite 8 strategies
4. Executes orders via BrokerSim
5. Tracks portfolio state and equity curve
6. Writes artefacts (Parquet + JSON)

#### BrokerSim

Simulates order execution with realistic costs:
- **Fill Price Model**:
  - BUY: `bar_close + half_spread + slippage`
  - SELL: `bar_close - half_spread - slippage`
- Configurable per-instrument spread and slippage
- Fee calculation: flat + per-lot + percentage

#### Artefacts

Each backtest run produces:
```
backtests/{run_id}/
├── manifest.json      # Run metadata, request params
├── equity_curve.parquet  # Timestamp, equity, cash, drawdown
├── trades.parquet     # Entry/exit prices, PnL, MAE/MFE
├── orders.parquet     # All orders with fill details
├── metrics.json       # Combined + per-bot metrics
└── warnings.json      # Accumulated warnings
```

### Strategy Layer

```
solat_engine/strategies/
├── indicators.py   # EMA, SMA, RSI, MACD, ATR, Bollinger, Stochastic, Ichimoku
└── elite8.py       # 8 Ichimoku-based trading strategies
```

#### Elite 8 Strategy Suite

Eight distinct Ichimoku-based strategies:

| Bot | Name | Entry Logic |
|-----|------|-------------|
| 1 | TKCrossSniper | Tenkan-Kijun cross with cloud confirmation |
| 2 | KumoBreaker | Cloud breakout with momentum |
| 3 | ChikouConfirmer | Chikou Span trend confirmation |
| 4 | KijunBouncer | Kijun-sen bounce in trend |
| 5 | CloudTwist | Senkou A/B crossover anticipation |
| 6 | MomentumRider | RSI + MACD momentum with Ichimoku filter |
| 7 | TrendSurfer | EMA alignment with Ichimoku trend |
| 8 | ReversalHunter | Counter-trend at RSI extremes |

### Market Data Layer (Phase 009)

```
solat_engine/market_data/
├── models.py      # Quote, BarUpdate, MarketStreamStatus, QuoteCache
├── streaming.py   # LightstreamerClient - real-time IG streaming
├── polling.py     # PollingMarketSource - REST fallback
├── controller.py  # MarketDataController - stream/poll orchestration
├── backfill.py    # BackfillService - gap healing on reconnect
└── publisher.py   # MarketDataPublisher - throttling and broadcasting
```

- **MarketDataController**: Unified orchestrator with automatic stream/poll fallback
- **LightstreamerClient**: Production streaming via IG Lightstreamer HTTP streaming
- **BackfillService**: Gap healing when reconnecting (fetches missing bars)
- **MarketDataPublisher**: Quote throttling (10/sec per symbol) and WS broadcast

See [streaming.md](streaming.md) for detailed documentation.

### Execution Layer (Phase 005)

```
solat_engine/execution/
├── models.py          # ExecutionState, OrderIntent, OrderAck, PositionView
├── router.py          # ExecutionRouter - intent routing and order submission
├── risk_engine.py     # RiskEngine - position sizing, exposure caps, limits
├── kill_switch.py     # KillSwitch - emergency trading halt
├── reconciliation.py  # PositionStore, ReconciliationService
├── ledger.py          # ExecutionLedger - append-only audit log
└── safety.py          # ExecutionSafetyGuard - idempotency, circuit breaker
```

#### ExecutionRouter

The central coordinator for live execution:
1. Receives OrderIntent from signal generator
2. Validates via RiskEngine (size caps, exposure limits, daily loss)
3. Submits to broker via AsyncIGClient (if armed)
4. Records to ExecutionLedger (audit trail)
5. Updates PositionStore on confirmation

#### Signal → Intent → Order Pipeline

```
┌──────────┐    ┌─────────────┐    ┌────────────┐    ┌────────────┐
│  Signal  │───▶│ OrderIntent │───▶│ RiskEngine │───▶│  Broker    │
│(Strategy)│    │  (Intent)   │    │ (Validate) │    │ (Execute)  │
└──────────┘    └─────────────┘    └────────────┘    └────────────┘
                                          │
                                          ▼
                                   ┌────────────┐
                                   │   Reject   │
                                   │(with reason)│
                                   └────────────┘
```

#### RiskEngine Checks

| Check | Description | Action |
|-------|-------------|--------|
| max_position_size | Order size exceeds maximum | Cap to max |
| max_concurrent_positions | Too many open positions | Reject |
| daily_loss_limit | Daily loss exceeds threshold | Reject + kill switch |
| trade_rate_limit | Too many trades/hour | Reject |
| per_symbol_exposure | Symbol exposure cap | Reject |
| require_sl | Stop loss required but missing | Reject |

#### Kill Switch

Emergency halt mechanism:
- **Activation**: Manual or automatic (daily loss limit)
- **Effect**: Immediately disarms trading, blocks new orders
- **Optional**: Close all positions on activation
- **Reset**: Manual only (requires deliberate action)

#### Execution Safety (Phase 009)

Additional safety hardening for DEMO mode:

| Guard | Description |
|-------|-------------|
| IdempotencyGuard | Rejects duplicate intent_id within 60s window |
| CircuitBreaker | Pauses after 5 order errors in 60s (120s cooldown) |
| SizeValidator | Caps order size to 1 lot in DEMO mode |

#### Position Reconciliation

Broker is the source of truth:
```
┌─────────────┐     Periodic      ┌─────────────┐
│ Local Store │◄──────Sync───────▶│   Broker    │
│ (Positions) │                   │ (Positions) │
└─────────────┘                   └─────────────┘
        │
        ▼
  Detect Drift:
  - Added (opened externally)
  - Removed (closed externally)
  - Changed (partial close)
```

Events emitted for UI sync and alerting.

### API Layer

```
solat_engine/api/
├── data_routes.py      # /data/* endpoints
├── ig_routes.py        # /ig/* endpoints (live broker)
├── health_routes.py    # /health, /status
├── backtest_routes.py  # /backtest/* endpoints
└── execution_routes.py # /execution/* endpoints (live trading)
```

#### Backtest Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /backtest/bots | List available strategy bots |
| POST | /backtest/run | Start backtest job (async) |
| GET | /backtest/status | Get job status |
| GET | /backtest/results | Get metrics and artefact paths |
| GET | /backtest/trades | Paginated trade list |
| GET | /backtest/equity | Paginated equity curve |
| POST | /backtest/sweep | Start Grand Sweep batch |
| GET | /backtest/sweep/status | Get sweep status |
| GET | /backtest/sweep/results | Get sweep results |

#### Execution Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /execution/status | Get execution state (mode, armed, kill switch) |
| POST | /execution/connect | Connect to IG broker |
| POST | /execution/disconnect | Disconnect from broker |
| POST | /execution/arm | Arm execution (enable order submission) |
| POST | /execution/disarm | Disarm execution |
| POST | /execution/kill-switch/activate | Activate kill switch |
| POST | /execution/kill-switch/reset | Reset kill switch |
| GET | /execution/positions | Get current broker positions |
| POST | /execution/close-position | Close a specific position |
| POST | /execution/run-once | Run single execution cycle (testing) |

### WebSocket Events

Backtest progress is streamed via WebSocket:

```typescript
// Backtest event types
type BacktestEvent = {
  type: "backtest_started" | "backtest_progress" | "backtest_completed";
  run_id: string;
  // ... additional fields per event type
}

// Execution event types (Phase 005)
type ExecutionEvent = {
  type:
    | "execution_status"
    | "execution_intent_created"
    | "execution_order_submitted"
    | "execution_order_rejected"
    | "execution_order_acknowledged"
    | "execution_positions_updated"
    | "execution_reconciliation_warning"
    | "execution_kill_switch_activated"
    | "execution_kill_switch_reset";
  run_id?: string;
  timestamp: string;
  // ... additional fields per event type
}
```

Events are published to EventBus and forwarded to connected WebSocket clients.

## Data Flow

```
┌─────────────┐    ┌───────────────┐    ┌──────────────┐
│ ParquetStore│───▶│ BacktestEngine│───▶│   Artefacts  │
└─────────────┘    └───────────────┘    └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │   Portfolio  │
                   │  BrokerSim   │
                   │  Strategies  │
                   └──────────────┘
```

### Runtime Layer (Phase 009)

```
solat_engine/runtime/
├── event_bus.py     # EventBus - pub/sub for internal events
├── cache.py         # BoundedLRUCache, WindowedCounter, MemoryBoundedBuffer
└── ws_throttle.py   # WSEventThrottler - execution event compression
```

#### Bounded Caches

Memory-safe caching with automatic eviction:

| Cache | Purpose | Limits |
|-------|---------|--------|
| BoundedLRUCache | Generic key-value with LRU eviction | max_size, TTL |
| QuoteCache | Latest quotes per symbol | 100 symbols (LRU) |
| MemoryBoundedBuffer | Append-only event buffer | 10MB max |
| WindowedCounter | Sliding window rate counting | 10K events |

#### Event Throttling

WS event compression to reduce noise:
- Quote throttling: max 10 updates/sec per symbol
- Execution event dedup: status events within 2s window
- Critical events (orders, kill switch) never compressed

## Key Invariants

1. **Determinism**: Same inputs always produce same outputs
2. **No lookahead**: Only uses data up to current bar index
3. **UTC timestamps**: All times stored and processed in UTC
4. **Offline operation**: Backtests never call live broker APIs
5. **Bounded memory**: All caches have configurable limits (Phase 009)
