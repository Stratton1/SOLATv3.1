---
name: solat-architecture-navigator
description: Maps SOLAT capabilities to file and directory paths. Use when the user asks where something lives, where to add code, or how data flows (e.g. "Where does IG auth live?", "Where should I add a new strategy?", "How does market data get to the strategy?"). Navigation only; no code generation.
---

# SOLAT Architecture Navigator

When the user asks **"Where does X live?"**, **"Where should I add Y?"**, or **"How does market data get to the strategy?"** (or similar), use this skill to return **file/directory paths and a one-line role** for each. Do not generate code; only navigate.

## Invariant

**UI never talks to IG.** Only the engine talks to IG. The UI talks only to the engine via HTTP + WebSocket on localhost (port 8765). All market data, orders, and positions flow through the engine.

## Capability → Path (Engine)

| Capability | Path | Role |
|------------|------|------|
| **App entry, health, config, WebSocket** | `engine/solat_engine/main.py` | FastAPI app, /health, /config, /ws, router includes |
| **Config, env, settings** | `engine/solat_engine/config.py` | Pydantic Settings (SOLAT_*, IG_*), data_dir, mode |
| **Domain models** | `engine/solat_engine/domain/` | Bar, Instrument, Signal, Order, Fill, Position |
| Bar, Timeframe | `engine/solat_engine/domain/bar.py` | Bar model, Timeframe enum |
| Order, OrderSide, OrderStatus | `engine/solat_engine/domain/order.py` | Order domain model |
| Position | `engine/solat_engine/domain/position.py` | Position model |
| Signal, SignalDirection | `engine/solat_engine/domain/signal.py` | Signal model |
| **Interfaces (ABCs)** | `engine/solat_engine/interfaces/` | BrokerAdapter, DataProvider, Strategy, BacktestEngine |
| **IG REST client, auth, session** | `engine/solat_engine/broker/ig/client.py` | AsyncIGClient, auth, CST/X-SECURITY-TOKEN, retries |
| IG rate limiting | `engine/solat_engine/broker/ig/rate_limit.py` | Rate limiter for IG API |
| IG redaction, safe logging | `engine/solat_engine/broker/ig/redaction.py` | Redact sensitive headers/fields |
| IG types (accounts, markets) | `engine/solat_engine/broker/ig/types.py` | IG response models |
| **Instrument catalogue** | `engine/solat_engine/catalog/` | 28-asset list, symbol↔epic, store |
| Catalogue seed | `engine/solat_engine/catalog/seed.py` | Seed list |
| Catalogue store | `engine/solat_engine/catalog/store.py` | JSON-backed store |
| **Parquet, aggregation, quality, IG history** | `engine/solat_engine/data/` | HistoricalBar, ParquetStore, aggregate, quality, ig_history |
| Parquet store | `engine/solat_engine/data/parquet_store.py` | OHLCV read/write, dedupe |
| Timeframe aggregation | `engine/solat_engine/data/aggregate.py` | 1m→5m/15m/1h/4h |
| Data quality checks | `engine/solat_engine/data/quality.py` | Missing bars, duplicates |
| IG historical fetch | `engine/solat_engine/data/ig_history.py` | Chunked history from IG |
| **Backtest engine, sim, metrics** | `engine/solat_engine/backtest/` | Deterministic backtest, BrokerSim, portfolio, metrics, sweep |
| Backtest engine | `engine/solat_engine/backtest/engine.py` | BacktestEngineV1, bar feed, no lookahead |
| Broker simulator | `engine/solat_engine/backtest/broker_sim.py` | Fill model, spread/slippage |
| Backtest metrics | `engine/solat_engine/backtest/metrics.py` | Sharpe, Sortino, drawdown |
| Backtest sweep | `engine/solat_engine/backtest/sweep.py` | Batch sweep runner |
| **Strategies, Elite 8, indicators** | `engine/solat_engine/strategies/` | Elite 8 bots, shared indicators |
| Elite 8 implementations | `engine/solat_engine/strategies/elite8.py` | Strategy classes, BarData, SignalIntent |
| Indicators | `engine/solat_engine/strategies/indicators.py` | EMA, RSI, MACD, ATR, Ichimoku, etc. |
| **Execution: router, risk, kill switch** | `engine/solat_engine/execution/` | Signal→order, risk gates, reconciliation, kill switch |
| Execution router | `engine/solat_engine/execution/router.py` | Signal → intent → order |
| Risk engine | `engine/solat_engine/execution/risk_engine.py` | Exposure, daily loss, trades/hour caps |
| Kill switch | `engine/solat_engine/execution/kill_switch.py` | Emergency stop |
| Reconciliation | `engine/solat_engine/execution/reconciliation.py` | Broker = truth, position sync |
| **Market data: bars, streaming, polling** | `engine/solat_engine/market_data/` | Bar builder, streaming, polling, publisher |
| Bar builder | `engine/solat_engine/market_data/bar_builder.py` | Build bars from ticks |
| Streaming | `engine/solat_engine/market_data/streaming.py` | Lightstreamer client / placeholder |
| Polling | `engine/solat_engine/market_data/polling.py` | REST polling fallback |
| **Event bus, artefacts, run context** | `engine/solat_engine/runtime/` | EventBus, artefacts dir, run_context, jobs |
| Event bus | `engine/solat_engine/runtime/event_bus.py` | Publish/subscribe, event types |
| **API routes** | `engine/solat_engine/api/` | REST routers mounted in main |
| Backtest API | `engine/solat_engine/api/backtest_routes.py` | Run backtest, sweep |
| Catalog API | `engine/solat_engine/api/catalog_routes.py` | Instrument catalogue |
| Chart/overlays API | `engine/solat_engine/api/chart_routes.py` | Overlays, signals |
| Data API | `engine/solat_engine/api/data_routes.py` | Data sync, quality |
| Execution API | `engine/solat_engine/api/execution_routes.py` | Connect, arm, kill switch |
| IG API | `engine/solat_engine/api/ig_routes.py` | IG session, accounts |
| Market data API | `engine/solat_engine/api/market_data_routes.py` | Subscribe, status |

