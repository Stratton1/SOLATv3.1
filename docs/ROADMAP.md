# SOLAT v3.1 Development Roadmap

## Phase Overview

| Phase | Focus | Status |
|-------|-------|--------|
| 001-009 | Foundations | ✅ Complete |
| 010-019 | IG Connectivity | ✅ Complete |
| 020-029 | Data Layer | ✅ Complete |
| 030-039 | Backtest Engine | ✅ Complete |
| 040-049 | Elite 8 Strategies | ✅ Complete |
| 050-059 | Live Execution | ✅ Complete |
| 060-069 | Terminal UI | 🚧 In progress |
| 070-079 | Hardening | 🔲 Pending |
| 080+ | Live Trading | 🔲 Pending |

---

## Phase 001-009: Foundations ✅

**Objective**: Create monorepo structure with working Tauri + Python sidecar

### Deliverables
- [x] Repository structure (apps/desktop, engine/)
- [x] Python package with FastAPI
- [x] Domain models (Bar, Instrument, Signal, Order, Fill, Position)
- [x] Interfaces (BrokerAdapter, DataProvider, Strategy, BacktestEngine)
- [x] Event bus and runtime utilities
- [x] Configuration and logging system
- [x] Tauri v2 desktop shell
- [x] React UI with health display
- [x] WebSocket heartbeat connection
- [x] CI pipeline (tests + build)
- [x] Documentation (Architecture, Conventions, Security)

---

## Phase 010-019: IG Connectivity ✅

**Objective**: Implement IG broker adapter (demo mode)

### Deliverables
- [x] IG REST client (authentication, session management)
- [x] Account selection (demo/live)
- [x] Instrument search and catalogue
- [x] Price history fetching
- [x] Rate limiter with IG-specific error handling
- [ ] Streaming client (Lightstreamer) — placeholder/simulation only; production integration deferred
- [x] Real-time price subscriptions
- [ ] Account update subscriptions
- [x] Connection health monitoring

### Key Files
```
engine/solat_engine/broker/ig/
├── __init__.py
├── client.py          # REST client (session + retries + redaction)
├── rate_limit.py      # Rate limiting
├── redaction.py       # Secret redaction utilities
└── types.py           # IG-specific response models

engine/solat_engine/market_data/
├── models.py          # Quote/BarUpdate/Status models
├── polling.py         # REST polling fallback
└── streaming.py       # Lightstreamer client (placeholder/sim)
```

---

## Phase 020-029: Data Layer ✅

**Objective**: Build market data storage and retrieval

### Deliverables
- [x] Canonical instrument catalogue (28 assets)
- [x] Symbol ↔ Epic mapping
- [x] Parquet storage for OHLCV data
- [x] DuckDB query layer
- [x] Timeframe aggregation (1m → 5m/15m/1h/4h)
- [x] Data validation (missing bars, duplicates)
- [x] Historical data backfill from IG
- [x] Data integrity checks

### Key Files
```
engine/solat_engine/catalog/
├── models.py          # Instrument catalogue item model
├── seed.py            # 28-asset seed list
└── store.py           # JSON-backed store

engine/solat_engine/data/
├── ig_history.py      # Historical fetcher (chunked)
├── parquet_store.py   # Parquet store (upsert/dedupe)
├── aggregate.py       # Timeframe aggregation
└── quality.py         # Data quality checks
```

---

## Phase 030-039: Backtest Engine v1 ✅

**Objective**: Deterministic backtesting with realistic fills

### Deliverables
- [x] Event-driven backtest loop
- [x] Bar feed iterator (no lookahead)
- [x] Broker simulator
- [x] Fill model (spread + slippage)
- [x] Order types (market, attached SL/TP)
- [ ] Limit/stop order simulation (deferred)
- [x] Position tracking
- [x] Equity curve calculation
- [x] Performance metrics (Sharpe, Sortino, drawdown)
- [x] Trade blotter export
- [x] Artefact generation (JSON + Parquet)

