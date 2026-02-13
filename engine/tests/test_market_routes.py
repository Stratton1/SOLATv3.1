"""
Tests for market data API routes.

Tests endpoints for subscribing to realtime data.
Uses mocked IG client - NO REAL NETWORK CALLS.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.market_data_routes import get_catalogue_store
from solat_engine.config import get_settings_dep

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_market_service():
    """Reset market service singleton between tests."""
    from solat_engine.api import market_data_routes

    market_data_routes._market_service = None
    market_data_routes._catalogue_store = None
    yield
    market_data_routes._market_service = None
    market_data_routes._catalogue_store = None


@pytest.fixture
def mock_catalogue_with_epics():
    """Mock catalogue store with enriched items."""
    from solat_engine.catalog.models import AssetClass, InstrumentCatalogueItem

    items = [
        InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
            epic="CS.D.EURUSD.CFD.IP",
        ),
        InstrumentCatalogueItem(
            symbol="GBPUSD",
            display_name="GBP/USD",
            asset_class=AssetClass.FX,
            epic="CS.D.GBPUSD.CFD.IP",
        ),
        InstrumentCatalogueItem(
            symbol="USDJPY",
            display_name="USD/JPY",
            asset_class=AssetClass.FX,
            # No epic - not enriched
        ),
    ]

    mock_store = MagicMock()
    mock_store.load.return_value = items
    return mock_store


# =============================================================================
# Status Endpoint Tests
# =============================================================================


class TestMarketStatus:
    """Tests for /market/status endpoint."""

    def test_status_when_not_started(self, app_client: TestClient) -> None:
        """Status should show not connected when service not started."""
        response = app_client.get("/market/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["mode"] == "poll"
        assert data["subscriptions"] == []

    def test_status_includes_all_fields(self, app_client: TestClient) -> None:
        """Status response should include all expected fields."""
        response = app_client.get("/market/status")

        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert "mode" in data
        assert "stale" in data
        assert "subscriptions" in data
        assert "last_tick_ts" in data
        assert "reconnect_attempts" in data
        assert "last_error" in data


# =============================================================================
# Subscribe Endpoint Tests
# =============================================================================


class TestMarketSubscribe:
    """Tests for /market/subscribe endpoint."""

    def test_subscribe_requires_symbols(self, app_client: TestClient) -> None:
        """Subscribe should require at least one symbol."""
        response = app_client.post(
            "/market/subscribe",
            json={"symbols": [], "mode": "poll"},
        )

        assert response.status_code == 422  # Validation error

    def test_subscribe_validates_mode(self, app_client: TestClient) -> None:
        """Subscribe should reject invalid mode."""
        response = app_client.post(
            "/market/subscribe",
            json={"symbols": ["EURUSD"], "mode": "invalid"},
        )

        assert response.status_code == 400
        assert "Invalid mode" in response.json()["detail"]

    def test_subscribe_without_ig_credentials(self, app_client: TestClient, mock_settings: MagicMock, overrider) -> None:
        """Subscribe should fail gracefully without IG credentials."""
        mock_settings.has_ig_credentials = False
        overrider.override(get_settings_dep, lambda: mock_settings)

        response = app_client.post(
            "/market/subscribe",
            json={"symbols": ["EURUSD"], "mode": "poll"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "IG credentials not configured" in data["message"]

    def test_subscribe_symbol_not_in_catalogue(
        self, app_client: TestClient, mock_catalogue_with_epics, overrider
    ) -> None:
        """Subscribe should fail for symbol not in catalogue."""
        overrider.override(get_catalogue_store, lambda: mock_catalogue_with_epics)

        response = app_client.post(
            "/market/subscribe",
            json={"symbols": ["UNKNOWN"], "mode": "poll"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert len(data["failed"]) == 1
        assert data["failed"][0]["symbol"] == "UNKNOWN"
        assert "not in catalogue" in data["failed"][0]["error"]

    def test_subscribe_symbol_without_epic(self, app_client: TestClient, mock_catalogue_with_epics, overrider) -> None:
        """Subscribe should fail for symbol without epic mapping."""
        overrider.override(get_catalogue_store, lambda: mock_catalogue_with_epics)

        response = app_client.post(
            "/market/subscribe",
            json={"symbols": ["USDJPY"], "mode": "poll"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert len(data["failed"]) == 1
        assert "No epic mapping" in data["failed"][0]["error"]

    def test_subscribe_max_symbols_enforced(self, app_client: TestClient) -> None:
        """Subscribe should reject more than max symbols."""
        # Max is 20
        symbols = [f"SYM{i}" for i in range(25)]

        response = app_client.post(
            "/market/subscribe",
            json={"symbols": symbols, "mode": "poll"},
        )

        assert response.status_code == 422  # Validation error


# =============================================================================
# Unsubscribe Endpoint Tests
# =============================================================================


class TestMarketUnsubscribe:
    """Tests for /market/unsubscribe endpoint."""

    def test_unsubscribe_when_not_running(self, app_client: TestClient) -> None:
        """Unsubscribe should handle not-running service gracefully."""
        response = app_client.post(
            "/market/unsubscribe",
            json={"symbols": ["EURUSD"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "not running" in data["message"]

    def test_unsubscribe_all_with_empty_list(self, app_client: TestClient) -> None:
        """Empty symbols list should unsubscribe all."""
        response = app_client.post(
            "/market/unsubscribe",
            json={"symbols": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


# =============================================================================
# Quotes Endpoint Tests
# =============================================================================


class TestMarketQuotes:
    """Tests for /market/quotes endpoint."""

    def test_quotes_returns_empty_when_no_subscriptions(self, app_client: TestClient) -> None:
        """Quotes should return empty when nothing subscribed."""
        response = app_client.get("/market/quotes")

        assert response.status_code == 200
        data = response.json()
        assert data["quotes"] == {}
        assert data["count"] == 0

    def test_quotes_accepts_symbol_filter(self, app_client: TestClient) -> None:
        """Quotes should accept comma-separated symbol filter."""
        response = app_client.get("/market/quotes?symbols=EURUSD,GBPUSD")

        assert response.status_code == 200
        data = response.json()
        # Will be empty since no subscriptions, but filter is accepted
        assert isinstance(data["quotes"], dict)


# =============================================================================
# Stop Endpoint Tests
# =============================================================================


class TestMarketStop:
    """Tests for /market/stop endpoint."""

    def test_stop_when_not_running(self, app_client: TestClient) -> None:
        """Stop should handle not-running service gracefully."""
        response = app_client.post("/market/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "not running" in data["message"]


# =============================================================================
# Integration Tests
# =============================================================================


class TestMarketIntegration:
    """Integration tests for market data workflow."""

    def test_subscribe_unsubscribe_workflow(
        self, mock_catalogue_with_epics
    ) -> None:
        """Full subscribe/unsubscribe workflow."""
        # Skip if no way to mock IG client properly
        # This would be tested with a full mock setup
        pass

    def test_status_after_subscribe(self) -> None:
        """Status should reflect subscriptions after subscribe."""
        # Would need full mock setup
        pass
