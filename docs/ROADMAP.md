# SOLAT Project Roadmap

**Version:** 3.1.0
**Status:** Finalizing for LIVE trading.

This document outlines the development roadmap for SOLAT, from the immediate tasks required to go live with v3.1 to future feature enhancements and architectural goals.

---

## 🎯 Current Milestone: v3.1 Go-Live

**Objective:** To safely and successfully deploy the SOLAT v3.1 trading engine to a live environment with the IG broker. This milestone is focused on testing, validation, and risk management.

### Suggested Timeline

| Day | Phase | Focus |
|-----|-------|-------|
| 1 | 1, 2 | Fix tests, Complete IG epics |
| 2 | 3, 4 | Data quality, Run backtests |
| 3 | 5 | Walk-forward optimization |
| 4-5 | 6 | Paper trading (48h) |
| 6 | 7, 8 | Risk controls, Final checklist |
| 7 | GO LIVE | Start with minimum sizes |

### PHASE 1: FIX TEST SUITE 🔧
**Priority:** CRITICAL | **Status:** In Progress

*Tasks:*
- [ ] 1.1 Create test fixture helper module with `app.dependency_overrides` pattern.
- [ ] 1.2 Migrate `test_ig_endpoints.py` to new DI pattern.
- [ ] 1.3 Migrate `test_execution_*.py` to new DI pattern.
- [ ] 1.4 Migrate `test_market_data_*.py` to new DI pattern.
- [ ] 1.5 Migrate `test_catalog.py` to new DI pattern.
- [ ] 1.6 Run full test suite: `pytest --tb=short`.
- [ ] 1.7 Verify all 57 tests pass.

### PHASE 2: COMPLETE IG LIVE EPIC MAPPING 🗺️
**Priority:** HIGH | **Status:** Not Started

*Tasks:*
- [ ] 2.1 Document all LIVE vs DEMO epic differences.
- [ ] 2.2 Add remaining `live_epic` values to `seed.py` (currently only 3 pairs done).
- [ ] 2.3 Update catalog bootstrap to use `live_epic` when `IG_ACC_TYPE=LIVE`.
- [ ] 2.4 Test catalog bootstrap with LIVE account.
- [ ] 2.5 Verify all 10 forex pairs have correct LIVE epics.

### PHASE 3: VALIDATE HISTORICAL DATA QUALITY 📈
**Priority:** MEDIUM | **Status:** Not Started

*Tasks:*
- [ ] 3.1 Run data quality checker: `python scripts/check_data_quality.py --timeframe 1h`.
- [ ] 3.2 Review any OHLC validation errors.
- [ ] 3.3 Check for excessive gaps in major pairs.
- [ ] 3.4 Verify date ranges are consistent (2020-2025).
- [ ] 3.5 Spot-check 3 random instruments manually.

### PHASE 4: RUN FULL BACKTEST SUITE 🧪
**Priority:** HIGH | **Status:** Not Started

*Tasks:*
- [ ] 4.1 Start engine: `pnpm dev:engine`.
- [ ] 4.2 Run single bot backtest on EURUSD (sanity check).
- [ ] 4.3 Run all 8 Elite bots on EURUSD 1h (2023-2024).
- [ ] 4.4 Run Grand Sweep: All bots × Top 5 pairs × 1h timeframe.
- [ ] 4.5 Review top performers (Sharpe > 1.5, Win Rate > 50%).
- [ ] 4.6 Identify best 2-3 bot/symbol combinations for LIVE.

*Example API Calls:*
```bash
# Single backtest
curl -X POST http://127.0.0.1:8765/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["EURUSD"],
    "timeframe": "1h",
    "start": "2023-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z",
    "bots": ["TKCrossSniper", "MomentumRider"],
    "initial_cash": 10000
  }'

# Grand Sweep
curl -X POST http://127.0.0.1:8765/backtest/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "bots": ["TKCrossSniper", "KumoBreaker", "MomentumRider", "TrendSurfer"],
    "symbols": ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "AUDUSD"],
    "timeframes": ["1h"],
    "start": "2023-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z"
  }'
```

### PHASE 5: WALK-FORWARD OPTIMIZATION 🔄
**Priority:** MEDIUM | **Status:** Not Started

*Tasks:*
- [ ] 5.1 Verify walk-forward bug fix works (`combined_metrics`).
- [ ] 5.2 Configure and run walk-forward on top 3 bot/symbol combinations.
- [ ] 5.3 Analyze out-of-sample performance degradation.
- [ ] 5.4 Select final bot/symbol/params for LIVE.

### PHASE 6: PAPER TRADING VALIDATION 📝
**Priority:** HIGH | **Status:** Not Started

*Tasks:*
- [ ] 6.1 Configure engine for PAPER mode with LIVE data feed.
- [ ] 6.2 Run selected bot for 24-48 hours.
- [ ] 6.3 Monitor via WebSocket events and logs.
- [ ] 6.4 Verify order generation matches backtest signals.
- [ ] 6.5 Check for any API errors or connectivity issues.
- [ ] 6.6 Review paper trades against backtest expectations.

