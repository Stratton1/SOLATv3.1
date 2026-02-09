# SOLAT Engine Development Roadmap

## Phases

### Phase 001: Core Infrastructure ✅
- Project structure and configuration
- Domain models (Bar, Signal, Order, Fill, Position)
- Logging and settings management
- Health endpoints

### Phase 002: IG Markets Integration ✅
- IG REST API client with rate limiting
- Historical data fetching
- Account balance and positions
- Order placement (demo mode)

### Phase 003: Data Storage & Quality ✅
- Parquet-based bar storage
- SQLite metadata catalogue
- Gap detection and quality scoring
- M1 to higher timeframe aggregation
- Data sync endpoints

### Phase 004: Backtest Engine + Elite 8 ✅
- **Backtest Components**:
  - BacktestEngineV1 (bar-driven, deterministic)
  - BrokerSim (spread/slippage/fees)
  - Portfolio (positions, equity tracking)
  - Position sizing (fixed/risk-per-trade)
  - Metrics (Sharpe, Sortino, Calmar, drawdown)
  - GrandSweep (batch bot×symbol×timeframe)

- **Elite 8 Strategies**:
  - TKCrossSniper, KumoBreaker, ChikouConfirmer
  - KijunBouncer, CloudTwist, MomentumRider
  - TrendSurfer, ReversalHunter

- **Technical Indicators**:
  - EMA, SMA, RSI, MACD, ATR
  - Bollinger Bands, Stochastic
  - Full Ichimoku Cloud (Tenkan, Kijun, Senkou A/B, Chikou)

- **API Endpoints**:
  - POST /backtest/run (async job)
  - GET /backtest/status, /results, /trades, /equity
  - POST /backtest/sweep, GET /sweep/status, /sweep/results
  - GET /backtest/bots

- **Artefacts**:
  - manifest.json, equity_curve.parquet
  - trades.parquet, orders.parquet
  - metrics.json, warnings.json

- **WebSocket Events**:
  - backtest_started, backtest_progress, backtest_completed

### Phase 005: Live Execution v1 (DEMO) ✅
- **Execution Router**:
  - Connect/disconnect to IG DEMO
  - Arm/disarm gates for order submission
  - Signal → Intent → Order pipeline
  - Idempotency via dealReference

- **Safety Controls**:
  - Kill switch (manual + automatic)
  - Daily loss limit with auto-halt
  - Position size caps
  - Trade rate limiting
  - Symbol exposure caps
  - Stop loss requirement option

- **Risk Engine**:
  - Pre-order validation
  - Size capping and rounding
  - Dealing rules per symbol
  - Rejection with reason codes

- **Position Reconciliation**:
  - Broker as source of truth
  - Periodic sync (configurable interval)
  - Drift detection (added/removed/changed)
  - Warning events for external changes

- **Execution Ledger**:
  - Append-only JSONL audit log
  - Intent, submission, fill, rejection records
  - Daily rotation with Parquet compaction

- **WebSocket Events**:
  - execution_status, execution_intent_created
  - execution_order_submitted, execution_order_rejected
  - execution_order_acknowledged, execution_positions_updated
  - execution_reconciliation_warning
  - execution_kill_switch_activated, execution_kill_switch_reset

- **API Endpoints**:
  - /execution/status, /connect, /disconnect
  - /execution/arm, /disarm
  - /execution/kill-switch/activate, /reset
  - /execution/positions, /close-position
  - /execution/run-once

- **Restrictions**:
  - DEMO mode only (LIVE blocked)
  - Broker = truth for positions
  - Tokens never logged

### Phase 006: Desktop App Integration (Planned)
- Electron/Tauri frontend
- Real-time dashboard
- Strategy configuration UI
- Backtest visualization
- Execution control panel

## Status Legend
- ✅ Complete
- 🚧 In Progress
- ⏳ Planned