## Capability → Path (Desktop)

| Capability | Path | Role |
|------------|------|------|
| **App root** | `apps/desktop/src/App.tsx` | Root component, health + WS + layout |
| **Components** | `apps/desktop/src/components/` | StatusScreen, ExecutionPanel, CandleChart, etc. |
| Status, engine health | `apps/desktop/src/components/StatusScreen.tsx` | Engine status, config, heartbeat |
| Execution panel | `apps/desktop/src/components/ExecutionPanel.tsx` | Connect, arm, kill switch |
| **Hooks (engine/WS)** | `apps/desktop/src/hooks/` | useEngineHealth, useWebSocket, useExecutionStatus, useBars, useCatalogue, etc. |
| Engine health | `apps/desktop/src/hooks/useEngineHealth.ts` | GET /health, /config |
| WebSocket | `apps/desktop/src/hooks/useWebSocket.ts` | WS connection, heartbeat |
| Execution status | `apps/desktop/src/hooks/useExecutionStatus.ts` | Execution API (connect, arm, kill switch) |
| **Screens** | `apps/desktop/src/screens/` | Full-screen views (e.g. TerminalScreen) |
| **Tauri (Rust)** | `apps/desktop/src-tauri/` | Tauri config, capabilities, Rust commands |

## Data flow (short)

- **Market data → strategy:** IG or Parquet → data/market_data layer → backtest engine or live feed → `strategies/elite8.py` (BarData) → Signal. See `docs/ARCHITECTURE.md` for full Live and Backtest flow diagrams.
- **Strategy → order:** Signal → `execution/router.py` → risk_engine → broker/ig client → IG.
- **UI:** Only calls engine HTTP/WS; no direct IG or strategy logic.

## Output format

For each concept or feature the user asks about, respond with:

1. **Path(s):** Exact file or directory (e.g. `engine/solat_engine/execution/router.py`).
2. **Role:** One line (e.g. "Signal → intent → order; risk gating").
3. If the question is about flow, add one or two sentences pointing to `docs/ARCHITECTURE.md` (Live Trading Flow / Backtest Flow) and the relevant table rows above.

Do not generate or modify code. Navigation and pointers only.
