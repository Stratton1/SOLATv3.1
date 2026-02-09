"""
Tests for health and config endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from solat_engine import __version__
from solat_engine.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Health endpoint should return 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status(self, client: TestClient) -> None:
        """Health endpoint should return status field."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_returns_version(self, client: TestClient) -> None:
        """Health endpoint should return version."""
        response = client.get("/health")
        data = response.json()
        assert data["version"] == __version__

    def test_health_returns_time(self, client: TestClient) -> None:
        """Health endpoint should return current time."""
        response = client.get("/health")
        data = response.json()
        assert "time" in data
        # Should be ISO format
        assert "T" in data["time"]

    def test_health_returns_uptime(self, client: TestClient) -> None:
        """Health endpoint should return uptime."""
        response = client.get("/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0


class TestConfigEndpoint:
    """Tests for /config endpoint."""

    def test_config_returns_200(self, client: TestClient) -> None:
        """Config endpoint should return 200 OK."""
        response = client.get("/config")
        assert response.status_code == 200

    def test_config_returns_mode(self, client: TestClient) -> None:
        """Config endpoint should return mode."""
        response = client.get("/config")
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ("DEMO", "LIVE")

    def test_config_returns_data_dir(self, client: TestClient) -> None:
        """Config endpoint should return data directory."""
        response = client.get("/config")
        data = response.json()
        assert "data_dir" in data

    def test_config_does_not_expose_secrets(self, client: TestClient) -> None:
        """Config endpoint should not expose sensitive values."""
        response = client.get("/config")
        data = response.json()
        # Should not contain actual credentials
        assert "api_key" not in str(data).lower()
        assert "password" not in str(data).lower()
        assert "secret" not in str(data).lower()


class TestRootEndpoint:
    """Tests for / endpoint."""

    def test_root_returns_200(self, client: TestClient) -> None:
        """Root endpoint should return 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_returns_api_info(self, client: TestClient) -> None:
        """Root endpoint should return API information."""
        response = client.get("/")
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["version"] == __version__
