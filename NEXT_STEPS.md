# SOLATv3.1 - Next Steps Guide

This guide walks you through testing the full flow, building the desktop app, and preparing for LIVE trading.

**Run these commands on your Mac** (requires Python 3.12+ from your existing venv).

---

## Step 1: Start the Engine

```bash
cd /Users/joseph/Projects/SOLAT_ALL/solat_v3.1/engine
source .venv/bin/activate
python -m solat_engine.main
```

Keep this terminal open. You should see:
```
INFO     solat_engine.main:main.py:XX Starting SOLAT Engine v3.1.x
INFO     solat_engine.main:main.py:XX IG credentials: configured
INFO     uvicorn.error:server.py:XX Uvicorn running on http://127.0.0.1:8765
```

---

## Step 2: Bootstrap the Catalog

Open a **new terminal** and run:

```bash
curl -s -X POST "http://127.0.0.1:8765/catalog/bootstrap?enrich=true" | python3 -m json.tool
```

This will:
1. Load seed instruments (28 symbols)
2. Enrich each from IG API (get EPICs, dealing rules)

Expected output:
```json
{
  "ok": true,
  "created": 28,
  "enriched": 28,
  "total": 28,
  "message": "Bootstrap complete: 28 created, 28 enriched"
}
```

---

## Step 3: Sync Historical Data

Quick sync (last 30 days):
```bash
curl -s -X POST "http://127.0.0.1:8765/data/sync/quick?days=30" | python3 -m json.tool
```

This runs in the background. Check progress:
```bash
curl -s "http://127.0.0.1:8765/data/summary" | python3 -m json.tool
```

Wait until you see bars > 0 (may take 5-10 minutes):
```json
{
  "total_symbols": 28,
  "total_bars": 150000
}
```

---

## Step 4: Verify Data with Test Scripts

Run the endpoint verification:
```bash
cd /Users/joseph/Projects/SOLAT_ALL/solat_v3.1
bash scripts/test_endpoints.sh
```

Run the full flow test:
```bash
python scripts/test_full_flow.py
```

Expected: All steps should pass (✓).

---

## Step 5: Run Backtest

Test a single backtest:
```bash
curl -s -X POST "http://127.0.0.1:8765/backtest/run" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["EURUSD"],
    "bots": ["ichimoku_cloud_basic"],
    "timeframe": "1h",
    "start": "2026-01-01T00:00:00Z",
    "end": "2026-02-01T00:00:00Z",
    "initial_cash": 10000
  }' | python3 -m json.tool
```

---

## Step 6: Run Walk-Forward Optimization

```bash
curl -s -X POST "http://127.0.0.1:8765/optimization/walk-forward" \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
    "bots": ["ichimoku_cloud_basic", "ichimoku_tk_cross", "ichimoku_kumo_breakout"],
    "timeframes": ["1h"],
    "start_date": "2025-08-01T00:00:00Z",
    "end_date": "2026-02-01T00:00:00Z",
    "window_type": "rolling",
    "in_sample_days": 60,
    "out_of_sample_days": 30,
    "step_days": 30,
    "optimization_mode": "sharpe",
    "top_n": 5,
    "min_trades": 5
  }' | python3 -m json.tool
```

Check allowlist after optimization:
```bash
curl -s "http://127.0.0.1:8765/optimization/allowlist" | python3 -m json.tool
```

---

## Step 7: Build Desktop App

First, clean up any stale build artifacts:
```bash
cd /Users/joseph/Projects/SOLAT_ALL/solat_v3.1/apps/desktop
rm -rf target
rm -rf node_modules/.cache
```

Install dependencies and build:
```bash
npm install
npm run tauri build
```

The built app will be in:
- macOS: `target/release/bundle/macos/SOLAT.app`
- DMG installer: `target/release/bundle/dmg/SOLAT_x.x.x_aarch64.dmg`

For development testing:
```bash
npm run tauri dev
```

---

## Step 8: DEMO Validation Checklist

Follow the complete checklist in `docs/GO_LIVE_CHECKLIST.md`:

### Quick Summary:

| Phase | What to Check |
|-------|---------------|
| 1. Environment | Engine healthy, app launches |
| 2. IG Connectivity | Login succeeds, market data flows |
| 3. Historical Data | Bars synced, charts render |
| 4. Backtest | Single and multi-symbol tests pass |
| 5. Execution Safety | Gates status, kill switch test |
| 6. Pre-LIVE | Risk limits decided, oversight plan ready |

### Key Commands:

```bash
# Health check
curl http://127.0.0.1:8765/health

# IG login test
curl -X POST http://127.0.0.1:8765/ig/login

# Execution gates
curl http://127.0.0.1:8765/execution/gates

# Kill switch test (DEMO)
curl -X POST http://127.0.0.1:8765/execution/kill-switch/activate \
  -H "Content-Type: application/json" \
  -d '{"reason": "test"}'
```

---

## Step 9: Prepare for LIVE Trading

**ONLY after ALL demo validation passes.**

See `docs/LIVE_RUNBOOK.md` for complete procedures.

### Pre-LIVE Preparation:

1. **Update `.env` for LIVE:**
   ```bash
   # Edit engine/.env
   SOLAT_MODE=LIVE
   LIVE_TRADING_ENABLED=true
   LIVE_ENABLE_TOKEN=<generate-32-char-random-string>
   LIVE_ACCOUNT_ID=<your-ig-live-account-id>

   # Risk limits (adjust for your account)
   LIVE_MAX_ORDER_SIZE=0.5
   MAX_DAILY_LOSS_PCT=2.0
   MAX_CONCURRENT_POSITIONS=3
   PER_SYMBOL_EXPOSURE_CAP=5000
   MAX_TRADES_PER_HOUR=10
   ```

2. **Generate LIVE token:**
   ```bash
   openssl rand -hex 16
   ```

3. **First supervised LIVE session:**
   - Run pre-live check
   - Complete UI confirmation (type "ENABLE LIVE TRADING", paste token)
   - Arm for LIVE
   - **Monitor constantly during first session**
   - Keep IG platform open for manual intervention

---

## Troubleshooting

### "No enriched instruments" error
→ Run catalog bootstrap first (Step 2)

### Data sync fails
→ Check IG credentials in `.env`
→ Verify catalog has enriched instruments

### Backtest shows "no running event loop"
→ Restart the engine

### Tauri build path mismatch
→ Clean target directory: `rm -rf target`
→ Rebuild from fresh

### IG login fails
→ Check `IG_API_KEY`, `IG_USERNAME`, `IG_PASSWORD` in `engine/.env`
→ Restart engine after .env changes

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `engine/.env` | Engine configuration (IG credentials, mode) |
| `engine/.env.example` | Template with all options documented |
| `docs/GO_LIVE_CHECKLIST.md` | DEMO validation checklist |
| `docs/LIVE_RUNBOOK.md` | LIVE trading procedures |
| `scripts/test_full_flow.py` | Integration test script |
| `scripts/test_endpoints.sh` | Quick endpoint verification |

---

**Good luck with your trading system!**
