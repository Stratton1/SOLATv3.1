# SOLAT v3.1 - Codebase Context

## Project Overview
**SOLAT** (Systematic Opportunistic Liquidity Automated Trading) is a Tauri desktop trading terminal with a Python FastAPI backend, designed for algorithmic forex/indices/commodities trading via the IG broker API.

## Tech Stack
- **Frontend:** Tauri + React + TypeScript
- **Backend:** Python 3.12 + FastAPI + Pydantic
- **Data:** Parquet (PyArrow) for historical bars
- **Broker:** IG Markets REST API (LIVE account configured)

## Directory Structure
```
solat_v3.1/
├── engine/                      # Python backend
│   ├── solat_engine/
│   │   ├── api/                 # FastAPI routes
│   │   │   ├── backtest_routes.py
│   │   │   ├── catalog_routes.py
│   │   │   ├── chart_routes.py
│   │   │   ├── data_routes.py
│   │   │   ├── execution_routes.py
│   │   │   ├── ig_routes.py
│   │   │   ├── market_data_routes.py
│   │   │   └── optimization_routes.py
│   │   ├── backtest/            # Backtesting engine
│   │   │   ├── engine.py
│   │   │   ├── models.py
│   │   │   ├── metrics.py
│   │   │   └── sweep.py
│   │   ├── brokers/             # Broker integrations
│   │   │   └── ig/
│   │   │       ├── client.py
│   │   │       └── models.py
│   │   ├── catalog/             # Instrument catalog
│   │   │   ├── models.py
│   │   │   ├── seed.py
│   │   │   └── symbols.py
│   │   ├── data/                # Data layer
│   │   │   ├── parquet_store.py
│   │   │   └── models.py
│   │   ├── execution/           # Order execution
│   │   │   └── manager.py
│   │   ├── optimization/        # Walk-forward optimization
│   │   │   └── walk_forward.py
│   │   ├── strategies/          # Trading strategies
│   │   │   ├── elite8.py        # 8 Ichimoku-based bots
│   │   │   └── indicators.py
│   │   ├── config.py            # Settings & DI
│   │   ├── main.py              # FastAPI app entry
│   │   └── logging.py
│   ├── scripts/
│   │   ├── import_histdata.py   # Historical data import
│   │   └── check_data_quality.py
│   ├── tests/                   # Test suite
│   ├── data/parquet/bars/       # Historical data (1.5GB)
│   └── .env                     # Credentials (LIVE)
├── src/                         # React frontend
├── src-tauri/                   # Tauri Rust backend
└── LIVE_READINESS_ROADMAP.md
```

## Current State (as of 2026-02-05)

### ✅ Complete
- 38 instruments imported (1.5GB, 2020-2025)
- IG LIVE account connected (WVK88)
- Elite 8 Ichimoku strategies implemented
- Walk-forward bug fixed (`combined_metrics`)
- FastAPI DI refactor complete
- `main.py` entry point fixed
- IG epic mapping complete (all 10 FX pairs have demo_epic/live_epic)
- Test suite DI migration complete:
  - Removed 18 @patch decorators from test_live_gates.py
  - Removed 3 @patch decorators from test_ig_endpoints.py
  - All tests now use DependencyOverrider pattern
  - All test files pass Python syntax check

### ⚠️ In Progress
- Full test suite validation (requires Python 3.11+ environment)

### ❌ Not Started
- Data quality validation
- Full backtest suite
- Walk-forward optimization
- Paper trading
- Risk controls audit
- Go-live checklist

## Key Files - Test Infrastructure

### DI Pattern for Tests
```
tests/api_fixtures.py          # TestSettings, DependencyOverrider, create_test_client
tests/conftest.py              # Imports fixtures, reset_singletons
```

### Test Pattern Example
```python
def test_example(self, api_client: TestClient, overrider, mock_settings) -> None:
    from solat_engine.api.some_routes import get_some_dep
    overrider.override(get_some_dep, lambda: mock_value)
    # ... test code ...
```

### Risk Controls (Priority 3)
```
solat_engine/execution/manager.py
solat_engine/execution/kill_switch.py
```

## API Endpoints
- `GET /health` - Health check
- `GET /config` - Configuration
- `POST /backtest/run` - Start backtest
- `POST /backtest/sweep` - Grand sweep
- `GET /backtest/bots` - List Elite 8 bots
- `POST /ig/login` - IG authentication
- `GET /data/bars/{symbol}` - Historical bars
- `POST /chart/overlays` - Indicator computation
- `WS /ws` - Real-time updates

## Elite 8 Bots
1. **TKCrossSniper** - Tenkan-Kijun cross with cloud confirmation
2. **KumoBreaker** - Cloud breakout with momentum
3. **ChikouConfirmer** - Chikou Span trend confirmation
4. **KijunBouncer** - Kijun-sen bounce in trend
5. **CloudTwist** - Senkou A/B cross anticipation
6. **MomentumRider** - RSI + MACD with Ichimoku filter
7. **TrendSurfer** - EMA alignment with Ichimoku trend
8. **ReversalHunter** - Counter-trend at extremes

## Environment Variables (.env)
```
SOLAT_MODE=LIVE
IG_ACC_TYPE=LIVE
IG_API_KEY=<redacted>
IG_USERNAME=<redacted>
IG_PASSWORD=<redacted>
IG_ACCOUNT_ID=WVK88
```
