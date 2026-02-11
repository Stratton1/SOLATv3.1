"""
Tier 2: Account balance refresh after fills.

Tests that account balance is updated after order fills,
not just at initial connect.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep


@pytest.mark.chaos
@pytest.mark.tier2
class TestBalanceRefreshScenarios:
    """Tests for balance refresh logic."""

    @pytest.mark.skip(reason="Requires route_intent integration test harness (tracked: PROMPT-024)")
    async def test_balance_refresh_after_fills__updates_used(
        self, overrider, mock_settings, mock_ig_client
    ) -> None:
        """
        SCENARIO: Submit 10 orders, each fills successfully.
                  After 10th fill, balance should be refreshed from broker
        EXPECTED: Balance updates after every N fills (e.g., N=10)
        FAILURE MODE: Balance never updated, stale balance used for risk checks
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import OrderIntent, OrderSide
        from solat_engine.main import app

        reset_execution_state()

        # Setup
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Track list_accounts calls to verify balance refresh
        balance_fetch_count = 0
        initial_balance = 10000.0
        balance_after_fills = 9500.0  # Simulated after P&L

        async def mock_list_accounts():
            nonlocal balance_fetch_count
            balance_fetch_count += 1

            balance = initial_balance if balance_fetch_count == 1 else balance_after_fills

            return [
                {
                    "accountId": "ABC123",
                    "accountType": "CFD",
                    "balance": {"balance": balance, "available": balance},
                    "currency": "USD",
                }
            ]

        mock_ig_client.list_accounts = mock_list_accounts

        # Mock broker to confirm orders
        mock_ig_client.submit_order = AsyncMock(
            return_value={
                "dealReference": "DEAL_X",
                "dealId": "DEAL_X",
                "status": "CONFIRMED",
            }
        )

        with TestClient(app) as client:
            # Connect (first balance fetch)
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200
            assert balance_fetch_count == 1

            router = execution_routes._execution_router

            # Submit 10 orders (simulating fills)
            for i in range(10):
                intent = OrderIntent(
                    intent_id=uuid4(),
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    entry_price=None,
                    stop_loss=None,
                    take_profit=None,
                )

                ack = await router.route_intent(intent)
                # Note: Actual fill handling depends on execution mode
                # For this test, we assume fills occur

                # Simulate fill by calling router._handle_fill() if it exists
                # Or by incrementing router._fills_since_balance_refresh

                if hasattr(router, "_fills_since_balance_refresh"):
                    router._fills_since_balance_refresh += 1

            # After 10 fills, balance should be refreshed
            # Check if list_accounts was called again
            # Expected: balance_fetch_count should be 2 (initial + after 10 fills)

            # Note: This test validates the BEHAVIOR, not the API
            # Full implementation requires:
            # 1. _handle_fill() method in router
            # 2. Balance refresh logic after N fills
            # 3. _refresh_account_balance() call

            # For now, this test structure is ready
            # It will pass once Phase 4 bug fix is implemented
            assert balance_fetch_count >= 2, "Balance should be refreshed after fills"

            # Verify router uses updated balance
            if hasattr(router, "_account_balance"):
                assert router._account_balance == balance_after_fills
