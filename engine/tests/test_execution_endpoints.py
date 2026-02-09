"""
Tests for execution API endpoints.

All tests use mocks - no real IG network calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep
from solat_engine.execution.gates import GateMode, GateStatus

# =============================================================================
# Status Endpoint Tests
# =============================================================================


class TestStatusEndpoint:
    """Tests for GET /execution/status endpoint."""

    def test_status_returns_initial_state(self, api_client: TestClient) -> None:
        """Should return initial disconnected state."""
        response = api_client.get("/execution/status")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "DEMO"
        assert data["connected"] is False
        assert data["armed"] is False
        assert data["kill_switch_active"] is False


# =============================================================================
# Connect Endpoint Tests
# =============================================================================


class TestConnectEndpoint:
    """Tests for POST /execution/connect endpoint."""

    def test_connect_without_credentials(
        self, api_client: TestClient, mock_settings: MagicMock
    ) -> None:
        """Should fail when credentials not configured."""
        # Override settings to not have IG credentials
        mock_settings.has_ig_credentials = False

        from solat_engine.api import execution_routes
        execution_routes.reset_execution_state()

        response = api_client.post("/execution/connect")

        assert response.status_code == 400
        assert "credentials" in response.json()["detail"].lower()

    def test_connect_with_mocked_broker(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should connect when broker is mocked."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        response = api_client.post("/execution/connect")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["mode"] == "DEMO"

    def test_live_connect_blocked_when_gates_fail(
        self, mock_ig_client: AsyncMock, mock_settings, overrider
    ) -> None:
        """LIVE mode connect should fail when trading gates are not satisfied."""
        from solat_engine.api.execution_routes import (
            reset_execution_state,
        )

        reset_execution_state()

        # Set execution mode to LIVE
        mock_settings.execution_mode = "LIVE"
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock gates to return blocked
        mock_gates = MagicMock()
        mock_gates.evaluate.return_value = GateStatus(
            allowed=False,
            mode=GateMode.DEMO,
            blockers=["LIVE_TRADING_ENABLED is not set to true"],
        )

        with patch(
            "solat_engine.api.execution_routes.get_trading_gates",
            return_value=mock_gates,
        ):
            from solat_engine.main import app
            with TestClient(app) as client:
                response = client.post("/execution/connect")

        assert response.status_code == 400
        assert "LIVE mode blocked" in response.json()["detail"]

    def test_live_connect_succeeds_when_gates_pass(
        self, mock_ig_client: AsyncMock, mock_settings, overrider
    ) -> None:
        """LIVE mode connect should succeed when all trading gates pass."""
        from solat_engine.api.execution_routes import (
            reset_execution_state,
        )

        reset_execution_state()

        # Set execution mode to LIVE
        mock_settings.execution_mode = "LIVE"
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock gates to return allowed
        mock_gates = MagicMock()
        mock_gates.evaluate.return_value = GateStatus(
            allowed=True,
            mode=GateMode.LIVE,
        )

        with patch(
            "solat_engine.api.execution_routes.get_trading_gates",
            return_value=mock_gates,
        ):
            from solat_engine.main import app
            with TestClient(app) as client:
                response = client.post("/execution/connect")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["mode"] == "LIVE"


# =============================================================================
# Arm/Disarm Endpoint Tests
# =============================================================================


class TestArmEndpoint:
    """Tests for POST /execution/arm endpoint."""

    def test_arm_requires_confirmation(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should require confirmation to arm."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")

        # Try to arm without confirmation
        response = api_client.post("/execution/arm", json={"confirm": False})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "confirm" in data["error"].lower()

    def test_arm_with_confirmation(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should arm when confirmation provided."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")

        response = api_client.post("/execution/arm", json={"confirm": True})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["armed"] is True

    def test_disarm(self, api_client: TestClient, mock_ig_client: AsyncMock, overrider) -> None:
        """Should disarm execution."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")
        api_client.post("/execution/arm", json={"confirm": True})

        response = api_client.post("/execution/disarm")

        assert response.status_code == 200
        data = response.json()
        assert data["armed"] is False


# =============================================================================
# Kill Switch Endpoint Tests
# =============================================================================


class TestKillSwitchEndpoint:
    """Tests for kill switch endpoints."""

    def test_activate_kill_switch(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should activate kill switch."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")
        api_client.post("/execution/arm", json={"confirm": True})

        response = api_client.post(
            "/execution/kill-switch/activate",
            json={"reason": "test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify state
        status = api_client.get("/execution/status").json()
        assert status["kill_switch_active"] is True
        assert status["armed"] is False

    def test_reset_kill_switch(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should reset kill switch."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")
        api_client.post(
            "/execution/kill-switch/activate",
            json={"reason": "test"},
        )

        response = api_client.post("/execution/kill-switch/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        status = api_client.get("/execution/status").json()
        assert status["kill_switch_active"] is False

    def test_arm_blocked_by_kill_switch(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should not arm when kill switch is active."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")
        api_client.post(
            "/execution/kill-switch/activate",
            json={"reason": "test"},
        )

        response = api_client.post("/execution/arm", json={"confirm": True})

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "kill switch" in data["error"].lower()


# =============================================================================
# Positions Endpoint Tests
# =============================================================================


class TestPositionsEndpoint:
    """Tests for GET /execution/positions endpoint."""

    def test_positions_requires_connection(self, api_client: TestClient) -> None:
        """Should fail when not connected."""
        response = api_client.get("/execution/positions")

        assert response.status_code == 400
        assert "connected" in response.json()["detail"].lower()

    def test_positions_returns_empty_list(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should return empty positions list when connected."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")

        response = api_client.get("/execution/positions")

        assert response.status_code == 200
        data = response.json()
        assert data["positions"] == []
        assert data["count"] == 0


# =============================================================================
# Run Once Endpoint Tests
# =============================================================================


class TestRunOnceEndpoint:
    """Tests for POST /execution/run-once endpoint."""

    def test_run_once_requires_connection(self, api_client: TestClient) -> None:
        """Should fail when not connected."""
        response = api_client.post(
            "/execution/run-once",
            json={
                "symbol": "EURUSD",
                "bot": "TestBot",
                "side": "BUY",
                "size": 0.1,
            },
        )

        assert response.status_code == 400

    def test_run_once_when_not_armed(
        self, api_client: TestClient, mock_ig_client: AsyncMock, overrider
    ) -> None:
        """Should record intent but not submit when not armed."""
        overrider.override(get_ig_client, lambda: mock_ig_client)

        api_client.post("/execution/connect")
        # Note: NOT arming

        response = api_client.post(
            "/execution/run-once",
            json={
                "symbol": "EURUSD",
                "bot": "TestBot",
                "side": "BUY",
                "size": 0.1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True  # Intent recorded
        assert data["status"] == "PENDING"  # Not submitted
