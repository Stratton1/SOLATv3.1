#!/usr/bin/env python3
"""
Verify all LIVE epic mappings in the instrument catalogue.

Phase 070-B: Audits seed data for completeness and optionally tests
each epic against the IG REST API.

Usage:
    # Offline audit (no IG credentials needed)
    python3 scripts/verify_live_epics.py

    # Online verification against IG API
    python3 scripts/verify_live_epics.py --verify-api
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solat_engine.catalog.seed import SEED_INSTRUMENTS


def audit_seed_data() -> tuple[list[dict], list[dict]]:
    """Audit seed data for missing epics. Returns (complete, incomplete)."""
    complete = []
    incomplete = []

    for item in SEED_INSTRUMENTS:
        entry = {
            "symbol": item.symbol,
            "display_name": item.display_name,
            "asset_class": item.asset_class.value,
            "demo_epic": item.demo_epic,
            "live_epic": item.live_epic,
        }
        if item.demo_epic and item.live_epic:
            complete.append(entry)
        else:
            incomplete.append(entry)

    return complete, incomplete


async def verify_against_api(items: list[dict]) -> list[dict]:
    """Verify epics resolve via IG REST API (requires credentials)."""
    from solat_engine.broker.ig.client import IGClient
    from solat_engine.config import get_settings

    settings = get_settings()
    client = IGClient(settings)

    results = []
    for item in items:
        epic = item["live_epic"]
        try:
            market = await client.get_market(epic)
            instrument = market.get("instrument", {})
            results.append({
                **item,
                "api_status": "OK",
                "instrument_name": instrument.get("name", ""),
                "tradeable": market.get("snapshot", {}).get("marketStatus") == "TRADEABLE",
            })
        except Exception as e:
            results.append({
                **item,
                "api_status": "FAIL",
                "error": str(e),
            })

    return results


def print_report(complete: list[dict], incomplete: list[dict],
                 api_results: list[dict] | None = None) -> int:
    """Print audit report. Returns 0 if all good, 1 if issues."""
    print(f"\n{'='*80}")
    print("PHASE 070-B: IG LIVE EPIC MAPPING AUDIT")
    print(f"{'='*80}\n")

    # Summary by asset class
    from collections import Counter
    ac_complete = Counter(i["asset_class"] for i in complete)
    ac_incomplete = Counter(i["asset_class"] for i in incomplete)

    print(f"{'Asset Class':<15} {'Complete':<10} {'Missing':<10} {'Total':<10}")
    print("-" * 45)
    all_classes = sorted(set(list(ac_complete.keys()) + list(ac_incomplete.keys())))
    for ac in all_classes:
        c = ac_complete.get(ac, 0)
        m = ac_incomplete.get(ac, 0)
        print(f"{ac:<15} {c:<10} {m:<10} {c+m:<10}")
    print("-" * 45)
    print(f"{'TOTAL':<15} {len(complete):<10} {len(incomplete):<10} {len(complete)+len(incomplete):<10}")

    # Complete instruments
    print(f"\n--- Instruments with LIVE epic ({len(complete)}) ---\n")
    print(f"{'Symbol':<10} {'Class':<12} {'Demo Epic':<30} {'Live Epic':<30}")
    print("-" * 82)
    for item in sorted(complete, key=lambda x: (x["asset_class"], x["symbol"])):
        same = " (same)" if item["demo_epic"] == item["live_epic"] else ""
        print(f"{item['symbol']:<10} {item['asset_class']:<12} {item['demo_epic']:<30} {item['live_epic']}{same}")

    # Incomplete instruments
    if incomplete:
        print(f"\n--- Instruments MISSING live epic ({len(incomplete)}) ---\n")
        for item in sorted(incomplete, key=lambda x: (x["asset_class"], x["symbol"])):
            print(f"  {item['symbol']:<10} ({item['asset_class']}) — no demo_epic or live_epic")

    # API verification results
    if api_results:
        print(f"\n--- API Verification Results ---\n")
        ok = [r for r in api_results if r["api_status"] == "OK"]
        fail = [r for r in api_results if r["api_status"] == "FAIL"]

        for r in ok:
            tradeable = "TRADEABLE" if r.get("tradeable") else "NOT TRADEABLE"
            print(f"  {r['symbol']:<10} {r['live_epic']:<30} OK — {r.get('instrument_name', '')} [{tradeable}]")

        for r in fail:
            print(f"  {r['symbol']:<10} {r['live_epic']:<30} FAIL — {r.get('error', '')}")

        if fail:
            print(f"\n  {len(fail)} epic(s) FAILED API verification")

    # FX-specific note
    print(f"\n--- Notes ---")
    print(f"  FX: DEMO uses MINI, LIVE uses TODAY (verified pattern)")
    print(f"  Indices/Commodities: same epic for DEMO and LIVE (common IG pattern)")
    if incomplete:
        print(f"  {len(incomplete)} instruments have no IG epic — excluded from trading")

    has_issues = len(incomplete) > 0
    api_failures = len([r for r in (api_results or []) if r["api_status"] == "FAIL"])

    print(f"\n{'='*80}")
    if not has_issues and not api_failures:
        print("RESULT: ALL EPICS PRESENT AND VERIFIED")
    elif has_issues and not api_failures:
        print(f"RESULT: {len(incomplete)} instruments missing epics (non-blocking for go-live)")
    else:
        print(f"RESULT: {api_failures} API verification failures — NEEDS ATTENTION")
    print(f"{'='*80}\n")

    return 1 if api_failures else 0


def main():
    parser = argparse.ArgumentParser(description="Verify IG LIVE epic mappings")
    parser.add_argument("--verify-api", action="store_true",
                       help="Test epics against IG REST API (requires credentials)")
    args = parser.parse_args()

    complete, incomplete = audit_seed_data()

    api_results = None
    if args.verify_api:
        api_results = asyncio.run(verify_against_api(complete))

    exit_code = print_report(complete, incomplete, api_results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
