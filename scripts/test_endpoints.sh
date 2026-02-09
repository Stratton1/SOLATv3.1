#!/bin/bash
# Quick endpoint test using curl
# Run this after starting the engine to verify all endpoints work

BASE_URL="http://127.0.0.1:8765"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo "SOLAT v3.1 Endpoint Verification"
echo "=========================================="
echo ""

# Health check
echo "1. Health Check"
echo "----------------------------------------"
HEALTH=$(curl -s "$BASE_URL/health")
if echo "$HEALTH" | grep -q '"status"'; then
    echo -e "${GREEN}✓ Engine healthy${NC}"
    echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Version: {d.get(\"version\", \"?\")}')" 2>/dev/null || true
else
    echo -e "${RED}✗ Engine not reachable${NC}"
    echo "  Start with: cd engine && python -m solat_engine.main"
    exit 1
fi
echo ""

# Config
echo "2. Config"
echo "----------------------------------------"
CONFIG=$(curl -s "$BASE_URL/config")
if echo "$CONFIG" | grep -q '"mode"'; then
    echo -e "${GREEN}✓ Config OK${NC}"
    echo "$CONFIG" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Mode: {d.get(\"mode\", \"?\")}'); print(f'  IG Configured: {d.get(\"ig_configured\", False)}')" 2>/dev/null || true
else
    echo -e "${RED}✗ Config failed${NC}"
fi
echo ""

# Data summary
echo "3. Data Summary"
echo "----------------------------------------"
DATA=$(curl -s "$BASE_URL/data/summary")
if echo "$DATA" | grep -q '"total_'; then
    echo -e "${GREEN}✓ Data endpoint OK${NC}"
    echo "$DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Symbols: {d.get(\"total_symbols\", 0)}'); print(f'  Bars: {d.get(\"total_bars\", 0):,}')" 2>/dev/null || true
else
    echo -e "${RED}✗ Data summary failed or no data${NC}"
fi
echo ""

# Get bars
echo "4. Get Bars (EURUSD 1h)"
echo "----------------------------------------"
BARS=$(curl -s "$BASE_URL/data/bars?symbol=EURUSD&timeframe=1h&limit=10")
if echo "$BARS" | grep -q '"bars"'; then
    COUNT=$(echo "$BARS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('bars', [])))" 2>/dev/null || echo "0")
    if [ "$COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Got $COUNT bars${NC}"
    else
        echo -e "${RED}✗ No bars returned (need to sync data)${NC}"
    fi
else
    echo -e "${RED}✗ Get bars failed${NC}"
fi
echo ""

# Backtest bots
echo "5. Available Bots"
echo "----------------------------------------"
BOTS=$(curl -s "$BASE_URL/backtest/bots")
if echo "$BOTS" | grep -q '"bots"'; then
    echo -e "${GREEN}✓ Bots endpoint OK${NC}"
    echo "$BOTS" | python3 -c "import sys,json; d=json.load(sys.stdin); bots=d.get('bots',[]); print(f'  {len(bots)} bots available'); [print(f'    - {b.get(\"name\")}') for b in bots[:5]]" 2>/dev/null || true
else
    echo -e "${RED}✗ Bots endpoint failed${NC}"
fi
echo ""

# Execution gates
echo "6. Execution Gates"
echo "----------------------------------------"
GATES=$(curl -s "$BASE_URL/execution/gates")
if echo "$GATES" | grep -q '"mode"'; then
    echo -e "${GREEN}✓ Gates endpoint OK${NC}"
    echo "$GATES" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Mode: {d.get(\"mode\", \"?\")}'); print(f'  Allowed: {d.get(\"allowed\", False)}'); blockers=d.get('blockers',[]); print(f'  Blockers: {len(blockers)}')" 2>/dev/null || true
else
    echo -e "${RED}✗ Gates endpoint failed${NC}"
fi
echo ""

# Optimization allowlist
echo "7. Optimization Allowlist"
echo "----------------------------------------"
ALLOWLIST=$(curl -s "$BASE_URL/optimization/allowlist")
if echo "$ALLOWLIST" | grep -q '"total_entries"'; then
    echo -e "${GREEN}✓ Allowlist endpoint OK${NC}"
    echo "$ALLOWLIST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Total: {d.get(\"total_entries\", 0)}'); print(f'  Enabled: {d.get(\"enabled_entries\", 0)}')" 2>/dev/null || true
else
    echo -e "${RED}✗ Allowlist endpoint failed${NC}"
fi
echo ""

# Diagnostics
echo "8. Diagnostics"
echo "----------------------------------------"
DIAG=$(curl -s "$BASE_URL/diagnostics/all")
if echo "$DIAG" | grep -q '"memory"'; then
    echo -e "${GREEN}✓ Diagnostics endpoint OK${NC}"
else
    echo -e "${RED}✗ Diagnostics endpoint failed${NC}"
fi
echo ""

echo "=========================================="
echo "Endpoint Verification Complete"
echo "=========================================="
