---
name: solat-backtest-regression
description: Adds backtest regression test: golden dataset, run backtest, snapshot metrics, assert within tolerance. Use when locking backtest results or adding regression test for strategy X.
---

# SOLAT Backtest Golden / Regression Agent (6.3)

When the user asks **"Lock backtest results"** or **"Add regression test for strategy X"**, output a **test script** (or test module) and **snapshot location** so changing strategy or fill model is caught by known-good outputs.

## Backtest artefacts

- **metrics.json:** run_id, strategy_id, symbol, timeframe, dates, capital, return_pct, drawdown, sharpe, trades, win_rate, profit_factor (see [docs/CONVENTIONS.md](docs/CONVENTIONS.md)).
- **equity.parquet,** **signals.parquet,** **orders.parquet,** **fills.parquet:** Under data/runs/{run_id}/.

## Regression test pattern

1. **Golden dataset:** Small, fixed set of bars (e.g. 1 symbol, 1 timeframe, fixed date range) stored in tests/fixtures/ or generated once and committed (or in CI artifact). Use ParquetStore or in-memory bars for BacktestEngineV1.
2. **Run backtest:** Call BacktestEngineV1 (or POST /backtest with fixed params); strategy + symbol + timeframe + date range fixed.
3. **Snapshot metrics:** After first run, save metrics (e.g. metrics.json or key fields) as expected snapshot (e.g. tests/fixtures/golden_metrics_strategy_X.json or inline in test).
4. **Assert:** In regression test, run backtest again; compare metrics to snapshot (allow small tolerance for float if needed, or exact match for deterministic run). Fail if metrics drift beyond tolerance.

## Optional: parameterise

- Strategy id, symbol, timeframe as pytest parameters so one test file can cover multiple golden runs.
- Snapshot per (strategy, symbol, timeframe) or single snapshot for one canonical run.

## Output format

1. **Test file path:** e.g. engine/tests/test_backtest_regression.py or test_backtest_golden.py.
2. **Fixture/data:** Where golden bars come from (path or fixture); where snapshot (expected metrics) is stored.
3. **Test steps:** Load bars → run BacktestEngineV1 (or trigger via API) with fixed config → load expected metrics → assert actual vs expected (with tolerance if documented).
4. **Snapshot location:** e.g. engine/tests/fixtures/golden_metrics_TKCrossSniper_EURUSD_1h.json.

Reference: [engine/solat_engine/backtest/engine.py](engine/solat_engine/backtest/engine.py), [docs/CONVENTIONS.md](docs/CONVENTIONS.md) (Metrics JSON Structure).
