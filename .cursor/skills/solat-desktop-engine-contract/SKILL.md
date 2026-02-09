---
name: solat-desktop-engine-contract
description: Maps desktop hooks to engine endpoints and WebSocket events. Use when adding UI for a feature, when the engine sends a new event and the UI must subscribe, or when editing hooks vs api.
---

# SOLAT Desktop–Engine Contract Agent (4.2)

When the user says **"Add UI for X"**, **"Engine now sends Y; how does UI subscribe?"**, or when editing desktop hooks vs engine api, output the **endpoint(s) or WebSocket event(s)** and the **hook(s) to add or change** so the UI uses the correct contract.

## Invariant

The UI talks only to the engine. Base URL: `http://127.0.0.1:8765` (or from env/config). WebSocket: `ws://127.0.0.1:8765/ws`. No direct IG or external API calls from the desktop.

## Desktop hooks → engine (current)

| Hook | Engine usage | Notes |
|------|--------------|--------|
| useEngineHealth | GET /health, GET /config | Status, version, config (redacted) |
| useWebSocket | WS /ws | Connection, heartbeat; subscribe to events |
| useExecutionStatus | /execution (connect, arm, disarm, kill switch, etc.) | Execution control and status |
| useCatalogue | /catalog (list, summary) | Instrument catalogue |
| useMarketStatus | /market/status (or equivalent) | Market connection status |
| useMarketSubscription | /market (subscribe, unsubscribe) | Symbol subscriptions |
| useBars | /data or /market bars | OHLCV bars for chart |
| useOverlays | /chart/overlays | EMA, RSI, etc. overlay series |
| useSignals | /chart/signals | Strategy signals for markers |
| useWsEvents | WS message handling | Typed handlers for sync, backtest, execution, quote, bar events |
| useBacktestRuns | /backtest (runs, results) | Backtest job list and results |
| useWorkspace | (local state or future endpoint) | Workspace/layout persistence |

## Adding a new UI feature that needs engine data

1. **Identify data source:** REST endpoint (method, path, query/body) or WebSocket event type (e.g. backtest_progress, execution_positions_updated).
2. **Choose or add hook:** If an existing hook fits (e.g. useExecutionStatus for execution), extend it. Otherwise add a new hook under [apps/desktop/src/hooks/](apps/desktop/src/hooks/) (e.g. useX.ts) that calls the engine (fetch or WS subscription).
3. **Engine base URL:** Use a single source (env or config); do not hardcode `http://127.0.0.1:8765` in multiple places.
4. **WebSocket:** If the feature depends on a new event type, ensure (a) the engine publishes that event type to WS, (b) the desktop WS handler (e.g. useWsEvents) handles the type and exposes it to components.

## Engine sends a new event; UI must subscribe

1. **Event type:** Name and payload shape (e.g. type, run_id, timestamp, data fields).
2. **Where it’s published:** EventBus in [engine/solat_engine/main.py](engine/solat_engine/main.py) (lifespan) forwards to WS clients.
3. **Desktop:** In [apps/desktop/src/hooks/useWsEvents.ts](apps/desktop/src/hooks/useWsEvents.ts) (or equivalent), add a handler for the new type and expose state/callbacks to components. Document the event in ARCHITECTURE or api docs.

## Output format

For a given feature (e.g. "backtest progress"):

1. **Endpoint or WS event:** Method + path + request/response shape, or WS event type + payload.
2. **Hook changes:** Which hook to create or extend; what to fetch/subscribe to; what state to expose.
3. **Optional:** One-line reminder (base URL from config, no hardcoded URLs).

Reference: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (Communication Protocols, Data Flow).
