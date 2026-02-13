# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

SOLAT (Strategic Opportunistic Leveraged Algorithmic Trading) is a desktop trading terminal:
- **Desktop shell**: Tauri v2 + React/TypeScript (`apps/desktop/`)
- **Trading engine**: Python FastAPI sidecar (`engine/solat_engine/`)
- **Broker**: IG Markets (REST + Lightstreamer)
- **Strategies**: "Elite 8" pack with deterministic signals

## Prerequisites

- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- Node.js 18+ with [pnpm](https://pnpm.io)
- Rust (for Tauri) via [rustup](https://rustup.rs)

## Development Commands

```bash
# Start full development environment (engine + UI)
./scripts/dev.sh

# Or run separately:
pnpm dev:engine          # Python on 127.0.0.1:8765 (uses uv run)
pnpm dev:ui              # Tauri dev on port 1420

# Testing (use python3, not python, on macOS)
pnpm test                # All tests
pnpm test:engine         # Python tests only
cd engine && python3 -m pytest tests/test_backtest_engine_basic.py -v         # Single file
cd engine && python3 -m pytest tests/test_backtest_engine_basic.py::test_function -v  # Single test
cd engine && python3 -m pytest tests/chaos/ -v -m chaos  # Chaos tests only

# Linting & Type Checking
pnpm lint:all            # Lint everything
pnpm typecheck:all       # Type check everything
pnpm format              # Auto-format (ruff for Python)

# Building
pnpm build:all           # Full build (UI + Tauri app)
pnpm release             # lint + test + build:all

# Version management (synchronized across all components)
pnpm version:check       # Show current version
pnpm version:patch       # Bump patch (3.1.0 → 3.1.1)
```

## Architecture

```
┌──────────────────────────────────────┐
│        Tauri Desktop Shell           │
│  ┌────────────────────────────────┐  │
│  │     React UI (TypeScript)      │  │
│  │  Charts │ Controls │ Blotter   │  │
│  └────────────────────────────────┘  │
│              HTTP/WS ↕                │
│         localhost:8765               │
│  ┌────────────────────────────────┐  │
│  │   Python Engine (FastAPI)      │  │
│  │  Strategies │ Backtest │ Risk  │  │
│  │  Data (Parquet) │ Execution    │  │
│  └────────────────────────────────┘  │
│              HTTPS ↕                  │
│  ┌────────────────────────────────┐  │
│  │   IG Broker (REST + Stream)    │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

**Key data flows:**
- Live: Market Data → Strategy → Risk Engine → Execution Router → IG Broker
- Backtest: Parquet OHLCV → Bar Iterator (no lookahead) → Strategy → Fill Simulator → Metrics

## Architectural Invariants

1. **Demo-first**: Execution defaults to DEMO; LIVE requires multi-gate confirmation
2. **Localhost-only**: Engine binds to 127.0.0.1 only
3. **Broker truth**: In live mode, IG is source of truth; local state reconciles to broker
4. **No secrets in code**: Credentials via env vars with `SecretStr`; never log tokens; use `redact_sensitive()` before logging any request/response
5. **Deterministic backtests**: No lookahead, no hidden randomness
6. **Strategy logic in engine only**: UI renders data from engine; never computes indicators/signals
7. **All orders through router**: No direct broker calls; every order passes through risk engine and kill switch
8. **Minimal Rust layer**: Tauri Rust backend is thin (window lifecycle, plugins only). All trading/backtest/broker logic lives in Python engine. Prefer HTTP/WS calls to engine over new Tauri commands
9. **CSP locked to engine**: Tauri CSP connect-src allows only `http://127.0.0.1:8765` and `ws://127.0.0.1:8765`; no external URLs without explicit justification

## Engine Module Layout

| Module | Purpose |
|--------|---------|
| `api/` | FastAPI routers (health, ig, catalog, data, backtest, execution, market_data, chart, optimization, diagnostics, autopilot, recommendation) |
| `broker/ig/` | IG REST client (`client.py`), rate limiter, credential redaction (`redaction.py`), response types. All calls must go through rate limiter; use correct IG API Version header per endpoint |
| `catalog/` | 28-asset instrument catalogue with symbol↔epic mapping |
| `data/` | ParquetStore, timeframe aggregation (1m→5m/15m/1h/4h), quality checks, IG history fetch |
| `domain/` | Bar, Instrument, Signal, Order, Fill, Position (Pydantic models) |
| `backtest/` | Deterministic engine, broker simulator, portfolio, metrics, sweep |
| `strategies/` | Elite 8 strategies (`elite8.py`, `elite8_hardened.py`) + shared `indicators.py` |
| `execution/` | Router, risk engine, kill switch, reconciliation, audit ledger |
| `market_data/` | Polling/streaming, bar builder, WebSocket publisher |
| `runtime/` | Event bus, artefact manager, run context, jobs |
| `optimization/` | Parameter optimization, strategy selector, walk-forward |
| `interfaces/` | Abstract protocol definitions |

## Desktop UI Layout

Screens are tab-navigated via `App.tsx` with `Meta+N` hotkeys. Tab order:
Dashboard (`/`) → Terminal → Backtests → Optimise → Library → Blotter → Status (`/status`) → Settings

- **Screens**: `src/screens/` (most tabs) + `src/components/StatusScreen.tsx` (legacy location)
- **Hooks**: `src/hooks/` — `useEngineHealth`, `useExecutionStatus`, `usePositions`, `useAutopilot`, `useWebSocket`, etc.
- **Engine client**: `src/lib/engineClient.ts` — typed singleton wrapping all engine REST calls
- **Command palette**: `Meta+K` → fuzzy search over `src/lib/commands.ts` registry
- **Charting**: Plotly.js (finance bundle) via `src/components/PlotlyChart.tsx` + `src/components/CandleChart.tsx`
- **Theming**: CSS custom properties in `:root` (`styles.css`), TypeScript tokens in `src/theme/tokens.ts`
- **Fonts**: Geist (sans-serif) + JetBrains Mono (monospace), self-hosted via `public/fonts/`

## Testing Patterns

Tests use **FastAPI `dependency_overrides`** for DI (not `@patch`). Key fixtures are in `engine/tests/api_fixtures.py`:

```python
# Core DI dependencies to override in tests:
from solat_engine.config import get_settings_dep
from solat_engine.api.ig_routes import get_ig_client       # for IG API routes
from solat_engine.api.execution_routes import get_ig_client  # for execution routes

# Use TestSettings (dataclass) instead of real Settings
# Use DependencyOverrider helper to manage overrides
# Use create_test_client() for standard setup
# Call reset_execution_state() before execution tests
```

- `asyncio_mode = "auto"` in pytest config — async tests work without explicit markers
- For async in `TestClient`: use `asyncio.get_event_loop().run_until_complete()`, not `async def`
- Chaos tests use markers: `@pytest.mark.chaos`, `@pytest.mark.tier1` through `tier4`

## Domain Model Rules

- Use `Decimal` for all price/quantity values (never float for money)
- Use `UUID` for internal IDs, `str` for broker IDs
- Pydantic `BaseModel` with `frozen=True` for value objects
- All timestamps are UTC datetime
- Enums use `str, Enum` pattern (e.g. `OrderSide`, `OrderStatus`, `Timeframe`)

## API Surface

REST routes: `/health`, `/config`, `/ig/*`, `/catalog/*`, `/data/*`, `/backtest/*`, `/execution/*`, `/market/*`, `/chart/*`, `/optimization/*`, `/diagnostics/*`, `/autopilot/*`, `/recommendation/*`

WebSocket at `/ws`: heartbeat (1s), connected, sync_*, backtest_*, execution_*, quote_received, bar_received, broker_connected/disconnected events via EventBus.

**API backward compatibility**: extend with new optional fields or version routes; do not remove/rename existing response fields without deprecation.

## Configuration

- Engine config: `engine/solat_engine/config.py` — Pydantic `BaseSettings` with `SOLAT_` env prefix
- IG credentials: `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD` — all `SecretStr`, never log `.get_secret_value()`
- Copy `.env.example` to `.env` for local development
- `data_dir` from config for all data paths — no hardcoded paths

## Logging

```python
from solat_engine.logging import get_logger
logger = get_logger(__name__)

# Always use structured logging with extra dict
logger.info("Order submitted", extra={"order_id": str(order.id), "symbol": order.symbol})

# Never log credentials — log bool instead
logger.info("API key configured: %s", bool(api_key))

# Use redact_sensitive() from broker/ig/redaction.py before logging any request/response
```

## Execution Safety

- **Risk engine**: 9 checks — position size caps, concurrent position limits, daily loss limits, trades/hour, per-symbol exposure, stop-loss requirement
- **Kill switch**: When active, no new orders; optionally closes all positions; must be explicitly reset
- **Reconciliation**: Broker state is truth; local state syncs to it
- **Audit ledger**: Append-only log of all intents, orders, fills — no deletion

## Code Style

**Python** (engine/):
- Formatter/Linter: ruff (line length 100)
- Type checker: mypy (strict mode, Pydantic plugin)
- Tests: pytest with pytest-asyncio
- Modules: `snake_case.py`, classes: `PascalCase`, constants: `SCREAMING_SNAKE_CASE`

**TypeScript** (apps/desktop/):
- Linter: ESLint with TypeScript rules
- Components: `PascalCase.tsx`, named exports (no default exports), no `any`
- Hooks: `useCamelCase.ts` (e.g., `useEngineHealth.ts`)
- Screens: `PascalCase.tsx` under `src/screens/`

## Run Artifacts

Output to `data/runs/{run_id}/` where run_id = `{type}_{date}_{time}_{uuid8}` (type: backtest|paper|live):
```
├── config.json
├── signals.parquet
├── orders.parquet
├── fills.parquet
├── equity.parquet
├── metrics.json
└── logs/
```

## Current Development Phase

Per `docs/ROADMAP.md`:
- **Completed**: Phases 001-059 (foundations, IG connectivity, data layer, backtest engine, Elite 8 strategies, live execution)
- **In progress**: Phase 060-069 (Terminal UI - charting, overlays, markers)
- **Pending**: Phases 070+ (hardening, live trading)

Do not build later-phase features prematurely.

## Key Documentation

- `docs/ARCHITECTURE.md` - System design, data flows, WS event types
- `docs/ROADMAP.md` - Development phases
- `docs/SECURITY.md` - Credential handling, safety gating, CSP
- `docs/CONVENTIONS.md` - Coding standards, metrics JSON schema
- `docs/LIVE_RUNBOOK.md` - Live trading operations
