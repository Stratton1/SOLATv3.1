#!/usr/bin/env python3
"""
Full Flow Integration Test: Data Sync → Backtest → Walk-Forward Optimization

This script validates that all components work together end-to-end.
Run this after starting the engine with: python -m solat_engine.main

Usage:
    python scripts/test_full_flow.py
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

import httpx

BASE_URL = "http://127.0.0.1:8765"


async def check_health() -> bool:
    """Check if engine is running."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ Engine healthy: {data.get('version', 'unknown')}")
                return True
        except Exception as e:
            print(f"✗ Engine not reachable: {e}")
            return False
    return False


async def test_data_summary() -> dict | None:
    """Get data summary."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/data/summary", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                total_symbols = data.get("total_symbols", 0)
                total_bars = data.get("total_bars", 0)
                print(f"✓ Data summary: {total_symbols} symbols, {total_bars:,} bars")
                return data
            else:
                print(f"✗ Data summary failed: {resp.status_code}")
        except Exception as e:
            print(f"✗ Data summary error: {e}")
    return None


async def test_data_sync(days: int = 7) -> bool:
    """Test quick data sync."""
    async with httpx.AsyncClient() as client:
        try:
            print(f"  Syncing last {days} days of data...")
            resp = await client.post(
                f"{BASE_URL}/data/sync/quick?days={days}",
                timeout=300.0,  # 5 minutes for sync
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    print(f"✓ Data sync started: run_id={data.get('run_id')}")
                    return True
                else:
                    print(f"✗ Data sync failed: {data.get('message')}")
            else:
                print(f"✗ Data sync HTTP error: {resp.status_code}")
        except Exception as e:
            print(f"✗ Data sync error: {e}")
    return False


async def test_get_bars(symbol: str = "EURUSD", timeframe: str = "1h") -> bool:
    """Test fetching bars."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/data/bars",
                params={"symbol": symbol, "timeframe": timeframe, "limit": 100},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                bars = data.get("bars", [])
                print(f"✓ Got {len(bars)} bars for {symbol} {timeframe}")
                return len(bars) > 0
            else:
                print(f"✗ Get bars failed: {resp.status_code}")
        except Exception as e:
            print(f"✗ Get bars error: {e}")
    return False


