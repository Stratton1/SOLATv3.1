# SOLAT v3.1 - Trading Terminal

A production-grade desktop trading terminal for algorithmic trading with IG broker integration.

## Features

- **Elite 8 Strategies**: Modular strategy pack with deterministic, no-lookahead signals
- **Backtesting Engine**: Deterministic bar-driven engine with realistic spread/slippage fills and artefact outputs
- **Historical Data Layer**: Local Parquet OHLCV store with aggregation (1m → 5m/15m/1h/4h) and quality checks
  - **Latest-First Querying**: API returns the most recent data by default when no date range is provided.
  - **Symbol Aliasing**: Automatic resolution between catalogue symbols (e.g., XAUUSD) and storage keys (e.g., GOLD).
- **Realtime Market Data (Backend)**: Market subscribe/status endpoints, quote + bar events over WebSocket, overlay/signal endpoints
- **IG Broker Integration (DEMO)**: REST auth, accounts, market search, instrument catalogue, execution controls
- **Risk Management**: Size caps, position limits, trade-rate limiting, reconciliation, kill switch, append-only audit ledger
- **Desktop Terminal (Frontend)**: Tauri + React terminal UI (Terminal screen charting is in progress)

## Prerequisites

- **Python 3.11+** with [uv](https://github.com/astral-sh/uv)
- **Node.js 18+** with [pnpm](https://pnpm.io)
- **Rust** (for Tauri) - install via [rustup](https://rustup.rs)

### macOS Quick Install

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install pnpm
npm install -g pnpm
```

## Quick Start

### 1. Clone and Setup

```bash
cd SOLATv3.1

# Copy environment template
cp .env.example .env

# Edit .env with your IG credentials
# IMPORTANT: Never commit .env to version control!
```

### 2. Run Development Mode

```bash
# Start both engine and UI
./scripts/dev.sh

# Or run separately:
# Terminal 1: Start Python engine
pnpm dev:engine

# Terminal 2: Start Tauri UI
pnpm dev:ui
```

### 3. Access the Terminal

The Tauri window will open automatically. You should see:
- Engine health status (green = connected)
- WebSocket heartbeat counter incrementing
- Execution controls (connect/arm/kill switch)
- Market data status (connected/stale/disconnected)

## Project Structure

```
SOLATv3.1/
├── apps/
│   └── desktop/          # Tauri + React UI
├── engine/
│   └── solat_engine/     # Python trading engine
├── docs/                 # Documentation
├── scripts/              # Dev/build scripts
└── data/                 # Runtime data (gitignored)
```

## Configuration

All configuration is via environment variables. See `.env.example` for available options.

| Variable | Description | Default |
|----------|-------------|---------|
| `SOLAT_MODE` | Trading mode (DEMO/LIVE) | DEMO |
| `SOLAT_PORT` | Engine server port | 8765 |
| `IG_API_KEY` | IG API key | - |
| `IG_USERNAME` | IG username | - |
| `IG_PASSWORD` | IG password | - |
| `IG_ACC_TYPE` | IG account type (DEMO/LIVE for API base URL) | DEMO |
| `EXECUTION_MODE` | Execution mode (DEMO/LIVE) | DEMO |
| `EXECUTION_RECONCILE_INTERVAL_S` | Broker reconciliation interval (seconds) | 5 |
| `MAX_POSITION_SIZE` | Per-trade size cap | - |
| `MAX_CONCURRENT_POSITIONS` | Max open positions | - |
| `MAX_DAILY_LOSS_PCT` | Daily loss kill threshold (%) | - |
| `MAX_TRADES_PER_HOUR` | Trade rate limit | - |
| `PER_SYMBOL_EXPOSURE_CAP` | Exposure cap per symbol | - |
| `CLOSE_ON_KILL_SWITCH` | Close positions when kill switch activates | false |
| `MARKET_DATA_MODE` | Market data mode (stream/poll) | poll |
| `MARKET_DATA_POLL_INTERVAL_MS` | Poll cadence (ms) when in poll mode | 1500 |
| `MARKET_DATA_PERSIST_BARS` | Persist realtime bars to Parquet store | true |

## Current Status

Completed phases (engine + API):
- Phase 001: Core infrastructure (monorepo, engine sidecar, health/WS)
- Phase 002: IG REST auth + instrument catalogue
- Phase 003: Historical data layer (Parquet store + aggregation + quality + sync jobs)
- Phase 004: Backtest engine v1 + Elite 8 runtime + sweep runner
- Phase 005: Live execution v1 (DEMO) + reconciliation + kill switch + audit ledger
- Phase 006: Realtime market data backend + overlays/signals endpoints

In progress:
- Phase 007: Terminal UI (candles + overlays + signals + live execution markers)

See `docs/ROADMAP.md` for the canonical phase plan.

## Development

### Python Engine

```bash
cd engine

# Run tests
source .venv/bin/activate && pytest

# Run linter
source .venv/bin/activate && ruff check .

# Run type checker
source .venv/bin/activate && mypy solat_engine

# Format code
source .venv/bin/activate && ruff format .
```

### Desktop UI

```bash
# Type check
pnpm typecheck

# Lint
pnpm lint
```

## Building for Release

### Version Management

All component versions are synchronized. Check current versions:

```bash
pnpm version:check
```

Bump version across all files:

```bash
# Patch release (3.1.0 → 3.1.1)
pnpm version:patch

# Minor release (3.1.0 → 3.2.0)
pnpm version:minor

# Major release (3.1.0 → 4.0.0)
pnpm version:major
```

### Build Commands

```bash
# Build everything (engine wheel + UI + Tauri app)
pnpm build:all

# Build individual components
pnpm build:engine   # Python wheel in engine/dist/
pnpm build:ui       # Vite bundle
pnpm build:tauri    # Native app in apps/desktop/src-tauri/target/release/

# Full release (lint + test + build)
pnpm release
```

### Output Locations

- **Engine wheel**: `engine/dist/solat_engine-*.whl`
- **Desktop app**: `apps/desktop/src-tauri/target/release/solat-desktop` (or `.app` on macOS)

## Troubleshooting

### Engine won't start

1. **Port in use**: Check if port 8765 is free
   ```bash
   lsof -i :8765
   ```

2. **Missing dependencies**: Reinstall Python packages
   ```bash
   cd engine && uv pip install -e ".[dev]"
   ```

3. **Missing .env file**: Copy from template
   ```bash
   cp .env.example .env
   ```

### UI shows "Engine Offline"

1. **Engine not running**: Start the engine first
   ```bash
   pnpm dev:engine
   ```

2. **Wrong port**: Ensure engine is on port 8765

3. **Network issue**: The UI expects `127.0.0.1:8765` - check no firewall blocks this

### IG Login Test Fails

1. **Credentials not set**: Check `.env` has `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD`

2. **Wrong account type**: Set `IG_ACC_TYPE=DEMO` for demo accounts

3. **Rate limited**: Wait a moment and try again

### Build Errors

1. **Rust not installed**: Install via [rustup](https://rustup.rs)
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

2. **Missing Tauri dependencies (macOS)**:
   ```bash
   xcode-select --install
   ```

3. **pnpm not found**: Install globally
   ```bash
   npm install -g pnpm
   ```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Conventions](docs/CONVENTIONS.md) - Coding standards
- [Security](docs/SECURITY.md) - Security guidelines
- [Roadmap](docs/ROADMAP.md) - Development phases

## Security

⚠️ **IMPORTANT**:
- Never commit credentials to version control
- Start with DEMO mode before live trading
- Test the kill switch regularly
- Read [Security Guidelines](docs/SECURITY.md) before live trading

## License

MIT License.
