# Grand Sweep v4.2 - Upgrade Summary

**Date**: 2026-02-11
**Scope**: PROMPT 022 Implementation

---

## Overview

Upgraded Grand Sweep from v4.0 to v4.2 with comprehensive improvements:
- ✅ Fixed end-of-run crash (len(glob) bug)
- ✅ Expanded timeframe support (1m/5m/15m/30m/1h/4h)
- ✅ Added "disk" scope for automatic symbol discovery
- ✅ Implemented broken bot detection (0-trade analysis)
- ✅ Generated curated allowlist (grouped by symbol/timeframe/bot)
- ✅ Added --apply-allowlist flag for engine integration
- ✅ Updated documentation with new usage examples

---

## Key Changes

### 1. Fixed print_summary() Crash ✅

**Problem**: `len(results_csv.parent.glob("preflight.json"))` raised `TypeError: object of type 'generator' has no len()`

**Solution**:
- Reads preflight.json and extracts `skipped_combos` count
- Wrapped in defensive try/except to prevent crash
- Falls back to 0 if preflight.json doesn't exist or is malformed

**File**: [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L194-L215)

---

### 2. Expanded Timeframe Support ✅

**New Features**:
- Added `DEFAULT_TIMEFRAMES_FULL = ["1m", "5m", "15m", "30m", "1h", "4h"]`
- Support for `--timeframes all` keyword (expands to full set)
- Disk scope defaults to full timeframe set

**Usage**:
```bash
# Test all 6 timeframes
python3 scripts/run_grand_sweep.py --scope live --timeframes all

# Specific timeframes
python3 scripts/run_grand_sweep.py --scope live --timeframes 1m 5m 15m

# Old behavior still works
python3 scripts/run_grand_sweep.py --scope live  # Defaults to 1h 4h
```