async def test_backtest_bots() -> list[str]:
    """Get available bots."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/backtest/bots", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                bots = [b["name"] for b in data.get("bots", [])]
                print(f"✓ Available bots: {', '.join(bots[:5])}{'...' if len(bots) > 5 else ''}")
                return bots
        except Exception as e:
            print(f"✗ Get bots error: {e}")
    return []


async def test_single_backtest(
    symbol: str = "EURUSD",
    bot: str = "ichimoku_cloud_basic",
    timeframe: str = "1h",
) -> dict | None:
    """Run a single backtest."""
    async with httpx.AsyncClient() as client:
        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=30)

            payload = {
                "symbols": [symbol],
                "bots": [bot],
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "initial_cash": 10000.0,
            }

            print(f"  Running backtest: {symbol}/{bot}/{timeframe}...")
            resp = await client.post(
                f"{BASE_URL}/backtest/run",
                json=payload,
                timeout=120.0,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    run_id = data.get("run_id")
                    print(f"✓ Backtest started: run_id={run_id}")

                    # Poll for completion
                    for _ in range(60):  # Max 60 seconds
                        await asyncio.sleep(1)
                        status_resp = await client.get(
                            f"{BASE_URL}/backtest/status",
                            params={"run_id": run_id},
                            timeout=10.0,
                        )
                        if status_resp.status_code == 200:
                            status = status_resp.json()
                            if status.get("status") == "done":
                                # Get results
                                results_resp = await client.get(
                                    f"{BASE_URL}/backtest/results",
                                    params={"run_id": run_id},
                                    timeout=10.0,
                                )
                                if results_resp.status_code == 200:
                                    results = results_resp.json()
                                    metrics = results.get("metrics", {})
                                    print(
                                        f"✓ Backtest done: "
                                        f"trades={metrics.get('total_trades', 0)}, "
                                        f"sharpe={metrics.get('sharpe_ratio', 0):.2f}"
                                    )
                                    return results
                            elif status.get("status") == "failed":
                                print(f"✗ Backtest failed: {status.get('message')}")
                                return None
                else:
                    print(f"✗ Backtest rejected: {data.get('message', data)}")
            else:
                print(f"✗ Backtest HTTP error: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            print(f"✗ Backtest error: {e}")
    return None


async def test_walk_forward(
    symbols: list[str] = None,
    bots: list[str] = None,
) -> dict | None:
    """Test walk-forward optimization."""
    if symbols is None:
        symbols = ["EURUSD"]
    if bots is None:
        bots = ["ichimoku_cloud_basic"]

    async with httpx.AsyncClient() as client:
        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=180)  # 6 months

            payload = {
                "symbols": symbols,
                "bots": bots,
                "timeframes": ["1h"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "window_type": "rolling",
                "in_sample_days": 60,
                "out_of_sample_days": 30,
                "step_days": 30,
                "optimization_mode": "sharpe",
                "top_n": 5,
                "min_trades": 5,
            }

            print(f"  Starting walk-forward: {len(symbols)} symbols, {len(bots)} bots...")
            resp = await client.post(
                f"{BASE_URL}/optimization/walk-forward",
                json=payload,
                timeout=600.0,  # 10 minutes
            )

            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ Walk-forward started: run_id={data.get('run_id')}")
                return data
            else:
                print(f"✗ Walk-forward HTTP error: {resp.status_code}")
                print(f"  Response: {resp.text[:200]}")
        except Exception as e:
            print(f"✗ Walk-forward error: {e}")
    return None


async def test_allowlist() -> dict | None:
    """Test allowlist status."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/optimization/allowlist", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                print(
                    f"✓ Allowlist: {data.get('enabled_entries', 0)} enabled, "
                    f"{data.get('total_entries', 0)} total"
                )
                return data
            else:
                print(f"✗ Allowlist HTTP error: {resp.status_code}")
        except Exception as e:
            print(f"✗ Allowlist error: {e}")
    return None


async def main():
    """Run full integration test."""
    print("=" * 60)
    print("SOLAT v3.1 Full Flow Integration Test")
    print("=" * 60)
    print()

    # Step 1: Health check
    print("Step 1: Health Check")
    print("-" * 40)
    if not await check_health():
        print("\n❌ Engine not running. Start with: python -m solat_engine.main")
        sys.exit(1)
    print()

    # Step 2: Check existing data
    print("Step 2: Data Summary")
    print("-" * 40)
    summary = await test_data_summary()
    has_data = summary and summary.get("total_bars", 0) > 0
    print()

    # Step 3: Data sync (if needed)
    if not has_data:
        print("Step 3: Data Sync (no existing data)")
        print("-" * 40)
        if await test_data_sync(days=30):
            # Wait a bit for sync to complete
            print("  Waiting for sync to complete...")
            await asyncio.sleep(10)
            await test_data_summary()
        print()
    else:
        print("Step 3: Data Sync (skipped - data exists)")
        print()

    # Step 4: Test bar retrieval
    print("Step 4: Bar Retrieval")
    print("-" * 40)
    await test_get_bars("EURUSD", "1h")
    print()

    # Step 5: Get available bots
    print("Step 5: Available Strategies")
    print("-" * 40)
    bots = await test_backtest_bots()
    print()

    # Step 6: Single backtest
    print("Step 6: Single Backtest")
    print("-" * 40)
    bot = bots[0] if bots else "ichimoku_cloud_basic"
    await test_single_backtest("EURUSD", bot, "1h")
    print()

    # Step 7: Walk-forward optimization
    print("Step 7: Walk-Forward Optimization")
    print("-" * 40)
    await test_walk_forward(symbols=["EURUSD"], bots=[bot])
    print()

    # Step 8: Allowlist status
    print("Step 8: Allowlist Status")
    print("-" * 40)
    await test_allowlist()
    print()

    print("=" * 60)
    print("Integration Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
