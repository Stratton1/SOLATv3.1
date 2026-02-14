# SOLAT Tuning Pipeline V1

## Overview

The tuning pipeline takes raw sweep results and produces a diversified, risk-constrained portfolio of 20-25 bot-instances. It operates in four stages:

```
Sweep (baseline) -> Tune (Optuna variants) -> Score (0-100) -> Portfolio (diversified)
```

Each stage writes its own artefacts so any step can be re-run independently.

## Architecture

```
engine/solat_engine/
  optimization/
    search_space.py     # Per-bot Optuna search spaces + param conversion
    scoring.py          # Hard gates + weighted 0-100 scorer
    portfolio_builder.py # Diversified portfolio builder
    tuner.py            # 2-stage Optuna param tuner
    models.py           # AllowlistEntry (extended with variant_id, score, evidence)
  backtest/
    models.py           # BacktestRequest.params_override, MetricsSummary extended fields
    engine.py           # Threads params_override to strategy factory
    parallel_sweep.py   # 13th arg tuple element for params
    metrics.py          # trades_per_day, equity_peak, best/worst 5
  data/
    ohlcv_validator.py  # OHLCV frame quality checks

scripts/
  run_tuning.py         # Tuning CLI (smoke / single combo / from sweep results)
  build_portfolio.py    # Portfolio builder CLI

tests/
  test_tuning_pipeline.py  # 70 tests covering entire pipeline
```

## Stage 1: Baseline Sweep

Run the existing parallel sweep to establish baseline performance for all bot/symbol/timeframe combos:

```bash
python3 scripts/run_grand_sweep.py \
  --workers 6 \
  --asset-classes fx \
  --timeframes 1h 4h
```

Output: `data/sweep_results/sweep_{timestamp}/ranked.csv`

## Stage 2: Parameter Tuning

The tuner runs a 2-stage Optuna optimization for each passing combo:

### Stage 1 (Fast Screen): 40 TPE Trials
- Each trial suggests params from the bot's search space
- Runs a single-period backtest with those params
- Scores via `score_combo()` as a proxy objective
- Optuna TPE (Tree-structured Parzen Estimator) guides the search

### Stage 2 (WF Validation): Top 5 -> Walk-Forward
- Top 5 trial params go through walk-forward with N folds
- Full OOS metrics computed for each
- **tunedA** = highest `score_total`
- **tunedB** = lowest `max_drawdown_pct` among top scorers

### CLI Usage

```bash
# Smoke test (1 combo, 5 trials, 3 folds)
python3 scripts/run_tuning.py --smoke

# Tune a specific combo
python3 scripts/run_tuning.py \
  --bot CloudTwist \
  --symbol USDJPY \
  --timeframe 4h \
  --trials 40 \
  --wf-folds 5

# Tune top combos from sweep results
python3 scripts/run_tuning.py \
  --sweep-results data/sweep_results/sweep_live_*/ranked.csv \
  --top-n 20 \
  --trials 40
```

### Output

```
data/tuning/{run_id}/
  tuning_summary.json   # Per-combo TuningResult
  scored_combos.json    # All combos (baseline + variants) with 0-100 scores
```

### Search Spaces Per Bot

| Bot | Params Tuned | Ranges |
|-----|-------------|--------|
| TKCrossSniper | cooldown_bars, breakout_atr_mult, cloud_clear_atr_mult | [3,12], [0.2,1.0], [0.1,0.8] |
| KumoBreaker | cooldown_bars, breakout_atr_mult, breakout_retest_enabled, retest_tolerance_atr_mult | [3,12], [0.2,1.0], bool, [0.05,0.5] |
| ChikouConfirmer | cooldown_bars | [2,10] |
| KijunBouncer | cooldown_bars, impulse_atr_mult, kijun_touch_tolerance | [4,16], [1.0,4.0], [0.0003,0.003] |
| CloudTwist | cooldown_bars, breakout_atr_mult | [4,16], [0.1,0.8] |
| MomentumRider | cooldown_bars | [3,12] |
| TrendSurfer | cooldown_bars, pullback_entry_enabled | [3,12], bool |
| ReversalHunter | cooldown_bars, explosive_atr_pct_block | [5,20], [0.003,0.012] |
| ChikouKaizen | cooldown_bars, displacement, sl_atr_mult, tp_atr_mult | [3,12], [20,35], [0.5,2.5], [1.0,4.0] |