### PHASE 7: RISK CONTROLS & KILL SWITCH ⚠️
**Priority:** CRITICAL | **Status:** Not Started

*Tasks:*
- [ ] 7.1 Audit kill switch implementation.
- [ ] 7.2 Configure and document all risk parameters (`MAX_DAILY_LOSS_PCT`, etc.).
- [ ] 7.3 Test kill switch activation manually.
- [ ] 7.4 Verify kill switch blocks new orders and closes positions.
- [ ] 7.5 Document kill switch reset procedure.

*Example Risk Configuration:*
```python
risk_config = RiskConfig(
    sizing_method=SizingMethod.RISK_PER_TRADE,
    risk_per_trade_pct=0.5,  # 0.5% per trade
    max_open_positions=3,
    max_exposure_per_symbol=10000,  # £10k max per symbol
    max_total_exposure=30000,  # £30k total
)
```

### PHASE 8: GO-LIVE CHECKLIST ✅
**Priority:** CRITICAL | **Status:** Not Started

*Critical Reminders:*
1. **NEVER skip paper trading** - Even 24h reveals issues.
2. **Start with minimum position sizes** - Scale up after 1 week.
3. **Keep kill switch tested** - Test it monthly.
4. **Monitor daily** - At least for the first 2 weeks.
5. **Document everything** - It helps debug issues later.

*Pre-Launch Tasks:*
- [ ] 8.1 All tests passing.
- [ ] 8.2 Backtest results reviewed and documented.
- [ ] 8.3 Walk-forward validation complete.
- [ ] 8.4 Paper trading successful (48h minimum).
- [ ] 8.5 Risk parameters configured and verified.
- [ ] 8.6 Kill switch tested and working.
- [ ] 8.7 IG LIVE credentials verified.
- [ ] 8.8 Starting capital decided and funded.

*Launch Day Tasks:*
- [ ] 8.9 Set `SOLAT_MODE=LIVE` in `.env`.
- [ ] 8.10 Start with MINIMUM position sizes.
- [ ] 8.11 Monitor first 3 trades closely.
- [ ] 8.12 Keep kill switch easily accessible.

---

## 🚀 Future Milestones (Post v3.1)

This section outlines planned features and improvements for future versions of SOLAT.

### v3.2 - Stability & Observability
*Objective: Enhance system monitoring, performance, and reliability.*

- **Enhanced UI Dashboard:**
  - [ ] Add real-time performance metrics (Sharpe, Sortino, Max Drawdown).
  - [ ] Visualize equity curve and daily P/L.
  - [ ] Display detailed trade history and analytics.
- **Advanced Monitoring:**
  - [ ] Integrate with Sentry for real-time error tracking.
  - [ ] Add Prometheus/Grafana for system-level metrics (CPU, memory, API latency).
- **Performance Tuning:**
  - [ ] Optimize historical data queries for faster backtests.
  - [ ] Profile and optimize hot paths in the trading engine.

### v3.3 - Broker & Strategy Expansion
*Objective: Increase the platform's versatility by adding more brokers and strategy development capabilities.*

- **Multi-Broker Support:**
  - [ ] Refactor broker client into a generic interface.
  - [ ] Add support for a second broker (e.g., Alpaca for equities, Interactive Brokers for futures).
- **Strategy SDK:**
  - [ ] Develop a "Strategy SDK" to simplify the creation and testing of new bots.
  - [ ] Add support for community-contributed strategies.
- **Advanced Analytics:**
  - [ ] Implement Monte Carlo simulations for portfolio-level risk analysis.
  - [ ] Add tooling for analyzing parameter sensitivity.

### v4.0 - Architectural Evolution
*Objective: Evolve the architecture to support greater scale, complexity, and intelligence.*

- **Machine Learning Integration:**
  - [ ] Research and implement ML models for signal filtering or regime detection.
  - [ ] Build a pipeline for training, validating, and deploying ML models.
- **Event-Sourced Architecture:**
  - [ ] Explore migrating the trade ledger to an event-sourcing model for a perfect audit trail.
- **Cloud-Native Backtesting:**
  - [ ] Design a system to run large-scale backtest sweeps on cloud services (e.g., AWS Batch, Google Cloud Run) for massive parallelization.

---

## 🚨 Emergency Procedures

*This section is a critical reference and should be kept up-to-date.*

### If things go wrong:
1. **Activate kill switch**: `curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate -H "Content-Type: application/json" -d '{"reason":"emergency"}'`
2. **Check IG platform directly**: Manually close positions if necessary.
3. **Stop engine**: `Ctrl+C` in the terminal or `kill <PID>`.
4. **Review logs**: `tail -f engine/logs/solat.log`

### If credentials are exposed:
1. **Immediately** revoke the exposed credentials in the IG settings.
2. Generate new API keys and rotate all related passwords.
3. Audit recent account activity for any unauthorized actions.
4. Update credentials in your secure `.env` file.

### IG Support:
- **UK:** 0800 409 6789
- **International:** +44 20 7896 0011
- **Platform:** https://www.ig.com/uk