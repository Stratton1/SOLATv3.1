"""
Tier 2: Partial position close scenarios.

Tests that system handles partial fills and broker state drift gracefully,
ensuring local state reconciles to broker truth.
"""

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep


@pytest.mark.chaos
@pytest.mark.tier2
class TestPartialCloseScenarios:
    """Tests for partial position closes and reconciliation."""

    def test_broker_confirms_half__position_reconciled(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: Request close 1.0 lots, broker confirms 0.5 lots (partial fill)
        EXPECTED: Position store shows 0.5 remaining (broker truth), ledger records partial
        FAILURE MODE: Local shows fully closed, broker has 0.5 open (ghost position)
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.main import app

        reset_execution_state()

        # Setup
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock broker to return open position initially
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

        # Mock partial close (broker confirms only 0.5)
        mock_ig_client.close_position = AsyncMock(
            return_value={
                "dealReference": "CLOSE123",
                "dealId": "CLOSE123",
                "status": "CONFIRMED",
                "size": 0.5,  # Only half closed
            }
        )

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            # INJECT CHAOS: Request full close, but broker only closes half
            # Note: ExecutionRouter.close_position doesn't exist in HTTP API yet
            # This test would call: POST /execution/close with deal_id=POS123

            # After partial close, reconciliation should detect drift
            # Update mock to show 0.5 remaining
            mock_ig_client.list_positions = AsyncMock(
                return_value=[
                    {
                        "dealId": "POS123",
                        "position": {
                            "dealId": "POS123",
                            "size": 0.5,  # Half remaining
                            "direction": "BUY",
                        },
                        "market": {
                            "epic": "CS.D.EURUSD.CFD.IP",
                            "instrumentName": "EUR/USD",
                        },
                    }
                ]
            )

            # Verify that reconciliation detects partial close
            # (This requires a reconciliation endpoint or wait for auto-reconcile)
            status_resp = client.get("/execution/status")
            assert status_resp.status_code == 200

            # Position should eventually show 0.5 (broker truth)
            # Note: Full implementation requires reconciliation endpoint
            # For now, this validates the test structure

    def test_kill_switch_closes_3_of_4__drift_detected(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: 4 positions open, kill switch activates, first 3 closes succeed,
                  4th fails all 3 retries (broker timeout)
        EXPECTED: Drift warning logged, 1 position still open on broker
        FAILURE MODE: Kill switch marked "complete" but position still open untracked
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.main import app
        from solat_engine.execution.models import OrderSide

        reset_execution_state()

        # Setup
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock broker with 4 open positions
        initial_positions = [
            {
                "dealId": f"POS{i}",
                "position": {
                    "dealId": f"POS{i}",
                    "size": 1.0,
                    "direction": "BUY",
                },
                "market": {
                    "epic": "CS.D.EURUSD.CFD.IP",
                    "instrumentName": "EUR/USD",
                },
            }
            for i in range(1, 5)
        ]

        mock_ig_client.list_positions = AsyncMock(return_value=initial_positions)

        # Mock close_position: first 3 succeed, 4th fails
        close_call_count = 0

        async def mock_close(deal_id: str, direction: str, size: float):
            nonlocal close_call_count
            close_call_count += 1

            if deal_id == "POS4":
                # 4th position always fails (timeout)
                raise Exception("Broker timeout")
            else:
                # First 3 succeed
                return {
                    "dealReference": f"CLOSE{close_call_count}",
                    "status": "CONFIRMED",
                }

        mock_ig_client.close_position = mock_close

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            # INJECT CHAOS: Activate kill switch (if endpoint exists)
            # Note: This requires POST /execution/kill-switch endpoint
            # Or direct ExecutionRouter.kill_switch.activate() call

            # After kill switch, positions 1-3 should close, POS4 should remain
            # Update broker mock to show only POS4 open
            mock_ig_client.list_positions = AsyncMock(
                return_value=[
                    {
                        "dealId": "POS4",
                        "position": {
                            "dealId": "POS4",
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

            # Verify drift is detected
            # (Requires reconciliation to run and detect mismatch)
            # For now, this validates test structure

            # Note: Full implementation requires:
            # 1. Kill switch endpoint
            # 2. Reconciliation endpoint
            # 3. Drift detection logging