### Key Files
```
engine/solat_engine/backtest/
├── engine.py          # Deterministic backtest engine
├── broker_sim.py      # Broker simulator (fills)
├── portfolio.py       # Positions + PnL
├── sizing.py          # Sizing + risk caps
├── metrics.py         # Performance metrics
└── sweep.py           # Batch sweep runner
```

---

## Phase 040-049: Elite 8 Strategy Pack ✅

**Objective**: Implement the 8 core trading strategies

### Deliverables
- [x] Shared indicator library (EMA, SMA, RSI, MACD, ATR, Bollinger, Stochastic, Ichimoku)
- [x] Elite 8 bots implemented (selectable by name)
- [x] Deterministic, no-lookahead signal generation
- [x] Unit tests (golden fixtures where applicable)
- [x] Reason codes for signal explanation

### Key Files
```
engine/solat_engine/strategies/
├── __init__.py
├── elite8.py          # Elite 8 implementations
└── indicators.py      # Shared indicators
```

---

## Phase 050-059: Live Execution v1 ✅

**Objective**: Execute trades on IG demo account

### Deliverables
- [x] Execution router (signal → intent → order)
- [x] Risk engine
  - [x] Exposure caps
  - [x] Max loss per day
  - [x] Max trades per hour
  - [x] Kill switch
- [x] Order lifecycle management
- [x] Position reconciliation (broker = truth)
- [x] Trade logging and audit
- [x] Error handling and recovery

### Key Files
```
engine/solat_engine/execution/
├── models.py          # Execution models + state
├── router.py          # Signal → intent → order
├── risk_engine.py     # Risk management + gates
├── reconciliation.py  # Broker truth sync
├── kill_switch.py     # Emergency stop
└── ledger.py          # Append-only audit log
```

---

## Phase 060-069: Terminal UI 🚧

**Objective**: Build full trading terminal interface

### Deliverables
- [x] Charting component (OHLC candlestick via lightweight-charts)
- [x] Indicator overlays (EMA, VWAP, Ichimoku, etc.)
- [x] Signal markers on chart
- [x] Entry/exit markers (execution markers with legend)
- [x] SL/TP visualization (dashed price lines with labels)
- [x] Bot control panels (StrategyDrawer with per-panel config)
- [x] Enable/disable per bot (toggle + params + apply-to-all)
- [x] Timeframe selection
- [x] Asset allowlist (catalogue search, preset groups, engine-synced)
- [x] Backtest runner UI (BacktestsScreen with run/sweep)
- [x] Results comparison (multi-select, metrics table, per-bot breakdown)
- [x] Trade blotter (events/fills/orders tabs, filters, CSV export)
- [x] Settings panel (SettingsScreen with diagnostics export, data sync, risk display)
- [x] Error boundary (RouteErrorBoundary wrapping all routes)
- [x] Navigation (React Router: Status, Terminal, Backtests, Blotter, Settings)
- [x] Connection status + offline banner
- [x] Light theme design system (tokens, CSS variables, white cards)

### Key Files
```
engine/solat_engine/api/
├── chart_routes.py          # Overlays + signals endpoints
└── market_data_routes.py    # Market subscribe/status endpoints

apps/desktop/src/
├── components/
│   ├── CandleChart.tsx      # Chart with markers, SL/TP, legend
│   ├── ExecutionPanel.tsx
│   ├── ErrorBoundary.tsx    # RouteErrorBoundary + copy error details
│   ├── GoLiveModal.tsx
│   ├── LiveBanner.tsx
│   ├── OfflineBanner.tsx
│   ├── backtest/
│   │   ├── BacktestRunViewer.tsx
│   │   └── BacktestComparison.tsx  # Multi-run comparison
│   ├── strategy/
│   │   └── StrategyDrawer.tsx      # Bots, presets, allowlist, risk
│   └── workspace/
│       ├── WorkspaceShell.tsx
│       └── ChartPanel.tsx          # Execution + SL/TP toggles
├── hooks/
│   ├── useExecutionStatus.ts
│   ├── useExecutionEvents.ts   # Fills + SL/TP levels for chart
│   ├── usePositions.ts         # Open positions
│   ├── useAllowlist.ts         # Engine-synced allowlist
│   ├── useLiveGates.ts
│   ├── useCatalogue.ts
│   ├── useMarketSubscription.ts
│   ├── useBars.ts
│   ├── useOverlays.ts
│   └── useSignals.ts
├── screens/
│   ├── TerminalScreen.tsx
│   ├── BacktestsScreen.tsx     # Multi-select comparison
│   ├── BlotterScreen.tsx       # Trade blotter (NEW)
│   └── SettingsScreen.tsx
├── theme/
│   └── tokens.ts               # Design system tokens
└── lib/
    ├── engineClient.ts         # Typed API client (extended)
    └── workspace.ts            # Panel model with showSlTp/showExecutions
```

