# SOLAT v3.1 - Project Context

## Overview
SOLAT (Strategic Opportunistic Leveraged Algorithmic Trading) is a production-grade desktop trading terminal for algorithmic trading, integrated with the IG broker. It follows a sidecar architecture where a Python-based trading engine acts as a backend for a Tauri-based desktop application.

### Key Technologies
- **Backend (Trading Engine):** Python 3.11+, FastAPI, Pydantic, Parquet (Data storage), `uv` (Package management).
- **Frontend (Desktop UI):** React, TypeScript, Vite, Tauri (Rust), `lightweight-charts`.
- **Infrastructure:** Monorepo managed with `pnpm` workspaces.

### Architecture
- **Tauri Shell:** Manages the native window and the lifecycle of the Python engine sidecar.
- **UI Layer (React):** Provides real-time charting, strategy controls, backtest visualization, and trade blotters.
- **Trading Engine (Python):** Handles strategy execution (Elite 8 pack), backtesting, risk management, order routing, and market data aggregation.
- **Communication:** The UI communicates with the Engine via HTTP REST and WebSockets on `localhost:8765`.

---

## Building and Running

### Development
The main development entry point is the root `dev.sh` script or root `pnpm` commands.

- **Start All (Engine + UI):** `./scripts/dev.sh`
- **Start Engine Only:** `pnpm dev:engine` (Runs FastAPI with uvicorn on port 8765)
- **Start UI Only:** `pnpm dev:ui` (Runs Vite dev server for the React app)
- **Start Tauri Dev:** `pnpm tauri:dev` (Runs the full Tauri app in development mode)

### Build Commands
- **Full Release Build:** `pnpm release` (Runs lint, test, and build)
- **Build All:** `pnpm build:all`
- **Build Engine:** `pnpm build:engine` (Installs engine in editable mode)
- **Build UI:** `pnpm build:ui`
- **Build Tauri:** `pnpm build:tauri`

---

## Testing and Quality

### Engine (Python)
- **Run Tests:** `pnpm test:engine` (uses `pytest`)
- **Lint:** `pnpm lint:engine` (uses `ruff`)
- **Type Check:** `pnpm typecheck:engine` (uses `mypy`)
- **Format:** `pnpm format:engine` (uses `ruff format`)

### UI (TypeScript/React)
- **Run Tests:** `pnpm test:ui` (currently runs `typecheck`)
- **Lint:** `pnpm lint:ui` (uses `eslint`)
- **Type Check:** `pnpm typecheck:ui` (uses `tsc`)

---

## Development Conventions

### Python Engine
- **Naming:** `snake_case` for modules/functions, `PascalCase` for classes.
- **Models:** Use Pydantic `BaseModel`. Prefer immutable models (`frozen = True`).
- **Finance:** **ALWAYS** use `Decimal` for prices, quantities, and currency values. Never use `float`.
- **Logging:** Use structured logging via `solat_engine.logging`. Avoid logging sensitive credentials.
- **Exceptions:** Catch specific exceptions; log with context before re-raising.

### UI (TypeScript/React)
- **Naming:** `PascalCase` for components and types, `camelCase` for utilities/hooks.
- **Components:** Named exports, functional components, props interfaces defined locally.
- **State:** Use custom hooks to encapsulate complex logic. Avoid prop drilling beyond 2 levels.

### Git & Versioning
- **Commits:** Use conventional commits (e.g., `feat(engine): ...`, `fix(ui): ...`).
- **Versioning:** Synchronized across components via `scripts/bump_version.py`. Use `pnpm version:[patch|minor|major]`.

---

## Key Directories
- `apps/desktop/`: Tauri/React application.
- `engine/solat_engine/`: Python engine source code.
- `engine/tests/`: Engine unit and integration tests.
- `docs/`: Technical documentation (Architecture, Conventions, Roadmap, Security).
- `data/`: Runtime data, including historical Parquet files and backtest runs (gitignored).
- `scripts/`: Utility scripts for development and versioning.