All bots also inherit `BaseHardeningParams` (cooldown_bars, breakout_atr_mult).

## Stage 3: Scoring

### Hard Gates (Auto-Reject)

Any combo failing a gate gets `score_total = 0` and `rejected = True`:

| Gate | Threshold | Rationale |
|------|-----------|-----------|
| Max Drawdown | > 20% | Capital preservation |
| Min Trades (sweep) | < 30 | Statistical significance |
| Min Trades (OOS) | < 10 | OOS significance |
| Exposure | < 1% or > 90% | Inactive or over-leveraged |
| Folds Profitable | < 50% | Consistency across regimes |
| NaN/Inf | Any critical field | Data integrity |

### Weighted Score (0-100)

| Component | Weight | Formula | Clamp |
|-----------|--------|---------|-------|
| OOS Sharpe | 45% | `sharpe / 6.0 * 100` | [0, 6.0] |
| OOS Return | 20% | `return_pct` (after scaling) | [0%, 100%] |
| Drawdown | 25% | `(1 - (dd/20)^2) * 100` | [0%, 20%] |
| Trade Confidence | 10% | `(0.5*tpd_norm + 0.5*folds) * 100 * (1-cv_pen)` | n/a |

**Drawdown bonus**: If DD <= 10%, score gets a 10% bonus (capped at 100).

**Stability penalties** (deducted from total):
- Sharpe CV > 0.75: up to -15 points
- Folds profitable < 60%: up to -8 points

### Worked Example

```
CloudTwist/USDJPY/4h baseline:
  oos_sharpe = 4.2  -> sharpe_score = 4.2/6.0 * 100 = 70.0
  oos_return = 0.35  -> return_score = 35.0
  max_drawdown = 0.08 -> dd_score = (1-(8/20)^2)*100 = 84.0, bonus -> 92.4
  trades_per_day = 1.5, folds_pct = 0.80, sharpe_cv = 0.40

  Weighted = 0.45*70 + 0.20*35 + 0.25*92.4 + 0.10*conf
           = 31.5 + 7.0 + 23.1 + conf
           ~ 65-70 (depending on confidence component)

  No penalties (CV < 0.75, folds > 0.60)
  Final score: ~67
```

## Stage 4: Portfolio Construction

### Constraints

| Constraint | Default | Rationale |
|-----------|---------|-----------|
| Max Slots | 25 | Capital concentration |
| Min Slots | 15 | Diversification floor |
| Max Per Symbol | 2 | Single-instrument risk |
| Max Per Bot Family | 6 | Strategy concentration |
| Max Per Timeframe | 10 | TF balance |
| Max Per Currency | 8 | FX exposure buckets |
| Min Score | 40.0 | Quality floor |
| Risk Per Trade | 1.0% | Position sizing |
| Max Concurrent Risk | 10.0% | Portfolio-level risk |

**Bot family**: All variants of the same bot count together (CloudTwist baseline + tunedA + tunedB = 3 slots toward the 6-slot cap).

**Currency buckets**: Each FX pair exposes two currencies (e.g. EURUSD -> EUR + USD). The cap prevents over-concentration in any single currency.

### Algorithm

1. Sort all non-rejected combos by `score_total` descending
2. Greedily add each combo if it doesn't violate any constraint
3. Track distributions: symbol, bot family, timeframe, currency
4. Stop when `max_slots` reached or candidates exhausted

### CLI Usage

```bash
# Build portfolio from scored combos
python3 scripts/build_portfolio.py \
  --scored data/tuning/{run_id}/scored_combos.json

# Build and write allowlist (ready for POST to /execution/allowlist)
python3 scripts/build_portfolio.py \
  --scored data/tuning/{run_id}/scored_combos.json \
  --apply-allowlist

# Custom constraints
python3 scripts/build_portfolio.py \
  --scored data/tuning/{run_id}/scored_combos.json \
  --max-slots 20 \
  --min-score 50 \
  --max-per-symbol 3 \
  --max-per-bot 4 \
  --risk-per-trade 0.5
```