---

## Known Issues (as of PROMPT 012)

- Backtest endpoints emit 4 `RuntimeWarning: coroutine was never awaited` warnings (cosmetic; progress callbacks in tests)
- Lightstreamer streaming client is placeholder/simulation only; production integration deferred
- Account update subscriptions not implemented
- Limit/stop order simulation deferred

---

## Phase 070-079: Hardening 🔲

**Objective**: Prepare for production use

### Deliverables
- [ ] Chaos testing
  - [ ] Disconnect handling
  - [ ] Partial fills
  - [ ] Order rejects
  - [ ] Rate limit recovery
  - [ ] Stale stream detection
- [ ] Health report panel
- [ ] Automated alerts
- [ ] Application packaging
- [ ] Code signing setup

---

## Phase 080+: Live Trading 🚧

**Objective**: Production LIVE trading with real money

### PROMPT 010: LIVE Trading Gating ✅

Multi-layer safety gating to prevent accidental LIVE trading:

- [x] **Configuration gates**
  - [x] `LIVE_TRADING_ENABLED` master switch (default: false)
  - [x] `LIVE_ENABLE_TOKEN` second-factor token
  - [x] `LIVE_ACCOUNT_ID` locked account enforcement
  - [x] `LIVE_MAX_ORDER_SIZE` mandatory size limit
  - [x] Risk settings validation for LIVE mode

- [x] **Runtime gates**
  - [x] Account verification (must be LIVE account, must match lock)
  - [x] Pre-live check (config, broker, risk, safety validation)
  - [x] UI confirmation (typed phrase + token + TTL expiry)
  - [x] Gate evaluation before arm and before each order

- [x] **UI workflow**
  - [x] GoLiveModal multi-step confirmation
  - [x] LiveBanner persistent warning when in LIVE mode
  - [x] LiveModeIndicator for status display
  - [x] useLiveGates hook for gate state

- [x] **Engine endpoints**
  - [x] `GET /execution/gates` - gate status
  - [x] `POST /execution/live/confirm` - confirm LIVE mode
  - [x] `POST /execution/live/revoke` - revoke confirmation
  - [x] `POST /execution/prelive/run` - run pre-live check
  - [x] `GET /execution/reconcile/report` - reconciliation status

- [x] **Order lifecycle**
  - [x] Order state machine with valid transitions
  - [x] OrderTracker for lifecycle tracking
  - [x] OrderRegistry for idempotency

- [x] **Documentation**
  - [x] `docs/LIVE_RUNBOOK.md` - operational procedures

### Key Files
```
engine/solat_engine/execution/
├── gates.py           # Multi-layer trading gates
├── models.py          # Order state machine + tracker
├── router.py          # Gate integration for arm/route
└── safety.py          # Circuit breaker + idempotency

engine/solat_engine/api/
└── execution_routes.py   # LIVE endpoints

apps/desktop/src/
├── components/
│   ├── GoLiveModal.tsx   # Multi-step LIVE enable
│   └── LiveBanner.tsx    # LIVE mode indicators
└── hooks/
    └── useLiveGates.ts   # Gate state management

docs/
└── LIVE_RUNBOOK.md       # Operational procedures
```

### Remaining Deliverables
- [ ] Live credential management
- [ ] A/B testing framework (paper vs live shadow)
- [ ] Small-size live validation
- [ ] Full deployment checklist
- [ ] Monitoring and alerting
- [ ] Disaster recovery plan
