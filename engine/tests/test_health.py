"""
Tests for health and config endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from solat_engine import __version__


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_200(self, app_client: TestClient) -> None:
        """Health endpoint should return 200 OK."""
        response = app_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status(self, app_client: TestClient) -> None:
        """Health endpoint should return status field."""
        response = app_client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_returns_version(self, app_client: TestClient) -> None:
        """Health endpoint should return version."""
        response = app_client.get("/health")
        data = response.json()
        assert data["version"] == __version__

    def test_health_returns_time(self, app_client: TestClient) -> None:
        """Health endpoint should return current time."""
        response = app_client.get("/health")
        data = response.json()
        assert "time" in data
        # Should be ISO format
        assert "T" in data["time"]

    def test_health_returns_uptime(self, app_client: TestClient) -> None:
        """Health endpoint should return uptime."""
        response = app_client.get("/health")
        data = response.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_health_returns_system_metrics(self, app_client: TestClient) -> None:
        """Health endpoint should return system metrics."""
        response = app_client.get("/health")
        data = response.json()
        assert "system" in data
        system = data["system"]
        assert "cpu_pct" in system
        assert "memory_usage_mb" in system
        assert "disk_free_gb" in system
        assert "process_id" in system
        assert system["cpu_pct"] == 5.0
        assert system["memory_usage_mb"] == 100.0
        assert system["disk_free_gb"] == 500.0


class TestConfigEndpoint:
    """Tests for /config endpoint."""

    def test_config_returns_200(self, app_client: TestClient) -> None:
        """Config endpoint should return 200 OK."""
        response = app_client.get("/config")
        assert response.status_code == 200

    def test_config_returns_mode(self, app_client: TestClient) -> None:
        """Config endpoint should return mode."""
        response = app_client.get("/config")
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ("DEMO", "LIVE")

    def test_config_returns_data_dir(self, app_client: TestClient) -> None:
        """Config endpoint should return data directory."""
        response = app_client.get("/config")
        data = response.json()
        assert "data_dir" in data

    def test_config_does_not_expose_secrets(self, app_client: TestClient) -> None:
        """Config endpoint should not expose sensitive values."""
        response = app_client.get("/config")
        data = response.json()
        # Should not contain actual credentials
        assert "api_key" not in str(data).lower()
        assert "password" not in str(data).lower()
        assert "secret" not in str(data).lower()


class TestRootEndpoint:
    """Tests for / endpoint."""

    def test_root_returns_200(self, app_client: TestClient) -> None:
        """Root endpoint should return 200 OK."""
        response = app_client.get("/")
        assert response.status_code == 200

    def test_root_returns_api_info(self, app_client: TestClient) -> None:
        """Root endpoint should return API information."""
        response = app_client.get("/")
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert data["version"] == __version__
