---
name: solat-strategy-elite8
description: Template and checklist for adding or modifying Elite 8 strategies. Use when the user says add a strategy, add a new Elite 8 bot, or when editing strategies/elite8.py or strategies/indicators.py. Returns class skeleton, indicator usage, and integration steps.
---

# SOLAT Strategy (Elite 8) Agent

When the user asks to **add a strategy**, **add a new Elite 8 bot**, or when editing `engine/solat_engine/strategies/elite8.py` or `strategies/indicators.py`, provide a **class skeleton**, **indicator usage**, and **integration steps**. Enforce: BarData, SignalIntent, no lookahead, shared indicators, reason codes.

## Key types and locations

- **Base class:** `Elite8BaseStrategy` in `engine/solat_engine/strategies/elite8.py`.
- **Bar data:** `BarData` (dataclass: timestamp, open, high, low, close, volume) in elite8.py.
- **Signal:** `SignalIntent` from `solat_engine.backtest.models` (direction, sl, tp, reason_codes, etc.).
- **Indicators:** `engine/solat_engine/strategies/indicators.py` — ema, rsi, macd, atr, ichimoku, crossover, crossunder, is_price_above_cloud, is_price_below_cloud, etc.

## Contract

- **name:** property, str (e.g. `"TKCrossSniper"`).
- **description:** property, str (one-line human-readable).
- **generate_signal(self, bars: Sequence[BarData], current_position: str | None) -> SignalIntent:**  
  - `bars` = historical bars up to current (inclusive).  
  - `current_position` = `"long"`, `"short"`, or `None`.  
  - Return SignalIntent with direction (BUY/SELL/HOLD), optional sl/tp, and reason_codes (list of str).

## Rules

1. **Use BarData** — Do not introduce a different bar type; use the existing BarData dataclass.
2. **Return SignalIntent** — Use the existing model; include reason_codes for every signal.
3. **No lookahead** — Only use bars[0:idx+1] conceptually; never access future bars.
4. **Use shared indicators** — Import from `solat_engine.strategies.indicators`; do not reimplement.
5. **Warmup** — Respect `self.warmup_bars`; return HOLD with reason_codes like `["warmup"]` until enough bars.
6. **SL/TP** — Use `_calculate_sl_tp(entry_price, atr_value, is_long, ...)` or equivalent; pass sl/tp in SignalIntent when opening.

## Class skeleton (template)

```python
class MyNewStrategy(Elite8BaseStrategy):
    @property
    def name(self) -> str:
        return "MyNewStrategy"

    @property
    def description(self) -> str:
        return "One-line description."

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])
        # Use indicators on bars; no lookahead
        # Return SignalIntent(direction="BUY"|"SELL"|"HOLD", sl=..., tp=..., reason_codes=[...])
```

## Integration steps

1. Add the class in `engine/solat_engine/strategies/elite8.py` (with other Elite 8 implementations).
2. Register in `get_available_bots()` (or equivalent registry) so the strategy is selectable by name.
3. Add unit tests (e.g. golden bars → expected SignalIntent) in `engine/tests/` if required by project.
4. Document reason_codes used (for audit and UI).

## Output

For “add a strategy” or “add Elite 8 bot”: provide (1) class skeleton with name/description/generate_signal and indicator usage, (2) list of reason_codes to use, (3) integration steps (file, registry, tests). For “modify strategy”: identify the class and method, then suggest changes that keep BarData/SignalIntent and no-lookahead.
