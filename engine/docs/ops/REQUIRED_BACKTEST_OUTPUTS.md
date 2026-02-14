# Required Backtest Outputs

Authoritative field checklist for every combo type produced by the platform.

---

## 1. Single Backtest — MetricsSummary

Every `compute_metrics_summary()` call must produce all fields below. Default = 0 / 0.0 / False / None is acceptable for unused fields, but fields consumed by scoring (marked with **S**) and hard gates (marked with **G**) must be meaningfully populated.

### A. Run Metadata
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `bot` | str \| None | Yes | Bot name |
| `symbol` | str \| None | Yes | Instrument symbol |
| `run_id` | str \| None | Yes | Unique run identifier |
| `timestamp` | datetime \| None | Yes | Run completion time |
| `timeframe` | str \| None | Yes | Bar timeframe |
| `data_start` | datetime \| None | Yes | Backtest period start |
| `data_end` | datetime \| None | Yes | Backtest period end |
| `bar_count` | int | Yes | Number of bars processed |
| `duration_days` | float | Yes | Calendar days covered by backtest |
| `initial_cash` | float | Yes | Starting capital |
| `commission_model` | str | — | Default "flat" |
| `spread_model` | str | — | Default "fixed" |
| `slippage_model` | str | — | Default "fixed" |

### B. Trade Summary
| Field | Type | Required | Scoring | Notes |
|-------|------|----------|---------|-------|
| `total_trades` | int | Yes | **G** | Hard gate: ≥ 30 for sweep |
| `winning_trades` | int | Yes | | |
| `losing_trades` | int | Yes | | |
| `win_rate` | float | Yes | | 0.0–1.0 |
| `profit_factor` | float | Yes | | |
| `expectancy` | float | Yes | | |
| `avg_win` | float | Yes | | |
| `avg_loss` | float | Yes | | |
| `avg_trade_pnl` | float | Yes | | |
| `largest_win` | float | Yes | | |
| `largest_loss` | float | Yes | | |
| `avg_bars_held` | float | Yes | | |
| `median_trade_return_pct` | float | — | | |
| `max_consecutive_wins` | int | — | | |
| `max_consecutive_losses` | int | — | | |
| `long_trades` | int | — | | |
| `short_trades` | int | — | | |
| `median_bars_held` | float | — | | |
| `payoff_ratio` | float | — | | |

### C. Equity / Performance
| Field | Type | Required | Scoring | Notes |
|-------|------|----------|---------|-------|
| `total_return` | float | Yes | | Absolute PnL |
| `total_return_pct` | float | Yes | | Decimal (0.1 = 10%) |
| `annualized_return` | float | Yes | | |
| `cagr` | float | Yes | | |
| `sharpe_ratio` | float | Yes | | Annualized |
| `sortino_ratio` | float | Yes | | |
| `calmar_ratio` | float | Yes | | |
| `max_drawdown` | float | Yes | | Absolute |
| `max_drawdown_pct` | float | Yes | **G** **S** | Hard gate: ≤ 20%. Scoring: 25% weight (nonlinear) |
| `max_drawdown_duration_bars` | int | Yes | | |
| `volatility` | float | Yes | | Annualized |
| `start_equity` | float | Yes | | |
| `end_equity` | float | Yes | | |
| `downside_volatility` | float | — | | |
| `avg_drawdown_pct` | float | — | | |
| `avg_drawdown_duration_bars` | float | — | | |

### D. Risk / Distribution
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `skewness` | float | — | Return distribution |
| `kurtosis` | float | — | Return distribution |
| `exposure_adjusted_return` | float | — | |

### E. Execution Realism
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `total_orders` | int | Yes | |
| `filled_orders` | int | Yes | |
| `rejected_orders` | int | Yes | |
| `partial_fills_count` | int | — | |
| `avg_spread_paid` | float | Yes | |
| `avg_slippage` | float | Yes | |
| `total_spread_cost` | float | Yes | |
| `total_slippage_cost` | float | Yes | |
| `total_fees` | float | Yes | |
| `total_transaction_costs` | float | Yes | |

### F. Diagnostics
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `data_gaps_detected` | int | Yes | |
| `nan_inf_checks_passed` | bool | Yes | |
| `warnings_count` | int | — | |
| `time_in_market_pct` | float | Yes | 0.0–1.0 |

### G. Extended (Tuning Pipeline)
| Field | Type | Required | Scoring | Notes |
|-------|------|----------|---------|-------|
| `trades_per_day` | float | Yes | **S** | Scoring: 10% weight (confidence) |
| `equity_peak` | float | Yes | | |
| `best_5_trades_pnl` | list[float] | — | | |
| `worst_5_trades_pnl` | list[float] | — | | |
| `missing_bar_pct` | float | Yes | | Expected vs actual bar count |

---

## 2. Sweep Result — SweepComboResult

Per-combo summary from Grand Sweep.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `bot` | str | Yes | |
| `symbol` | str | Yes | |
| `timeframe` | str | Yes | |
| `sharpe` | float | Yes | From MetricsSummary.sharpe_ratio |
| `max_drawdown` | float | Yes | From MetricsSummary.max_drawdown_pct |
| `win_rate` | float | Yes | |
| `total_trades` | int | Yes | |
| `pnl` | float | Yes | |
| `params_hash` | str | — | |

