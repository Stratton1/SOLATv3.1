# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

SOLAT (Strategic Opportunistic Leveraged Algorithmic Trading) is a desktop trading terminal:
- **Desktop shell**: Tauri v2 + React/TypeScript (`apps/desktop/`)
- **Trading engine**: Python FastAPI sidecar (`engine/solat_engine/`)
- **Broker**: IG Markets (REST + Lightstreamer)
- **Strategies**: "Elite 8" pack with deterministic signals

## Development Commands

```bash
# Start full development environment (engine + UI)
./scripts/dev.sh

# Or run separately:
pnpm dev:engine          # Python on 127.0.0.1:8765 (uses uv run)
pnpm dev:ui              # Tauri dev on port 1420

# Testing
pnpm test                # All tests
pnpm test:engine         # Python tests only
cd engine && python3 -m pytest tests/test_backtest_engine_basic.py -v         # Single file
cd engine && python3 -m pytest tests/test_backtest_engine_basic.py::test_function -v  # Single test

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
4. **No secrets in code**: Credentials via env vars; never log tokens; always redact sensitive data
5. **Deterministic backtests**: No lookahead, no hidden randomness
6. **Strategy logic in engine only**: UI renders data from engine; never computes indicators/signals
7. **All orders through router**: No direct broker calls; every order passes through risk engine and kill switch

## Engine Module Layout

| Module | Purpose |
|--------|---------|
| `api/` | FastAPI routers (health, data, backtest, execution, chart, market_data) |
| `broker/ig/` | IG REST client, rate limiter, credential redaction |
| `catalog/` | 28-asset instrument catalogue with symbol↔epic mapping |
| `data/` | Parquet store, timeframe aggregation (1m→5m/15m/1h/4h), quality checks |
| `domain/` | Bar, Instrument, Signal, Order, Fill, Position (Pydantic models) |
| `backtest/` | Deterministic engine, broker simulator, metrics |
| `strategies/` | Elite 8 strategies + shared indicators |
| `execution/` | Router, risk engine, kill switch, reconciliation, audit ledger |
| `market_data/` | Polling/streaming, bar builder, WebSocket publisher |
| `interfaces/` | Abstract protocol definitions |
| `optimization/` | Parameter optimization / strategy tuning |

## Domain Model Rules

- Use `Decimal` for all price/quantity values (never float for money)
- Use `UUID` for internal IDs, `str` for broker IDs
- Pydantic `BaseModel` with `frozen=True` for value objects
- All timestamps are UTC datetime

## Execution Safety

- **Risk engine**: Position size caps, concurrent position limits, daily loss limits, trades/hour limits
- **Kill switch**: When active, no new orders; optionally closes all positions
- **Reconciliation**: Broker state is truth; local state syncs to it
- **Audit ledger**: Append-only log of all intents, orders, fills

## Current Development Phase

Per `docs/ROADMAP.md`:
- **Completed**: Phases 001-059 (foundations, IG connectivity, data layer, backtest engine, Elite 8 strategies, live execution)
- **In progress**: Phase 060-069 (Terminal UI - charting, overlays, markers)
- **Pending**: Phases 070+ (hardening, live trading)

## Code Style

**Python** (engine/):
- Formatter/Linter: ruff (line length 100)
- Type checker: mypy (strict mode)
- Tests: pytest with pytest-asyncio

**TypeScript** (apps/desktop/):
- Linter: ESLint with TypeScript rules
- Components: PascalCase files, named exports
- Hooks: `use` prefix (e.g., `useEngineHealth.ts`)

## Run Artifacts

Output to `data/runs/{run_id}/`:
```
{type}_{date}_{time}_{uuid8}/
├── config.json
├── signals.parquet
├── orders.parquet
├── fills.parquet
├── equity.parquet
├── metrics.json
└── logs/
```

## Cursor Rules

21 specialized rules in `.cursor/rules/` cover project-specific conventions (domain model, execution safety, IG broker, data layer, etc.). These are auto-applied by Cursor but contain useful context for any AI assistant.

## Key Documentation

- `docs/ARCHITECTURE.md` - System design, data flows
- `docs/ROADMAP.md` - Development phases
- `docs/SECURITY.md` - Credential handling, safety gating
- `docs/CONVENTIONS.md` - Coding standards
- `docs/LIVE_RUNBOOK.md` - Live trading operations