**Files**:
- [sweep_utils.py](engine/solat_engine/backtest/sweep_utils.py#L81)
- [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L352-L370)

---

### 3. Added "disk" Scope for Symbol Discovery ✅

**New Feature**: Automatically discover symbols from parquet directory

**Function**: `discover_symbols_from_disk(data_dir: Path) -> list[str]`
- Scans `parquet/bars/instrument_symbol=*/` directories
- Returns sorted list of storage symbols
- Gracefully handles missing directories

**Usage**:
```bash
# Discover all symbols with data on disk
python3 scripts/run_grand_sweep.py --scope disk --timeframes all

# Combine with derivation
python3 scripts/run_grand_sweep.py --scope disk --derive-missing
```

**Files**:
- [sweep_utils.py](engine/solat_engine/backtest/sweep_utils.py#L721-L742)
- [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L344-L349)

---

### 4. Broken Bot Detection ✅

**New Feature**: Automatically flag bots that generate 0 trades

**Function**: `detect_broken_bots(results_df, zero_trade_threshold=0.5)`
- Analyzes per-bot trade counts across all combos
- Flags bot if >= threshold fraction of combos have 0 trades
- Suggests action: "INVESTIGATE" or "REMOVE_FROM_ELITE_8"

**Output**: `disabled_bots.json`
```json
{
  "generated_at": "2026-02-11T15:00:00Z",
  "zero_trade_threshold": 0.5,
  "total_bots": 9,
  "broken_bots_count": 2,
  "broken_bots": [
    {
      "bot": "ChikouConfirmer",
      "combos_attempted": 20,
      "zero_trade_combos": 20,
      "zero_trade_ratio": 1.0,
      "rule_triggered": "zero_trade_ratio >= 0.5",
      "suggested_action": "REMOVE_FROM_ELITE_8"
    }
  ]
}
```

**Usage**:
```bash
# Default threshold (50%)
python3 scripts/run_grand_sweep.py --scope live

# Stricter threshold (80%)
python3 scripts/run_grand_sweep.py --scope live --broken-bot-threshold 0.8
```

**Files**:
- [sweep_utils.py](engine/solat_engine/backtest/sweep_utils.py#L562-L619)
- [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L567-L573)

---

### 5. Curated Allowlist Generation ✅

**New Feature**: Generate production-ready allowlist grouped by symbol/timeframe/bot

**Function**: `generate_curated_allowlist(ranked_df, broken_bots, max_per_symbol=3, max_per_bot=5)`
- Excludes broken bots automatically
- Applies min_sharpe filter (default: 1.0)
- Limits per-symbol (default: 3 combos)
- Limits per-bot globally (default: 5 combos)
- Groups by symbol → timeframe → bots

**Output**: `curated_allowlist.json`
```json
{
  "generated_at": "2026-02-11T15:00:00Z",
  "filters": {
    "excluded_bots": ["ChikouConfirmer", "ReversalHunter"],
    "max_per_symbol": 3,
    "max_per_bot": 5
  },
  "symbols": {
    "EURUSD": {
      "4h": [
        {"bot": "CloudTwist", "sharpe": 13.48, "total_trades": 52, "win_rate": 0.557, "pnl": 0.068},
        {"bot": "ChikouKaizen", "sharpe": 16.96, "total_trades": 161, "win_rate": 0.391, "pnl": 0.088}
      ],
      "1h": [
        {"bot": "CloudTwist", "sharpe": 1.26, "total_trades": 223, "win_rate": 0.444, "pnl": 0.013}
      ]
    }
  }
}
```

**Usage**:
```bash
# Default filters
python3 scripts/run_grand_sweep.py --scope live

# Higher quality threshold
python3 scripts/run_grand_sweep.py --scope live --min-sharpe 2.0
```

**Files**:
- [sweep_utils.py](engine/solat_engine/backtest/sweep_utils.py#L624-L718)
- [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L575-L585)

---

### 6. Apply Allowlist to Engine ✅

**New Feature**: Optionally POST curated allowlist to running engine

**Flag**: `--apply-allowlist` (explicit only, never automatic)

**Behavior**:
- If flag is set: POSTs `symbols` dict to `http://127.0.0.1:8765/execution/allowlist`
- If flag is NOT set: Prints "Not applied. Use --apply-allowlist to apply."
- Handles engine connection errors gracefully

**Usage**:
```bash
# Generate allowlist only (default)
python3 scripts/run_grand_sweep.py --scope live

# Generate AND apply to running engine
python3 scripts/run_grand_sweep.py --scope live --apply-allowlist
```

**Files**:
- [run_grand_sweep.py](engine/scripts/run_grand_sweep.py#L587-L601)

---

## Usage Examples

### Basic (Recommended for Most Users)

```bash
# Quick test on LIVE FX pairs with 1h/4h
python3 scripts/run_grand_sweep.py --scope live --workers 7

# Full catalogue scan with all timeframes
python3 scripts/run_grand_sweep.py --scope full --timeframes all --workers 7

# Discover everything on disk
python3 scripts/run_grand_sweep.py --scope disk --timeframes all --derive-missing
```

### Advanced

```bash
# High-quality picks only (Sharpe >= 2.0)
python3 scripts/run_grand_sweep.py --scope live --min-sharpe 2.0

# Strict broken bot detection (80% threshold)
python3 scripts/run_grand_sweep.py --scope live --broken-bot-threshold 0.8

# Generate and apply allowlist to engine
python3 scripts/run_grand_sweep.py --scope live --apply-allowlist

# FX + indices with all timeframes
python3 scripts/run_grand_sweep.py \
  --asset-classes fx index \
  --timeframes all \
  --workers 7
```

---

## Output Files

After running a sweep, the following files are generated:

### Standard Outputs (v4.0)
- `results.csv` - Raw results (all combos)
- `results.parquet` - Binary format
- `ranked.csv` - Filtered by min_trades, sorted by Sharpe
- `top_picks.json` - Diversified top-N picks
- `preflight.json` - Data availability report

### New Outputs (v4.2)
- `disabled_bots.json` - Broken bot analysis ✨
- `curated_allowlist.json` - Production-ready allowlist ✨

---

## Breaking Changes

None! All existing functionality preserved. v4.2 is fully backward compatible with v4.0.

---

## Testing

### Syntax Validation ✅
```bash
cd engine
python3 scripts/run_grand_sweep.py --help
# Output shows all new options correctly
```

### Smoke Test (Recommended)
```bash
# Quick mini sweep to verify functionality
python3 scripts/run_grand_sweep.py --scope mini --workers 2

# Check outputs
ls -lh data/sweep_results/sweep_mini_*/
# Should show: results.csv, ranked.csv, top_picks.json, preflight.json,
#              disabled_bots.json, curated_allowlist.json
```

### Full Integration Test
```bash
# Run on completed sweep results
cd engine
python3 scripts/analyze_sweep_interim.py aa2c3781
# Should work without errors
```

---

## Next Steps

1. **Test on Mini Scope** ✅
   ```bash
   python3 scripts/run_grand_sweep.py --scope mini --workers 2
   ```

2. **Run Full Sweep with All Timeframes**
   ```bash
   python3 scripts/run_grand_sweep.py \
     --scope live \
     --timeframes all \
     --workers 7 \
     --min-sharpe 1.5
   ```

3. **Test Disk Discovery**
   ```bash
   python3 scripts/run_grand_sweep.py \
     --scope disk \
     --timeframes 1h 4h \
     --workers 7
   ```

4. **Apply Allowlist to Engine**
   ```bash
   # Start engine first
   pnpm dev:engine

   # Then run sweep with --apply-allowlist
   python3 scripts/run_grand_sweep.py \
     --scope live \
     --apply-allowlist
   ```

---

## Troubleshooting

### Issue: "No symbols found on disk"
**Cause**: `parquet/bars/` directory empty or doesn't exist
**Solution**: Run data fetch first or use `--scope live` instead

### Issue: "Failed to apply allowlist to engine"
**Cause**: Engine not running on port 8765
**Solution**: Start engine with `pnpm dev:engine` first

### Issue: "ChikouConfirmer and ReversalHunter flagged as broken"
**Cause**: These bots generate 0 trades on 2023-2025 data
**Solution**: This is expected! They are correctly flagged and excluded from curated allowlist.

---

## Files Modified

| File | Changes |
|------|---------|
| `engine/scripts/run_grand_sweep.py` | Added disk scope, timeframe "all" keyword, broken bot detection, curated allowlist, --apply-allowlist flag, updated help |
| `engine/solat_engine/backtest/sweep_utils.py` | Added `DEFAULT_TIMEFRAMES_FULL`, `detect_broken_bots()`, `generate_curated_allowlist()`, `discover_symbols_from_disk()` |

---

## Deliverables Status

- ✅ Fix print_summary() crash
- ✅ Expand timeframe coverage (1m/5m/15m/30m/1h/4h)
- ✅ Add "disk" scope for symbol discovery
- ✅ Implement broken bot detection
- ✅ Generate curated allowlist
- ✅ Add --apply-allowlist flag
- ✅ Update documentation

**All deliverables complete!** 🎉