### Output

```
data/portfolio/{run_id}/
  portfolio.json        # Full portfolio with slots, distributions, constraints
  PORTFOLIO_REPORT.md   # Human-readable summary table
  allowlist.json        # (if --apply-allowlist) Ready for execution system
```

The `allowlist.json` is also written to `data/allowlist.json` (standard location) when `--apply-allowlist` is used.

## Full Pipeline Example

```bash
# 1. Run baseline sweep
python3 scripts/run_grand_sweep.py --workers 6 --asset-classes fx --timeframes 1h 4h

# 2. Tune top combos
python3 scripts/run_tuning.py \
  --sweep-results data/sweep_results/sweep_*/ranked.csv \
  --top-n 30 --trials 40 --wf-folds 5

# 3. Build portfolio
python3 scripts/build_portfolio.py \
  --scored data/tuning/*/scored_combos.json \
  --apply-allowlist

# 4. Review
cat data/portfolio/*/PORTFOLIO_REPORT.md
```

## Data Flow

```
ranked.csv (sweep)
  |
  v
ParamTuner.tune_combo()
  |-- Stage 1: 40 Optuna trials -> proxy scores
  |-- Stage 2: Top 5 -> WF validation
  |
  v
scored_combos.json (baseline + tunedA + tunedB per combo)
  |
  v
PortfolioBuilder.build()
  |-- Sort by score
  |-- Apply constraints (symbol, bot family, TF, currency)
  |
  v
portfolio.json + allowlist.json
```

## Params Passthrough

The `params_override` field flows through the entire stack:

1. `BacktestRequest.params_override: dict[str, dict]` — bot name -> param dict
2. `BacktestEngineV1` — lazy-imports `dict_to_params()`, creates strategy with custom params
3. `ParallelSweepRunner` — 13th element in work tuple, forwarded to BacktestRequest
4. `AllowlistEntry.params_override` — persisted for execution system consumption

**Lazy import pattern**: `dict_to_params` is imported inside the engine's strategy loop (not at module level) to avoid circular imports: `engine.py -> optimization -> walk_forward -> engine.py`.

## Troubleshooting

### No combos pass hard gates
- Lower `min_trades_sweep` if bots generate few trades on your data
- Check data quality — run `validate_ohlcv_frame()` on your bars
- ChikouConfirmer and ReversalHunter are known to produce 0 trades on some data

### Scoring seems off
- Check decimal vs percentage: `oos_return_pct` uses decimal convention (0.1 = 10%)
- The scorer auto-detects: values < 2.0 are treated as decimal, >= 2.0 as percentage
- Same for `max_drawdown_pct`: < 1.0 is decimal, >= 1.0 is percentage

### Tuner takes too long
- Use `--trials 20` for faster iteration
- Use `--smoke` mode (5 trials, 3 folds) for pipeline verification
- Each combo takes ~2-5 min with 40 trials (depends on data length)

### Portfolio too concentrated
- Increase `max_per_currency` if FX-only
- Increase `max_per_bot_family` if fewer bots pass gates
- Lower `min_score` to admit more candidates

## Testing

```bash
# Run pipeline tests only (70 tests, <1s)
cd engine && python3 -m pytest tests/test_tuning_pipeline.py -v

# Run full suite (819 tests)
cd engine && python3 -m pytest tests/ -v
```

Test coverage includes:
- OHLCV validation (NaN, Inf, timestamps, violations, empty)
- Scoring gates (DD, trades, exposure, NaN, all-pass)
- Scoring weights (perfect, clamp, bonus, penalties, range, combos)
- Portfolio builder (sort, caps, currency, variants, allowlist, report)
- Params passthrough (request, factory, extended fields)
- Search spaces (roundtrip for all 9 bots, defaults, custom, unknown)
- AllowlistEntry extensions (defaults, combo_id, serialization)
- FX currency exposure (pairs mapped, tuple structure)
- Integration smoke (score->portfolio, params->factory->strategy, determinism)
