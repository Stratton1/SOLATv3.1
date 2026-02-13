"""
Tests for IG and Catalog API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from solat_engine.broker.ig.types import (
    IGAccount,
    IGAccountStatus,
    IGAccountType,
    IGMarketSearchItem,
)
from solat_engine.catalog.store import CatalogueStore

# =============================================================================
# IG Endpoint Tests
# =============================================================================


class TestIGStatusEndpoint:
    """Tests for /ig/status endpoint."""

    def test_status_returns_200(self, app_client: TestClient) -> None:
        """Status endpoint should return 200 OK."""
        response = app_client.get("/ig/status")
        assert response.status_code == 200

    def test_status_returns_expected_fields(self, app_client: TestClient) -> None:
        """Status endpoint should return expected fields."""
        response = app_client.get("/ig/status")
        data = response.json()

        assert "configured" in data
        assert "mode" in data
        assert "base_url" in data
        assert "authenticated" in data
        assert "rate_limiter" in data
        assert "metrics" in data


class TestIGTestLoginEndpoint:
    """Tests for /ig/test-login endpoint."""

    def test_login_missing_credentials(
        self, app_client: TestClient, mock_settings: MagicMock
    ) -> None:
        """Test login without credentials should return failure."""
        mock_settings.ig_api_key = None
        mock_settings.ig_username = None
        mock_settings.ig_password = None

        response = app_client.post("/ig/test-login")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is False
        assert "not configured" in data["message"]


class TestIGAccountsEndpoint:
    """Tests for /ig/accounts endpoint."""

    def test_accounts_without_credentials(
        self, app_client: TestClient, mock_settings: MagicMock
    ) -> None:
        """Accounts endpoint without credentials should return 400."""
        mock_settings.has_ig_credentials = False

        response = app_client.get("/ig/accounts")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_accounts_success(
        self, app_client: TestClient, mock_ig_client: AsyncMock
    ) -> None:
        """Accounts endpoint should return account list."""
        mock_ig_client.get_accounts.return_value = [
            IGAccount(
                accountId="ABC123",
                accountName="Demo CFD",
                accountType=IGAccountType.CFD,
                status=IGAccountStatus.ENABLED,
                currency="GBP",
                preferred=True,
            )
        ]

        response = app_client.get("/ig/accounts")
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 1
        assert data["accounts"][0]["account_id"] == "ABC123"


class TestIGMarketsSearchEndpoint:
    """Tests for /ig/markets/search endpoint."""

    def test_search_without_credentials(
        self, app_client: TestClient, mock_settings: MagicMock
    ) -> None:
        """Search endpoint without credentials should return 400."""
        mock_settings.has_ig_credentials = False

        response = app_client.get("/ig/markets/search", params={"q": "EUR"})
        assert response.status_code == 400

    def test_search_without_query(self, app_client: TestClient) -> None:
        """Search endpoint without query should return 422."""
        response = app_client.get("/ig/markets/search")
        assert response.status_code == 422

    def test_search_success(
        self, app_client: TestClient, mock_ig_client: AsyncMock
    ) -> None:
        """Search endpoint should return market results."""
        mock_ig_client.search_markets.return_value = [
            IGMarketSearchItem(
                epic="CS.D.EURUSD.CFD.IP",
                instrumentName="EUR/USD",
                instrumentType="CURRENCIES",
            )
        ]

        response = app_client.get("/ig/markets/search", params={"q": "EUR/USD"})
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 1
        assert data["query"] == "EUR/USD"
        assert data["markets"][0]["epic"] == "CS.D.EURUSD.CFD.IP"


# =============================================================================
# Catalog Endpoint Tests
# =============================================================================


class TestCatalogSummaryEndpoint:
    """Tests for /catalog/summary endpoint."""

    def test_summary_returns_200(self, app_client: TestClient) -> None:
        """Summary endpoint should return 200 OK."""
        response = app_client.get("/catalog/summary")
        assert response.status_code == 200

    def test_summary_returns_expected_fields(self, app_client: TestClient) -> None:
        """Summary endpoint should return expected fields."""
        response = app_client.get("/catalog/summary")
        data = response.json()

        assert "total" in data
        assert "enriched" in data
        assert "by_asset_class" in data


class TestCatalogInstrumentsEndpoint:
    """Tests for /catalog/instruments endpoint."""

    def test_instruments_returns_200(self, app_client: TestClient) -> None:
        """Instruments endpoint should return 200 OK."""
        response = app_client.get("/catalog/instruments")
        assert response.status_code == 200

    def test_instruments_returns_expected_fields(self, app_client: TestClient) -> None:
        """Instruments endpoint should return expected fields."""
        response = app_client.get("/catalog/instruments")
        data = response.json()

        assert "instruments" in data
        assert "count" in data
        assert "enriched_count" in data

    def test_instruments_filter_by_asset_class(self, app_client: TestClient) -> None:
        """Instruments endpoint should filter by asset class."""
        response = app_client.get("/catalog/instruments", params={"asset_class": "fx"})
        assert response.status_code == 200

    def test_instruments_enriched_only(self, app_client: TestClient) -> None:
        """Instruments endpoint should filter enriched only."""
        response = app_client.get("/catalog/instruments", params={"enriched_only": "true"})
        assert response.status_code == 200


class TestCatalogInstrumentEndpoint:
    """Tests for /catalog/instruments/{symbol} endpoint."""

    def test_get_instrument_not_found(self, app_client: TestClient, overrider) -> None:
        """Get instrument should return 404 for missing symbol."""
        from solat_engine.api.catalog_routes import get_catalogue_store

        mock_store = MagicMock(spec=CatalogueStore)
        mock_store.get.return_value = None
        overrider.override(get_catalogue_store, lambda: mock_store)

        response = app_client.get("/catalog/instruments/NONEXISTENT")
        assert response.status_code == 404


class TestCatalogBootstrapEndpoint:
    """Tests for /catalog/bootstrap endpoint."""

    def test_bootstrap_returns_200(self, app_client: TestClient) -> None:
        """Bootstrap endpoint should return 200 OK."""
        response = app_client.post("/catalog/bootstrap", params={"enrich": "false"})
        assert response.status_code == 200

    def test_bootstrap_returns_expected_fields(self, app_client: TestClient) -> None:
        """Bootstrap endpoint should return expected fields."""
        response = app_client.post("/catalog/bootstrap", params={"enrich": "false"})
        data = response.json()

        assert "ok" in data
        assert "created" in data
        assert "total" in data
        assert "message" in data

    def test_bootstrap_is_idempotent(self, app_client: TestClient) -> None:
        """Bootstrap should be idempotent."""
        # First call
        response1 = app_client.post("/catalog/bootstrap", params={"enrich": "false"})
        data1 = response1.json()

        # Second call
        response2 = app_client.post("/catalog/bootstrap", params={"enrich": "false"})
        data2 = response2.json()

        # Total should be same
        assert data1["total"] == data2["total"]


class TestCatalogDeleteEndpoint:
    """Tests for /catalog/instruments/{symbol} DELETE endpoint."""

    def test_delete_not_found(self, app_client: TestClient, overrider) -> None:
        """Delete should return 404 for missing symbol."""
        from solat_engine.api.catalog_routes import get_catalogue_store

        mock_store = MagicMock(spec=CatalogueStore)
        mock_store.delete.return_value = False
        overrider.override(get_catalogue_store, lambda: mock_store)

        response = app_client.delete("/catalog/instruments/NONEXISTENT")
        assert response.status_code == 404

    def test_delete_success(self, app_client: TestClient, overrider) -> None:
        """Delete should return success for existing symbol."""
        from solat_engine.api.catalog_routes import get_catalogue_store

        mock_store = MagicMock(spec=CatalogueStore)
        mock_store.delete.return_value = True
        overrider.override(get_catalogue_store, lambda: mock_store)

        response = app_client.delete("/catalog/instruments/EURUSD")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["deleted"] == "EURUSD"
