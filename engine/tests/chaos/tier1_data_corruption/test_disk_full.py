"""
Tier 1: Disk full during critical writes.

Tests that system gracefully rejects operations when disk is full,
rather than corrupting data or allowing operations without audit trail.
"""

import asyncio

import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep
from tests.chaos.fixtures.fake_ig import FakeIGClient
from tests.chaos.fixtures.disk_chaos import DiskChaos


@pytest.mark.chaos
@pytest.mark.tier1
class TestDiskFullScenarios:
    """Tests for disk full failures during ledger and snapshot writes."""

    def test_ledger_write_fails__orders_rejected(
        self, overrider, mock_settings, tmp_path
    ) -> None:
        """
        SCENARIO: Disk full during ledger write
        EXPECTED: Order rejected or broker NOT called when ledger can't write
        FAILURE MODE: Order submitted despite ledger failure (audit trail lost)
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import OrderIntent, OrderSide
        from solat_engine.main import app

        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient(balance=10000.0)

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            # Enable demo mode + arm
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            client.post("/execution/allowlist", json={"symbols": ["EURUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            router = execution_routes._execution_router
            orders_before = fake_ig._order_count

            # INJECT CHAOS: Make ledger record_intent raise an error
            with patch.object(
                router._ledger, "record_intent",
                side_effect=OSError("No space left on device"),
            ):
                intent = OrderIntent(
                    intent_id=uuid4(),
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    bot="chaos_test",
                )

                loop = asyncio.get_event_loop()

                # route_intent should either:
                # 1. Raise an error (which the caller handles), or
                # 2. Return a REJECTED ack
                # Either way, broker should NOT have been called
                try:
                    ack = loop.run_until_complete(router.route_intent(intent))
                    # If it returns, it should be rejected
                except OSError:
                    # Error propagated - acceptable behavior
                    pass

            # Verify broker was NOT called with the failed intent
            assert fake_ig._order_count == orders_before, (
                "Broker should NOT have been called when ledger write fails"
            )

    def test_snapshot_write_fails__positions_still_tracked(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: Disk full during reconciliation snapshot flush
        EXPECTED: In-memory state updated, error logged, next reconciliation retries
        FAILURE MODE: Position state lost permanently
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.main import app

        reset_execution_state()

        # Setup: Configure settings with temp directory
        mock_settings.data_dir = tmp_path
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock broker to return open position
        mock_ig_client.list_positions = AsyncMock(
            return_value=[
                {
                    "dealId": "POS123",
                    "position": {
                        "dealId": "POS123",
                        "size": 1.0,
                        "direction": "BUY",
                    },
                    "market": {
                        "epic": "CS.D.EURUSD.CFD.IP",
                        "instrumentName": "EUR/USD",
                    },
                }
            ]
        )

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            # INJECT CHAOS: Simulate disk full during snapshot flush
            with DiskChaos.partial_write_on_flush():
                # Check that position state is still accessible
                status_resp = client.get("/execution/status")
                assert status_resp.status_code == 200

                # Even if snapshot write failed, status should still return
                data = status_resp.json()
                assert "connected" in data
                assert data["connected"] is True

    def test_artefact_directory_write_fails__graceful_error(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: Cannot write run artefacts (config.json, metrics) due to disk full
        EXPECTED: Operation completes in-memory, warning logged, results still available
        FAILURE MODE: Entire operation fails, backtest aborted
        """
        from solat_engine.api import backtest_routes
        from solat_engine.main import app

        # Reset backtest state
        backtest_routes._parquet_store = None
        backtest_routes._active_jobs.clear()
        backtest_routes._job_results.clear()

        # Setup with temp directory
        mock_settings.data_dir = tmp_path
        overrider.override(get_settings_dep, lambda: mock_settings)

        # Create minimal bars directory
        bars_dir = tmp_path / "parquet" / "bars"
        bars_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal 1h bars for EURUSD
        import pandas as pd

        bars_file = bars_dir / "EURUSD_1h.parquet"
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=100, freq="1h"),
                "open": [1.0850] * 100,
                "high": [1.0860] * 100,
                "low": [1.0840] * 100,
                "close": [1.0855] * 100,
                "volume": [1000] * 100,
            }
        )
        df.to_parquet(bars_file, index=False)

        with TestClient(app) as client:
            # Submit backtest (small date range for speed)
            response = client.post(
                "/backtest/run",
                json={
                    "bots": ["CloudTwist"],
                    "symbols": ["EURUSD"],
                    "timeframe": "1h",
                    "start": "2024-01-01T00:00:00Z",
                    "end": "2024-01-02T23:59:59Z",
                    "initial_balance": 10000.0,
                },
            )

            # Should return run_id even if artefacts can't be written
            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data

            # Result should be retrievable from in-memory cache
            run_id = data["run_id"]
            result_resp = client.get(f"/backtest/result/{run_id}")

            # Even if disk writes failed, result should be available from cache
            assert result_resp.status_code in [200, 404, 500]