---

## 3. Walk-Forward Fold — WalkForwardWindow

Per-fold OOS validation results.

| Field | Type | Required | Scoring | Notes |
|-------|------|----------|---------|-------|
| `window_id` | int | Yes | | Fold index |
| `in_sample_start` | datetime | Yes | | |
| `in_sample_end` | datetime | Yes | | |
| `out_of_sample_start` | datetime | Yes | | |
| `out_of_sample_end` | datetime | Yes | | |
| `oos_sharpe` | float \| None | Yes | **S** | 45% scoring weight |
| `oos_return_pct` | float \| None | Yes | **S** | 20% scoring weight |
| `oos_win_rate` | float \| None | Yes | | |
| `oos_trades` | int | Yes | **G** | Hard gate: ≥ 10 |

### WalkForwardResult Aggregates

| Field | Type | Required | Scoring | Notes |
|-------|------|----------|---------|-------|
| `aggregate_sharpe` | float \| None | Yes | | Cross-fold mean |
| `aggregate_return_pct` | float \| None | Yes | | Cross-fold mean |
| `aggregate_win_rate` | float \| None | Yes | | |
| `aggregate_trades` | int | Yes | | |

### Derived Stability Metrics (from `_aggregate_results()`)

| Metric | Type | Scoring | Notes |
|--------|------|---------|-------|
| `sharpe_cv` | float | **S** | CV of per-fold Sharpe; penalty if > 0.75 |
| `folds_profitable_pct` | float | **G** **S** | Hard gate: ≥ 50%. Scoring: 10% weight |
| `consistency_score` | float | | 0-100, higher = more stable |

---

## 4. Scored Combo — ComboScore

Output of `score_combo()`.

| Field | Type | Notes |
|-------|------|-------|
| `bot` | str | |
| `symbol` | str | |
| `timeframe` | str | |
| `variant_id` | str | "baseline" or tuned variant ID |
| `score_total` | float | 0-100 (0 if rejected) |
| `score_breakdown` | dict | sharpe_raw, return_raw, drawdown_raw, confidence_raw, penalties |
| `rejected` | bool | True if any hard gate failed |
| `rejection_reasons` | list[str] | Human-readable gate failure messages |
| `oos_sharpe` | float | Input to scoring |
| `oos_return_pct` | float | Input to scoring |
| `max_drawdown_pct` | float | Input to scoring |
| `total_trades` | int | Input to hard gate |
| `exposure_time_pct` | float | Input to hard gate |
| `folds_profitable_pct` | float | Input to hard gate + scoring |
| `sharpe_cv` | float | Input to scoring penalty |
| `trades_per_day` | float | Input to scoring confidence |
| `oos_trades` | int | Input to hard gate |
| `win_rate` | float | Informational |

---

## 5. Portfolio Entry — AllowlistEntry

Final trading allowlist after portfolio construction.

| Field | Type | Notes |
|-------|------|-------|
| `symbol` | str | |
| `bot` | str | |
| `timeframe` | str | |
| `variant_id` | str | |
| `params_override` | dict | Tuned params (empty for baseline) |
| `score_total` | float | From ComboScore |
| `score_breakdown` | dict | From ComboScore |
| `evidence` | dict | WF stats, sweep stats |
| `sharpe` | float \| None | |
| `sortino` | float \| None | |
| `win_rate` | float \| None | |
| `profit_factor` | float \| None | |
| `max_drawdown_pct` | float \| None | |
| `total_trades` | int | |
| `source_run_id` | str \| None | WF or sweep run ID |
| `validated_at` | datetime \| None | |
| `enabled` | bool | |

---

## Scoring Field Mapping

### Hard Gates (`apply_hard_gates`)
| Gate | MetricsSummary Field | Threshold |
|------|---------------------|-----------|
| Max drawdown | `max_drawdown_pct` | ≤ 20% |
| Min trades (sweep) | `total_trades` | ≥ 30 |
| Min trades (OOS) | `oos_trades` | ≥ 10 |
| Exposure range | `exposure_time_pct` | 1-90% |
| Folds profitable | `folds_profitable_pct` | ≥ 50% |
| NaN/Inf check | `oos_sharpe`, `oos_return_pct`, `max_drawdown_pct` | No NaN/Inf |

### Weighted Score (`compute_weighted_score`)
| Component | Weight | Input Field | Normalization |
|-----------|--------|-------------|---------------|
| OOS Sharpe | 45% | `oos_sharpe` | Clamped 0-6 → 0-100 |
| OOS Return | 20% | `oos_return_pct` | Clamped 0-100% |
| Drawdown | 25% | `max_drawdown_pct` | Nonlinear (1 - (dd/20)²), bonus ≤10% |
| Confidence | 10% | `trades_per_day` + `folds_profitable_pct` | Normalized, CV penalty |

### Stability Penalties
| Condition | Penalty |
|-----------|---------|
| `sharpe_cv > 0.75` | Up to -15 points |
| `folds_profitable_pct < 60%` | Up to -8 points |
