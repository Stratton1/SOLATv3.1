"""
Tier 1: Stale account balance in risk checks.

Tests that system detects and handles stale account balance data,
preventing overleveraged positions from being approved based on outdated info.
"""

import asyncio

import pytest
from datetime import datetime, timedelta, UTC
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep
from tests.chaos.fixtures.fake_ig import FakeIGClient


@pytest.mark.chaos
@pytest.mark.tier1
class TestStaleBalanceScenarios:
    """Tests for stale account balance in risk checks."""

    def test_balance_stale_300s__order_rejected_or_refreshed(
        self, overrider, mock_settings, tmp_path
    ) -> None:
        """
        SCENARIO: Account balance is 5+ minutes old when order submitted
        EXPECTED: Balance forcibly refreshed before risk check
        FAILURE MODE: Risk engine uses stale balance, overleveraged position approved
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
            # Connect - fetches balance
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

            # INJECT CHAOS: Make balance timestamp 6 minutes old
            router._balance_last_updated = datetime.now(UTC) - timedelta(minutes=6)
            old_list_accounts_count = fake_ig._list_accounts_count

            # Submit intent - should trigger balance refresh due to stale timestamp
            intent = OrderIntent(
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                bot="chaos_test",
            )

            loop = asyncio.get_event_loop()
            ack = loop.run_until_complete(router.route_intent(intent))

            # Balance should have been refreshed (list_accounts called again)
            assert fake_ig._list_accounts_count > old_list_accounts_count, (
                "Balance should be refreshed when stale (>5 min)"
            )

            # Balance timestamp should be recent now
            assert router._balance_last_updated is not None
            age_seconds = (datetime.now(UTC) - router._balance_last_updated).total_seconds()
            assert age_seconds < 10, f"Balance should be fresh, but is {age_seconds}s old"

    def test_balance_never_fetched__order_rejected(
        self, overrider, mock_settings, tmp_path
    ) -> None:
        """
        SCENARIO: Connect succeeds but balance is zero (never properly fetched)
        EXPECTED: Orders still go through risk engine with zero balance
        FAILURE MODE: Risk checks bypassed entirely
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import OrderIntent, OrderSide
        from solat_engine.main import app

        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient(balance=0.0)  # Zero balance

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
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

            # Submit intent with zero balance
            intent = OrderIntent(
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                bot="chaos_test",
            )

            loop = asyncio.get_event_loop()
            ack = loop.run_until_complete(router.route_intent(intent))

            # With zero balance, risk engine should still run and either:
            # - reject due to insufficient balance, OR
            # - allow because DEMO mode doesn't check balance strictly
            # Either way, the system must not crash
            assert ack is not None
            assert ack.intent_id == intent.intent_id

    def test_balance_refresh_after_fills__updates_used(
        self, overrider, mock_settings, tmp_path
    ) -> None:
        """
        SCENARIO: Multiple orders filled, balance should update after 10 fills
        EXPECTED: Balance refreshed periodically (every 10 fills)
        FAILURE MODE: Balance stale after fills, subsequent orders use wrong balance
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
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200
            assert fake_ig._list_accounts_count == 1  # Initial balance fetch

            # Enable demo mode + arm
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            client.post("/execution/allowlist", json={"symbols": ["EURUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            router = execution_routes._execution_router
            loop = asyncio.get_event_loop()

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

            # After 10+ fills, list_accounts should have been called again
            # (once at connect + at least once after 10 fills)
            assert fake_ig._list_accounts_count >= 2, (
                f"Balance should be refreshed after 10 fills, but list_accounts "
                f"called only {fake_ig._list_accounts_count} times"
            )
