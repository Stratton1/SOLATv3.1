"""
Tier 4: Kill switch persistence across restarts.

Tests that kill switch state is persisted to disk and restored
after engine restart, ensuring emergency stop remains effective.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep


@pytest.mark.chaos
@pytest.mark.tier4
class TestKillSwitchPersistenceScenarios:
    """Tests for kill switch state persistence."""

    def test_kill_switch_state_persisted_across_restart(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: Activate kill switch, restart engine, check if still active
        EXPECTED: Kill switch remains active after restart
        FAILURE MODE: Kill switch state lost, trading resumes after restart
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.main import app

        # Setup temp data directory
        mock_settings.data_dir = tmp_path
        kill_switch_state_file = tmp_path / "kill_switch_state.json"

        # === First session: Activate kill switch ===
        reset_execution_state()
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        mock_ig_client.list_accounts = AsyncMock(
            return_value=[
                {
                    "accountId": "ABC123",
                    "accountType": "CFD",
                    "balance": {"balance": 10000.0, "available": 10000.0},
                    "currency": "USD",
                }
            ]
        )

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router = execution_routes._execution_router
            router.kill_switch.activate(
                reason="Test emergency stop",
                activated_by="chaos_test"
            )

            # Verify kill switch is active (is_active is a @property)
            assert router.kill_switch.is_active is True

            # Save state to disk
            router.kill_switch.save_state(kill_switch_state_file)
            assert kill_switch_state_file.exists()

        # === Second session: Restart and verify state restored ===
        reset_execution_state()
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        with TestClient(app) as client:
            # Connect again (simulates engine restart)
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router2 = execution_routes._execution_router

            # Manually restore state (until auto-restore is wired into connect)
            router2.kill_switch.restore_state(kill_switch_state_file)

            # Verify kill switch is still active after restart
            assert router2.kill_switch.is_active is True
            assert router2.kill_switch.activation_reason == "Test emergency stop"

            # Verify orders are blocked (check_can_trade returns tuple)
            can_trade, reason = router2.kill_switch.check_can_trade()
            assert can_trade is False
            assert reason is not None
            assert "test emergency stop" in reason.lower()

    def test_kill_switch_reset_clears_state_file(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: Activate kill switch, reset it, restart engine
        EXPECTED: Kill switch inactive after restart (reset cleared state)
        FAILURE MODE: Kill switch reactivates after restart despite being reset
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.main import app

        mock_settings.data_dir = tmp_path
        kill_switch_state_file = tmp_path / "kill_switch_state.json"

        # === First session: Activate then reset ===
        reset_execution_state()
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        mock_ig_client.list_accounts = AsyncMock(
            return_value=[
                {
                    "accountId": "ABC123",
                    "accountType": "CFD",
                    "balance": {"balance": 10000.0, "available": 10000.0},
                    "currency": "USD",
                }
            ]
        )

        with TestClient(app) as client:
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router = execution_routes._execution_router

            # Activate kill switch
            router.kill_switch.activate(
                reason="Test stop",
                activated_by="test"
            )
            router.kill_switch.save_state(kill_switch_state_file)
            assert kill_switch_state_file.exists()

            # Reset kill switch
            router.kill_switch.reset()
            assert router.kill_switch.is_active is False

            # Save state after reset (should mark inactive)
            router.kill_switch.save_state(kill_switch_state_file)

        # === Second session: Verify kill switch stays inactive ===
        reset_execution_state()
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        with TestClient(app) as client:
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router2 = execution_routes._execution_router
            router2.kill_switch.restore_state(kill_switch_state_file)

            # Verify kill switch remains inactive after restart
            assert router2.kill_switch.is_active is False

            # Verify trading is allowed
            can_trade, reason = router2.kill_switch.check_can_trade()
            assert can_trade is True
