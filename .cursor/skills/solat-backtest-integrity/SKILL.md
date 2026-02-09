---
name: solat-backtest-integrity
description: Checks backtest and strategy code for lookahead and non-determinism. Use when reviewing backtest code, adding a new strategy, or editing engine/solat_engine/backtest/ or strategies/. Returns pass/fail and list of risks.
---

# SOLAT Backtest Integrity Agent

When the user asks to **review backtest code**, **add a new strategy**, or when editing `engine/solat_engine/backtest/` or `engine/solat_engine/strategies/`, run this checklist and report **pass/fail** plus any **lookahead or non-determinism risks**.

## Entry points

- **Backtest engine:** `engine/solat_engine/backtest/engine.py` — BacktestEngineV1, bar feed, single-pass iteration.
- **Broker sim:** `engine/solat_engine/backtest/broker_sim.py` — Fills based only on past/current bars.
- **Strategies:** `engine/solat_engine/strategies/elite8.py` — Elite8BaseStrategy, generate_signal(bars, current_position).

## Checklist

### 1. No lookahead (future data)

- [ ] **Bar iteration:** Bar feed is time-ordered and single-pass; no access to bars after current time.
- [ ] **Strategy:** Strategy receives only `bars` up to and including current bar; no `bars[i+1]`, no `df.shift(-1)`, no indexing beyond `len(bars)-1`.
- [ ] **BrokerSim:** Fill decisions use only past/current bar prices and state; no future OHLC.
- [ ] **Indicators:** Indicator functions use only past/current values; no forward-looking series.

### 2. No hidden randomness

- [ ] **Random seeds:** If any randomness (e.g. slippage model), seed is fixed and documented.
- [ ] **Order of iteration:** Multi-symbol or multi-strategy order is deterministic (e.g. defined sequence, no set/dict iteration for bar order).

### 3. Common lookahead patterns to flag

- `bars[i+1]`, `bars[idx + 1]`, any index beyond current.
- `df.shift(-1)`, `df.lead()`, or equivalent “next row” access.
- Using “close” of current bar before it is “final” in the bar feed (ensure bar is complete before strategy sees it).
- Caching or reusing data that implicitly includes future information.

### 4. Determinism

- [ ] Same inputs (bars, config, strategy) produce same outputs (signals, fills, metrics).
- [ ] No reliance on system time for bar logic (use bar timestamp only).
- [ ] No unseeded random in fill model or strategy.

## Output format

1. **Pass / Fail** — Overall: does the code respect no-lookahead and determinism?
2. **Risks** — List each potential lookahead or non-determinism issue with file/line or snippet reference.
3. **Suggestions** — Concrete fix (e.g. “Use only bars[0:idx+1]”, “Fix random seed in BrokerSim”).

If the user provides a code snippet or file, apply the checklist to it. If they only say “review backtest” or “add strategy”, remind them of this checklist and that generate_signal must use only past/current bars.
