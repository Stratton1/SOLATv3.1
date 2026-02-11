"""
Tier 2: Account balance refresh after fills.

Tests that account balance is updated after order fills,
not just at initial connect.
"""

import asyncio

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep
from tests.chaos.fixtures.fake_ig import FakeIGClient


@pytest.mark.chaos
@pytest.mark.tier2
class TestBalanceRefreshScenarios:
    """Tests for balance refresh logic."""

    def test_balance_refresh_after_fills__updates_used(
        self, overrider, mock_settings, tmp_path
    ) -> None:
        """
        SCENARIO: Submit 10+ orders, each fills successfully.
                  After 10th fill, balance should be refreshed from broker
        EXPECTED: Balance updates after every 10 fills
        FAILURE MODE: Balance never updated, stale balance used for risk checks
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import OrderIntent, OrderSide
        from solat_engine.main import app

        reset_execution_state()

        mock_settings.data_dir = tmp_path
        initial_balance = 10000.0
        balance_after_fills = 9500.0

        fake_ig = FakeIGClient(balance=initial_balance)

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            # Connect (first balance fetch)
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200
            assert fake_ig._list_accounts_count == 1

            # Enable demo mode + arm
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            client.post("/execution/allowlist", json={"symbols": ["EURUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            router = execution_routes._execution_router
            loop = asyncio.get_event_loop()

            # Update balance for post-fill refresh
            fake_ig.set_balance(balance_after_fills)

            # Submit 11 orders (balance refresh triggers every 10 fills)
            for i in range(11):
                intent = OrderIntent(
                    intent_id=uuid4(),
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    bot="chaos_test",
                )
                ack = loop.run_until_complete(router.route_intent(intent))

            # After 10 fills, balance should be refreshed
            assert fake_ig._list_accounts_count >= 2, (
                f"Balance should be refreshed after fills, but list_accounts "
                f"called only {fake_ig._list_accounts_count} times"
            )

            # Verify router uses updated balance
            assert router._account_balance == balance_after_fills, (
                f"Router balance should be {balance_after_fills}, "
                f"but is {router._account_balance}"
            )
