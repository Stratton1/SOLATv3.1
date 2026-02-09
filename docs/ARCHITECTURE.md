# SOLAT v3.1 Architecture

## Overview

SOLAT (Strategic Opportunistic Leveraged Algorithmic Trading) is a desktop trading terminal built with:
- **Tauri v2** - Secure, lightweight desktop shell
- **React/TypeScript** - Modern UI framework
- **Python** - Trading engine (FastAPI sidecar)
- **IG Broker** - Market connectivity

```
┌─────────────────────────────────────────────────────────────┐
│                    SOLAT Desktop Terminal                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Tauri Shell (Rust)                  │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │              React UI (TypeScript)             │  │   │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────────────┐  │  │   │
│  │  │  │ Charts  │ │ Controls│ │    Blotter      │  │  │   │
│  │  │  └─────────┘ └─────────┘ └─────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                   HTTP/WS │ localhost:8765                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Python Engine (FastAPI)                 │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │              Core Components                  │   │   │
│  │  │  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │   │   │
│  │  │  │Strategies│ │Backtest  │ │ Execution    │  │   │   │
│  │  │  │(Elite 8) │ │ Engine   │ │   Router     │  │   │   │
│  │  │  └─────────┘ └──────────┘ └──────────────┘  │   │   │
│  │  │  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │   │   │
│  │  │  │  Data   │ │  Risk    │ │   Event      │  │   │   │
│  │  │  │Provider │ │ Engine   │ │    Bus       │  │   │   │
│  │  │  └─────────┘ └──────────┘ └──────────────┘  │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                   HTTPS   │                                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               IG Broker (REST + Streaming)           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### Desktop Shell (Tauri)
- Window management and native OS integration
- Secure IPC between UI and sidecar
- Application lifecycle (start/stop Python process)
- File system access and credential storage

### UI Layer (React/TypeScript)
- Real-time charting with technical overlays
- Bot control panels and configuration
- Backtest runner and results visualization
- Trade blotter and audit trail display
- Settings management

### Trading Engine (Python/FastAPI)
- Strategy execution (Elite 8 pack)
- Backtest engine with realistic fills
- Risk management and position sizing
- Order lifecycle management
- Market data aggregation and storage

### Data Layer
- **Parquet**: Historical OHLCV storage
- **DuckDB**: Analytics queries
- **SQLite**: Application state and metadata

## Data Flow

### Live Trading Flow
```
Market Data (IG Streaming)
         │
         ▼
    Data Provider
         │
         ├──▶ Price Cache
         │
         ▼
    Strategy Engine
         │
         ├──▶ Signal (LONG/SHORT/FLAT)
         │
         ▼
    Risk Engine
         │
         ├──▶ Position Sizing
         ├──▶ Exposure Check
         │
         ▼
    Execution Router
         │
         ├──▶ Order Creation
         │
         ▼
    Broker Adapter (IG)
         │
         ├──▶ Submit Order
         │
         ▼
    Fill Confirmation
         │
         └──▶ Position Update ──▶ UI
```

### Backtest Flow
```
Historical Data (Parquet)
         │
         ▼
    Bar Iterator
         │
         ├──▶ [No Lookahead]
         │
         ▼
    Strategy Engine
         │
         ├──▶ Signal
         │
         ▼
    Broker Simulator
         │
         ├──▶ Fill Model (spread + slippage)
         │
         ▼
    Metrics Calculator
         │
         └──▶ BacktestResult ──▶ Artefacts
```

## Communication Protocols

### REST API (HTTP)
- `GET /health` - Engine health check
- `GET /config` - Configuration (redacted)
- `POST /backtest` - Run backtest (future)
- `GET /positions` - Current positions (future)
- `POST /orders` - Place order (future)

### WebSocket
- Heartbeat (1s interval)
- Price updates (subscribed symbols)
- Order events (created/filled/cancelled)
- Position updates

## Security Model

1. **Local-only binding**: Engine binds to 127.0.0.1 only
2. **No external network access from UI**: All external calls via engine
3. **Credential isolation**: Secrets in env vars, never in files
4. **CSP enforcement**: Strict content security policy in Tauri
5. **Demo-first**: Live trading requires explicit configuration

## Directory Layout

```
SOLATv3.1/
├── apps/
│   └── desktop/          # Tauri + React UI
│       ├── src/          # React components
│       └── src-tauri/    # Rust/Tauri code
├── engine/
│   ├── solat_engine/     # Python package
│   │   ├── domain/       # Domain models
│   │   ├── interfaces/   # Abstract base classes
│   │   ├── runtime/      # Event bus, artefacts
│   │   └── main.py       # FastAPI app
│   └── tests/            # Python tests
├── docs/                 # Documentation
├── scripts/              # Dev/build scripts
└── data/                 # Runtime data (gitignored)
    ├── runs/             # Backtest/live run artefacts
    ├── historical/       # Parquet price data
    └── logs/             # Application logs
```
