# Technology Stack

## Overview
SOLAT utilizes a sidecar architecture where a Python-based trading engine acts as a backend for a Tauri-based desktop application.

## Backend (Trading Engine)
- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Data Validation:** Pydantic
- **Data Storage:** Parquet (via `pyarrow`/`polars` implied)
- **Package Management:** `uv`
- **Testing:** `pytest`
- **Linting/Formatting:** `ruff`, `mypy`

## Frontend (Desktop UI)
- **Framework:** React
- **Language:** TypeScript
- **Build Tool:** Vite
- **Desktop Shell:** Tauri (Rust)
- **Charting:** `plotly.js-finance-dist` + `react-plotly.js`
- **Styling:** (To be confirmed, likely Tailwind or CSS Modules based on standard Vite apps)
- **Testing:** `vitest` (implied), `tsc` for types
- **Linting:** `eslint`

## Infrastructure
- **Monorepo Management:** `pnpm` workspaces
- **Version Control:** Git
- **CI/CD:** GitHub Actions (implied)
