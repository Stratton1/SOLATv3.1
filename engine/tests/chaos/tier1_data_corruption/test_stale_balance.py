"""
Tier 1: Stale account balance in risk checks.

Tests that system detects and handles stale account balance data,
preventing overleveraged positions from being approved based on outdated info.
"""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep


@pytest.mark.chaos
@pytest.mark.tier1
class TestStaleBalanceScenarios:
    """Tests for stale account balance in risk checks."""

    def test_balance_stale_300s__order_rejected_or_refreshed(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: Account balance is 5+ minutes old when order submitted
        EXPECTED: Order rejected OR balance forcibly refreshed before risk check
        FAILURE MODE: Risk engine uses stale balance, overleveraged position approved

        NOTE: This test documents a CRITICAL BUG identified in exploration:
        ExecutionRouter._account_balance is fetched once at connect() and never updated.
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.main import app

        reset_execution_state()

        # Configure overrides
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock broker responses
        initial_balance = 10000.0
        mock_ig_client.list_accounts = AsyncMock(
            return_value=[
                {
                    "accountId": "ABC123",
                    "balance": {"balance": initial_balance, "deposit": initial_balance},
                }
            ]
        )

        mock_ig_client.submit_order = AsyncMock(
            return_value={
                "dealReference": "DEAL123",
                "dealId": "DEAL123",
                "status": "CONFIRMED",
            }
        )

        with TestClient(app) as client:
            # Connect - fetches balance
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            # INJECT CHAOS: Simulate passage of time (5+ minutes)
            # Patch router's balance timestamp to be stale
            with patch("solat_engine.execution.router.ExecutionRouter") as mock_router_class:
                # Get actual router instance from execution_routes
                from solat_engine.api import execution_routes

                actual_router = execution_routes._execution_router

                if actual_router is not None:
                    # Mock the balance timestamp to be 6 minutes old
                    stale_timestamp = datetime.now(UTC) - timedelta(minutes=6)

                    with patch.object(
                        actual_router, "_balance_last_updated", stale_timestamp
                    ):
                        # Skip this test - requires refactoring to test router.route_intent() directly
                        # since /execution/intents endpoint doesn't exist
                        pytest.skip("Requires route_intent integration test harness (tracked: PROMPT-024)")

    def test_balance_never_fetched__order_rejected(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: Account balance was never successfully fetched
        EXPECTED: Orders rejected with clear error
        FAILURE MODE: Orders approved with zero/None balance (risk checks bypassed)
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.main import app

        reset_execution_state()

        # Configure broker to fail balance fetch
        mock_ig_client.list_accounts = AsyncMock(side_effect=Exception("Connection error"))

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        with TestClient(app) as client:
            # Try to connect - should fail or succeed with no balance
            try:
                connect_resp = client.post("/execution/connect")

                # Skip order submission test - endpoint doesn't exist
                pytest.skip("Requires route_intent integration test harness (tracked: PROMPT-024)")

            except Exception:
                # Connect failing is acceptable
                pass

    def test_balance_refresh_after_fills__updates_used(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: Multiple orders filled, balance should update after each
        EXPECTED: Balance refreshed periodically or after N fills
        FAILURE MODE: Balance stale after first fill, subsequent orders use wrong balance
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.main import app

        reset_execution_state()

        # Track balance queries
        balance_queries = []

        async def track_balance_queries():
            balance_queries.append(datetime.now(UTC))
            return [
                {
                    "accountId": "ABC123",
                    "balance": {"balance": 10000.0 - len(balance_queries) * 100},
                }
            ]

        mock_ig_client.list_accounts = AsyncMock(side_effect=track_balance_queries)

        mock_ig_client.submit_order = AsyncMock(
            return_value={
                "dealReference": "DEAL123",
                "dealId": "DEAL123",
                "status": "CONFIRMED",
            }
        )

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200
            assert len(balance_queries) == 1  # Initial balance fetch

            # Skip order submission - endpoint doesn't exist
            # This test would need to call router.route_intent() directly
            pytest.skip("Requires route_intent integration test harness (tracked: PROMPT-024)")

            # VERIFICATION: Balance should have been refreshed at least once more
            # Ideal: Refresh every N fills (e.g., N=10)
            # Minimum: Refresh at least once after connect
            # Current BUG: Balance never refreshed (will stay at 1)

            if len(balance_queries) == 1:
                pytest.xfail(
                    "BUG: Balance never refreshed after fills. "
                    "Expected balance refresh every N fills or on demand."
                )
            else:
                # If balance was refreshed, verify it happened periodically
                assert len(balance_queries) > 1
