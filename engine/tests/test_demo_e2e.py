"""
Demo E2E Integration Test.

Exercises the full DEMO trading flow using a deterministic fake IG transport:
  Connect → Enable Signals → Set Allowlist → Arm → Run Once → Check Fills/Events → Disarm
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client, reset_execution_state
from solat_engine.config import get_settings_dep
from solat_engine.main import app
from tests.chaos.fixtures.fake_ig import FakeIGClient


class TestDemoE2EFlow:
    """Full end-to-end demo flow with fake IG broker."""

    def test_full_demo_flow(self, overrider, mock_settings, tmp_path: Path) -> None:
        """Connect → mode → allowlist → arm → run-once → fills → events → disarm."""
        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient(balance=10000.0)

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            # 1. Connect
            resp = client.post("/execution/connect")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["account_id"] == "FAKE_DEMO_001"

            # 2. Enable signals + demo arm
            resp = client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["signals_enabled"] is True
            assert data["demo_arm_enabled"] is True

            # 3. Set allowlist
            resp = client.post(
                "/execution/allowlist",
                json={"symbols": ["EURUSD"]},
            )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

            # 4. Arm
            resp = client.post(
                "/execution/arm",
                json={"confirm": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["armed"] is True

            # 5. Run once
            resp = client.post(
                "/execution/run-once",
                json={
                    "symbol": "EURUSD",
                    "bot": "CloudTwist",
                    "side": "BUY",
                    "size": 0.1,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["deal_id"] is not None
            assert data["status"] == "FILLED"

            # 6. Check fills
            resp = client.get("/execution/fills")
            assert resp.status_code == 200
            fills = resp.json()
            assert fills["total"] >= 1

            # 7. Check events
            resp = client.get("/execution/events")
            assert resp.status_code == 200
            events = resp.json()
            assert events["total"] >= 1

            # 8. Check orders
            resp = client.get("/execution/orders")
            assert resp.status_code == 200
            orders = resp.json()
            assert orders["total"] >= 1

            # 9. Verify status reflects the trade
            resp = client.get("/execution/status")
            assert resp.status_code == 200
            status = resp.json()
            assert status["connected"] is True
            assert status["armed"] is True
            assert status["trades_this_hour"] >= 1

            # 10. Disarm
            resp = client.post("/execution/disarm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["armed"] is False

    def test_run_once_blocked_without_arm(
        self, overrider, mock_settings, tmp_path: Path
    ) -> None:
        """Run-once should fail if DEMO arm is not enabled."""
        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient()

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            # Connect but don't arm
            client.post("/execution/connect")

            resp = client.post(
                "/execution/run-once",
                json={
                    "symbol": "EURUSD",
                    "bot": "CloudTwist",
                    "side": "BUY",
                    "size": 0.1,
                },
            )
            # Should fail with 400 because demo_arm not enabled
            assert resp.status_code == 400

    def test_run_once_blocked_by_kill_switch(
        self, overrider, mock_settings, tmp_path: Path
    ) -> None:
        """Run-once should fail if kill switch is active."""
        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient()

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            client.post("/execution/connect")
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            client.post("/execution/allowlist", json={"symbols": ["EURUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            # Activate kill switch
            resp = client.post(
                "/execution/kill-switch/activate",
                json={"reason": "test"},
            )
            assert resp.status_code == 200

            # Run once should get rejected
            resp = client.post(
                "/execution/run-once",
                json={
                    "symbol": "EURUSD",
                    "bot": "CloudTwist",
                    "side": "BUY",
                    "size": 0.1,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is False

    def test_run_once_symbol_not_allowlisted(
        self, overrider, mock_settings, tmp_path: Path
    ) -> None:
        """Run-once should reject symbol not in allowlist."""
        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient()

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            client.post("/execution/connect")
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            # Only GBPUSD in allowlist
            client.post("/execution/allowlist", json={"symbols": ["GBPUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            resp = client.post(
                "/execution/run-once",
                json={
                    "symbol": "EURUSD",
                    "bot": "CloudTwist",
                    "side": "BUY",
                    "size": 0.1,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is False

    def test_broker_failure_handled_gracefully(
        self, overrider, mock_settings, tmp_path: Path
    ) -> None:
        """Run-once should handle broker failures without crashing."""
        reset_execution_state()

        mock_settings.data_dir = tmp_path
        fake_ig = FakeIGClient()
        fake_ig.fail_next_order(ConnectionError("Broker timeout"))

        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: fake_ig)

        with TestClient(app) as client:
            client.post("/execution/connect")
            client.post(
                "/execution/mode",
                json={"signals_enabled": True, "demo_arm_enabled": True},
            )
            client.post("/execution/allowlist", json={"symbols": ["EURUSD"]})
            client.post("/execution/arm", json={"confirm": True})

            resp = client.post(
                "/execution/run-once",
                json={
                    "symbol": "EURUSD",
                    "bot": "CloudTwist",
                    "side": "BUY",
                    "size": 0.1,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is False
            assert "timeout" in (data.get("error") or "").lower()
