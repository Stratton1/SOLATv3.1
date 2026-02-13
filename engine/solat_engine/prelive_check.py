#!/usr/bin/env python3
"""
Pre-live checklist runner.

Verifies system readiness before live trading:
- Parquet store readable with M1 bars
- Polling can fetch a quote
- Execution config is DEMO mode
- Risk engine smoke test

Run as script:
    python -m solat_engine.prelive_check

Exit codes:
    0: All checks passed
    1: One or more checks failed
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from solat_engine.config import TradingMode, get_settings
from solat_engine.data.models import SupportedTimeframe
from solat_engine.execution.models import (
    ExecutionConfig,
    ExecutionMode,
    OrderIntent,
    OrderSide,
    OrderType,
)
from solat_engine.execution.risk_engine import RiskEngine
from solat_engine.logging import get_logger, setup_logging

logger = get_logger(__name__)


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class PreLiveChecker:
    """
    Pre-live checklist runner.

    Runs a series of checks to verify system readiness.
    """

    def __init__(self) -> None:
        """Initialize checker."""
        self._settings = get_settings()
        self._results: list[CheckResult] = []

    async def run_all_checks(self) -> bool:
        """
        Run all pre-live checks.

        Returns:
            True if all checks passed, False otherwise
        """
        logger.info("=" * 60)
        logger.info("SOLAT Pre-Live Checklist")
        logger.info("=" * 60)

        # Run checks
        await self._check_parquet_store()
        await self._check_polling_quote()
        await self._check_execution_config()
        await self._check_risk_engine()
        await self._check_ig_credentials()

        # Print summary
        self._print_summary()

        return all(r.passed for r in self._results)

    async def _check_parquet_store(self) -> None:
        """Check Parquet store is readable with M1 bars."""
        logger.info("\n[1/5] Checking Parquet store...")

        try:
            from solat_engine.data.parquet_store import ParquetStore

            store = ParquetStore(self._settings.data_dir)

            # Check for any symbols
            summaries = store.get_summary()
            symbols = sorted({str(s.get("symbol")) for s in summaries if s.get("symbol")})
            if not symbols:
                self._results.append(CheckResult(
                    name="Parquet Store",
                    passed=False,
                    message="No symbols found in Parquet store",
                    details={"data_dir": str(self._settings.data_dir)},
                ))
                return

            # Check for M1 bars in first symbol
            symbol = symbols[0]
            bars = store.read_bars(
                symbol=symbol,
                timeframe=SupportedTimeframe.M1,
                limit=10,
            )

            if not bars:
                self._results.append(CheckResult(
                    name="Parquet Store",
                    passed=False,
                    message=f"No M1 bars found for {symbol}",
                    details={"symbol": symbol, "data_dir": str(self._settings.data_dir)},
                ))
                return

            self._results.append(CheckResult(
                name="Parquet Store",
                passed=True,
                message=f"Found {len(symbols)} symbols, {len(bars)} M1 bars for {symbol}",
                details={
                    "symbols": symbols[:5],
                    "total_symbols": len(symbols),
                    "sample_bars": len(bars),
                },
            ))

        except Exception as e:
            self._results.append(CheckResult(
                name="Parquet Store",
                passed=False,
                message=f"Error reading Parquet store: {e}",
            ))

    async def _check_polling_quote(self) -> None:
        """Check polling can fetch a quote."""
        logger.info("\n[2/5] Checking quote polling...")

        try:
            # Check if IG credentials are configured
            if not self._settings.has_ig_credentials:
                self._results.append(CheckResult(
                    name="Quote Polling",
                    passed=False,
                    message="IG credentials not configured",
                    details={"ig_configured": False},
                ))
                return

            from solat_engine.broker.ig.client import AsyncIGClient

            client = AsyncIGClient(self._settings, logger)

            # Try to get session
            await client.ensure_session()

            # Try to fetch a market quote
            # Use a known forex pair
            test_epic = "CS.D.EURUSD.MINI.IP"
            response = await client._request(
                "GET",
                f"/markets/{test_epic}",
                version="3",
            )

            if response.status_code == 200:
                data = response.json()
                bid = data.get("snapshot", {}).get("bid")
                offer = data.get("snapshot", {}).get("offer")

                self._results.append(CheckResult(
                    name="Quote Polling",
                    passed=True,
                    message=f"Fetched quote: bid={bid}, offer={offer}",
                    details={"epic": test_epic, "bid": bid, "offer": offer},
                ))
            else:
                self._results.append(CheckResult(
                    name="Quote Polling",
                    passed=False,
                    message=f"Quote fetch failed: status {response.status_code}",
                ))

            await client.close()

        except Exception as e:
            self._results.append(CheckResult(
                name="Quote Polling",
                passed=False,
                message=f"Error fetching quote: {e}",
            ))

    async def _check_execution_config(self) -> None:
        """Check execution config is DEMO mode."""
        logger.info("\n[3/5] Checking execution configuration...")

        try:
            mode = self._settings.mode

            if mode == TradingMode.DEMO:
                self._results.append(CheckResult(
                    name="Execution Config",
                    passed=True,
                    message="Execution mode is DEMO",
                    details={"mode": mode.value},
                ))
            else:
                self._results.append(CheckResult(
                    name="Execution Config",
                    passed=False,
                    message=f"Execution mode is {mode.value} (expected DEMO)",
                    details={"mode": mode.value, "expected": "DEMO"},
                ))

        except Exception as e:
            self._results.append(CheckResult(
                name="Execution Config",
                passed=False,
                message=f"Error checking config: {e}",
            ))

    async def _check_risk_engine(self) -> None:
        """Run risk engine smoke test."""
        logger.info("\n[4/5] Running risk engine smoke test...")

        try:
            config = ExecutionConfig(
                mode=ExecutionMode.DEMO,
                max_position_size=1.0,
                max_concurrent_positions=3,
                max_daily_loss_pct=5.0,
                max_trades_per_hour=10,
            )

            risk_engine = RiskEngine(config)

            # Create a valid test intent
            valid_intent = OrderIntent(
                intent_id=uuid4(),
                symbol="EURUSD",
                epic="CS.D.EURUSD.MINI.IP",
                side=OrderSide.BUY,
                size=0.5,
                order_type=OrderType.MARKET,
                bot="test_bot",
                timestamp=datetime.now(UTC),
            )

            # Check valid intent should pass
            result = risk_engine.check_intent(
                valid_intent,
                current_positions=[],
                account_balance=10000.0,
                realized_pnl_today=0.0,
            )

            if not result.allowed:
                self._results.append(CheckResult(
                    name="Risk Engine",
                    passed=False,
                    message=f"Valid intent rejected: {result.rejection_reason}",
                    details={"reason_codes": result.reason_codes},
                ))
                return

            # Create an oversized intent that should fail
            oversized_intent = OrderIntent(
                intent_id=uuid4(),
                symbol="EURUSD",
                epic="CS.D.EURUSD.MINI.IP",
                side=OrderSide.BUY,
                size=100.0,  # Way over max
                order_type=OrderType.MARKET,
                bot="test_bot",
                timestamp=datetime.now(UTC),
            )

            result = risk_engine.check_intent(
                oversized_intent,
                current_positions=[],
                account_balance=10000.0,
                realized_pnl_today=0.0,
            )

            if result.allowed and result.adjusted_size == 100.0:
                self._results.append(CheckResult(
                    name="Risk Engine",
                    passed=False,
                    message="Oversized intent was not rejected or adjusted",
                ))
                return

            self._results.append(CheckResult(
                name="Risk Engine",
                passed=True,
                message="Risk engine smoke test passed",
                details={
                    "valid_intent_allowed": True,
                    "oversized_intent_handled": True,
                },
            ))

        except Exception as e:
            self._results.append(CheckResult(
                name="Risk Engine",
                passed=False,
                message=f"Risk engine error: {e}",
            ))

    async def _check_ig_credentials(self) -> None:
        """Check IG credentials are configured."""
        logger.info("\n[5/5] Checking IG credentials...")

        if self._settings.has_ig_credentials:
            # Test actual authentication
            try:
                from solat_engine.broker.ig.client import AsyncIGClient

                client = AsyncIGClient(self._settings, logger)
                await client.ensure_session()

                self._results.append(CheckResult(
                    name="IG Credentials",
                    passed=True,
                    message="IG credentials configured and authenticated",
                    details={"authenticated": True},
                ))

                await client.close()

            except Exception as e:
                self._results.append(CheckResult(
                    name="IG Credentials",
                    passed=False,
                    message=f"IG authentication failed: {e}",
                ))
        else:
            self._results.append(CheckResult(
                name="IG Credentials",
                passed=False,
                message="IG credentials not configured",
                details={
                    "hint": "Set IG_USERNAME, IG_PASSWORD, IG_API_KEY environment variables",
                },
            ))

    def _print_summary(self) -> None:
        """Print summary of all checks."""
        logger.info("\n" + "=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)

        passed = 0
        failed = 0

        for result in self._results:
            status = "PASS" if result.passed else "FAIL"
            icon = "v" if result.passed else "X"
            logger.info(f"[{icon}] {result.name}: {status}")
            logger.info(f"    {result.message}")

            if result.passed:
                passed += 1
            else:
                failed += 1

        logger.info("\n" + "-" * 60)
        logger.info(f"Total: {passed} passed, {failed} failed")

        if failed == 0:
            logger.info("\nAll pre-live checks PASSED!")
        else:
            logger.warning("\nSome checks FAILED. Review before going live.")


async def main() -> int:
    """Run pre-live checks."""
    setup_logging(level="INFO")

    checker = PreLiveChecker()
    success = await checker.run_all_checks()

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
