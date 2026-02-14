# SOLAT v3.1 — Platform End State

Authoritative description of what the platform produces at each stage of the pipeline.

---

## Stage 1: Data Sync (IG → Parquet)

**Trigger**: `POST /data/sync` or `python3 engine/scripts/sync_history.py`

| Input | Output |
|-------|--------|
| IG API credentials + symbol list | Partitioned Parquet files + JSON manifests |

**Outputs**:
- `data/parquet/bars/instrument_symbol={SYMBOL}/timeframe={TF}/data.parquet` — OHLCV bars (timestamp_utc, open, high, low, close, volume)
- `data/parquet/manifests/{SYMBOL}_{TF}.json` — manifest with `first_available_from`, `last_synced_to`, `row_count`, `last_updated`

**Key metrics**: Row count per symbol/tf, date range coverage, sync duration.

---

## Stage 2: Single Backtest

**Trigger**: `POST /backtest/run` with `BacktestRequest`

| Input | Output |
|-------|--------|
| symbols, bots, timeframe, start/end, risk config | `BacktestResult` with per-bot `BotResult` + combined `MetricsSummary` |

**Outputs**:
- `BacktestResult.per_bot_results[]` — one `BotResult` per bot with `MetricsSummary`
- `BacktestResult.combined_metrics` — aggregate `MetricsSummary` across all bots
- Artefacts in `data/backtests/{run_id}/`: `config.json`, `signals.parquet`, `orders.parquet`, `fills.parquet`, `equity.parquet`, `metrics.json`

**MetricsSummary sections** (80+ fields):
- **A. Metadata**: bot, symbol, run_id, timeframe, data_start/end, bar_count, duration_days
- **B. Trade Summary**: total_trades, win_rate, profit_factor, expectancy, avg_win/loss, payoff_ratio, consecutive streaks
- **C. Equity/Performance**: total_return_pct, sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown_pct, volatility, CAGR
- **D. Risk/Distribution**: skewness, kurtosis, exposure_adjusted_return
- **E. Execution Realism**: total_orders, filled/rejected, spread/slippage/fees costs
- **F. Diagnostics**: data_gaps_detected, nan_inf_checks_passed, warnings_count
- **G. Extended**: trades_per_day, equity_peak, best/worst 5 trades, missing_bar_pct

---

## Stage 3: Grand Sweep (Parallel Multi-Combo)

**Trigger**: `POST /backtest/sweep` or `python3 engine/scripts/run_grand_sweep.py`

| Input | Output |
|-------|--------|
| bots × symbols × timeframes grid | `SweepResult` with per-combo `SweepComboResult` list |

**Outputs**:
- `SweepResult.results[]` — one `SweepComboResult` per combo (bot, symbol, tf, sharpe, max_drawdown, win_rate, total_trades, pnl)
- `SweepResult.top_performers[]` — ranked by Sharpe
- `data/sweep_results/{sweep_id}/` — per-combo JSON results
- Console/log output: leaderboard table, timing stats

**Parallelism**: `ParallelSweepRunner` using `ProcessPoolExecutor`. Combos sorted by `(symbol, tf)` for cache locality.

---

## Stage 4: Parameter Tuning (Optuna 2-Stage)

**Trigger**: `python3 engine/scripts/run_tuning.py`

| Input | Output |
|-------|--------|
| Sweep results + per-bot search spaces | Optimized variant params per combo |

**Outputs**:
- `data/tuning/{bot}_{symbol}_{tf}/` — Optuna study results
- `data/optimized_variants.json` — all tuned variants with params + scores
- Per-variant: `variant_id`, `params_override`, backtest `MetricsSummary`

**Process**: Stage 1 = coarse grid (50 trials), Stage 2 = refine around best (30 trials). Objective = Sharpe ratio from backtest.

---

## Stage 5: Walk-Forward Validation (IS/OOS Windows)

**Trigger**: `POST /optimization/walk-forward` or `python3 engine/scripts/run_wfo.py`

| Input | Output |
|-------|--------|
| combos + date range + window config | `WalkForwardResult` with per-fold windows |

**Outputs**:
- `WalkForwardResult.windows[]` — per-fold `WalkForwardWindow` with IS/OOS dates and OOS metrics
- `WalkForwardResult.aggregate_sharpe/return_pct/win_rate/trades` — cross-fold aggregates
- Per-fold: `oos_sharpe`, `oos_return_pct`, `oos_win_rate`, `oos_trades`
- Derived stability: `sharpe_cv` (coefficient of variation), `folds_profitable_pct`, `consistency_score`
- `data/artefacts/{wf_run_id}/` — folds.parquet, scorecard.parquet

---

## Stage 6: Scoring & Selection (Hard Gates + Weighted 0-100)

**Trigger**: Part of portfolio construction pipeline

| Input | Output |
|-------|--------|
| Combo metrics + WF results | `ComboScore` per combo (pass/reject + 0-100 score) |

**Hard Gates** (any fail = rejected):
- `max_drawdown_pct > 20%`
- `total_trades < 30` (sweep) or `oos_trades < 10` (WF)
- `exposure_time_pct` outside 1-90%
- `folds_profitable_pct < 50%`
- NaN/Inf in `oos_sharpe`, `oos_return_pct`, `max_drawdown_pct`

**Weighted Score** (0-100):
- 45% OOS Sharpe (clamped 0-6 → 0-100)
- 20% OOS Return (clamped 0-100%)
- 25% Drawdown (nonlinear, bonus ≤10%)
- 10% Trade confidence (trades_per_day + folds_profitable_pct, CV penalty)

**Stability penalties**: `sharpe_cv > 0.75` (-15 max), `folds_profitable_pct < 60%` (-8 max)

**Output**: `ComboScore.score_total`, `score_breakdown`, `rejected`, `rejection_reasons`

---

## Stage 7: Portfolio Construction (Diversified, Capped)

**Trigger**: `python3 engine/scripts/build_portfolio.py`

| Input | Output |
|-------|--------|
| Scored combos (passing hard gates) | Diversified allowlist with weights |

**Outputs**:
- `data/allowlist.json` — `AllowlistEntry[]` with score, params, evidence
- `data/portfolio/portfolio_YYYYMMDD.json` — portfolio snapshot
- Diversification caps: max per symbol (3), max per bot (5), max per timeframe

**Selection process**: Filter rejected → rank by score → diversify (cap per symbol/bot/tf) → assign weights → explain rationale.

---

## Stage 8: Autopilot Execution (DEMO Event-Driven)

**Trigger**: `POST /autopilot/start` (mode=DEMO only)

| Input | Output |
|-------|--------|
| Active allowlist + live market data | Signals → orders → fills (DEMO) |

**Process**: Subscribes to `BAR_RECEIVED` events → runs strategy `generate_signal()` → routes through risk engine → executes via IG DEMO API.

**Outputs**:
- Real-time signals via WebSocket (`/ws`)
- Execution audit in append-only ledger
- Position/PnL tracking via reconciliation

**Safety**: DEMO-first (LIVE requires multi-gate confirmation), kill switch, 9-check risk engine.

---

## Pipeline Dependency Graph

```
Data Sync (1) → Backtest (2) → Sweep (3) → Tuning (4) → WF Validation (5)
                                                              ↓
                                                    Scoring (6) → Portfolio (7) → Autopilot (8)
```

Each stage reads outputs from its predecessors. No stage can run without its upstream data.
