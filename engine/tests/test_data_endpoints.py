"""
Tests for data API endpoints.

Tests /data/bars, /data/sync, /data/summary endpoints.
Uses mocked IG responses - NO REAL IG CALLS.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_stores_and_cache():
    """Reset global stores and settings cache before each test."""
    from solat_engine.api import data_routes
    data_routes._parquet_store = None
    data_routes._catalogue_store = None
    from solat_engine.config import get_settings
    get_settings.cache_clear()


@pytest.fixture
def temp_data_dir():  # type: ignore[no-untyped-def]
    """Create a temporary data directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_client(temp_data_dir: Path):  # type: ignore[no-untyped-def]
    """Create a test client with mocked settings using dependency overrides."""
    from solat_engine.config import get_settings_dep
    from solat_engine.main import app

    # Create mocked settings
    settings = MagicMock()
    settings.mode.value = "DEMO"
    settings.env.value = "development"
    settings.data_dir = temp_data_dir
    settings.host = "localhost"
    settings.port = 8000
    settings.log_level = "INFO"
    settings.has_ig_credentials = False  # Default: no IG
    settings.history_max_rows_per_call = 5000
    settings.quality_gap_tolerance_multiplier = 1.5

    # Override dependency
    app.dependency_overrides[get_settings_dep] = lambda: settings

    # Reset singletons
    from solat_engine.api import data_routes
    data_routes._parquet_store = None
    data_routes._catalogue_store = None

    with TestClient(app) as client:
        yield client

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def populated_store(temp_data_dir: Path) -> ParquetStore:
    """Create a ParquetStore with test data."""
    store = ParquetStore(temp_data_dir)

    # Create test bars
    start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    bars = []
    for i in range(100):
        bar = HistoricalBar(
            timestamp_utc=start + timedelta(minutes=i),
            instrument_symbol="EURUSD",
            timeframe=SupportedTimeframe.M1,
            open=1.1000 + i * 0.0001,
            high=1.1010 + i * 0.0001,
            low=1.0990 + i * 0.0001,
            close=1.1005 + i * 0.0001,
            volume=100.0 + i,
        )
        bars.append(bar)

    store.write_bars(bars)
    return store


@pytest.fixture
def test_client_with_data(temp_data_dir: Path, populated_store: ParquetStore):  # type: ignore[no-untyped-def]
    """Create a test client with pre-populated data and dependency overrides."""
    from solat_engine.config import get_settings_dep
    from solat_engine.main import app

    # Create mocked settings
    settings = MagicMock()
    settings.mode.value = "DEMO"
    settings.env.value = "development"
    settings.data_dir = temp_data_dir
    settings.host = "localhost"
    settings.port = 8000
    settings.log_level = "INFO"
    settings.has_ig_credentials = False
    settings.history_max_rows_per_call = 5000
    settings.quality_gap_tolerance_multiplier = 1.5

    # Override dependency
    app.dependency_overrides[get_settings_dep] = lambda: settings

    # Reset and inject populated store
    from solat_engine.api import data_routes
    data_routes._parquet_store = populated_store
    data_routes._catalogue_store = None

    with TestClient(app) as client:
        yield client

    # Clear overrides
    app.dependency_overrides.clear()


# =============================================================================
# GET /data/bars Tests
# =============================================================================


class TestGetBars:
    """Tests for GET /data/bars endpoint."""

    def test_get_bars_returns_data(self, test_client_with_data: TestClient) -> None:
        """GET /data/bars should return stored bars."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "1m"
        assert data["count"] > 0
        assert len(data["bars"]) == data["count"]

    def test_get_bars_sorted_by_timestamp(
        self, test_client_with_data: TestClient
    ) -> None:
        """Returned bars should be sorted by timestamp."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m"},
        )

        data = response.json()
        timestamps = [b["ts"] for b in data["bars"]]
        assert timestamps == sorted(timestamps)

    def test_get_bars_with_limit(self, test_client_with_data: TestClient) -> None:
        """GET /data/bars with limit should cap results."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m", "limit": 25},
        )

        data = response.json()
        assert data["count"] == 25
        assert len(data["bars"]) == 25

    def test_get_bars_with_start_filter(
        self, test_client_with_data: TestClient
    ) -> None:
        """GET /data/bars with start should filter results."""
        # Start at 10:30 (skip first 30 bars)
        start = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        response = test_client_with_data.get(
            "/data/bars",
            params={
                "symbol": "EURUSD",
                "timeframe": "1m",
                "start": start.isoformat(),
            },
        )

        data = response.json()
        assert data["count"] == 70  # 100 total - 30 filtered
        # First bar should be at or after start
        first_ts = datetime.fromisoformat(data["bars"][0]["ts"])
        assert first_ts >= start

    def test_get_bars_with_end_filter(self, test_client_with_data: TestClient) -> None:
        """GET /data/bars with end should filter results."""
        # End at 10:30 (first 30 bars)
        end = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        response = test_client_with_data.get(
            "/data/bars",
            params={
                "symbol": "EURUSD",
                "timeframe": "1m",
                "end": end.isoformat(),
            },
        )

        data = response.json()
        assert data["count"] == 30
        # Last bar should be before end
        last_ts = datetime.fromisoformat(data["bars"][-1]["ts"])
        assert last_ts < end

    def test_get_bars_empty_symbol(self, test_client_with_data: TestClient) -> None:
        """GET /data/bars for unknown symbol should return empty."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "NONEXISTENT", "timeframe": "1m"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["bars"] == []

    def test_get_bars_invalid_timeframe(
        self, test_client_with_data: TestClient
    ) -> None:
        """GET /data/bars with invalid timeframe should return 400."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "invalid"},
        )

        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]

    def test_get_bars_ohlcv_values(self, test_client_with_data: TestClient) -> None:
        """Returned bars should have correct OHLCV values."""
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m", "limit": 1},
        )

        data = response.json()
        bar = data["bars"][0]

        assert "ts" in bar
        assert "o" in bar
        assert "h" in bar
        assert "l" in bar
        assert "c" in bar
        assert "v" in bar
        assert isinstance(bar["o"], (int, float))


# =============================================================================
# GET /data/summary Tests
# =============================================================================


class TestGetSummary:
    """Tests for GET /data/summary endpoint."""

    def test_get_summary_returns_data(
        self, test_client_with_data: TestClient
    ) -> None:
        """GET /data/summary should return summaries."""
        response = test_client_with_data.get("/data/summary")

        assert response.status_code == 200
        data = response.json()
        assert "summaries" in data
        assert "total_symbols" in data
        assert "total_bars" in data
        assert data["total_symbols"] >= 1

    def test_get_summary_filter_symbol(
        self, test_client_with_data: TestClient
    ) -> None:
        """GET /data/summary with symbol filter should filter results."""
        response = test_client_with_data.get(
            "/data/summary",
            params={"symbol": "EURUSD"},
        )

        data = response.json()
        for summary in data["summaries"]:
            assert summary["symbol"] == "EURUSD"

    def test_get_summary_filter_timeframe(
        self, test_client_with_data: TestClient
    ) -> None:
        """GET /data/summary with timeframe filter should filter results."""
        response = test_client_with_data.get(
            "/data/summary",
            params={"timeframe": "1m"},
        )

        data = response.json()
        for summary in data["summaries"]:
            assert summary["timeframe"] == "1m"

    def test_get_summary_empty(self, test_client: TestClient) -> None:
        """GET /data/summary with no data should return empty."""
        response = test_client.get("/data/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["summaries"] == []
        assert data["total_symbols"] == 0
        assert data["total_bars"] == 0


# =============================================================================
# DELETE /data/bars Tests
# =============================================================================


class TestDeleteBars:
    """Tests for DELETE /data/bars endpoint."""

    def test_delete_bars_success(self, test_client_with_data: TestClient) -> None:
        """DELETE /data/bars should delete data."""
        # Verify data exists
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m"},
        )
        assert response.json()["count"] > 0

        # Delete
        response = test_client_with_data.delete("/data/bars/EURUSD/1m")
        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify deleted
        response = test_client_with_data.get(
            "/data/bars",
            params={"symbol": "EURUSD", "timeframe": "1m"},
        )
        assert response.json()["count"] == 0

    def test_delete_bars_not_found(self, test_client: TestClient) -> None:
        """DELETE /data/bars for unknown symbol should return 404."""
        response = test_client.delete("/data/bars/NONEXISTENT/1m")

        assert response.status_code == 404

    def test_delete_bars_invalid_timeframe(self, test_client: TestClient) -> None:
        """DELETE /data/bars with invalid timeframe should return 400."""
        response = test_client.delete("/data/bars/EURUSD/invalid")

        assert response.status_code == 400


# =============================================================================
# POST /data/sync Tests
# =============================================================================


class TestSyncEndpoint:
    """Tests for POST /data/sync endpoint."""

    def test_sync_without_ig_credentials(self, test_client: TestClient) -> None:
        """POST /data/sync without IG credentials should fail gracefully."""
        response = test_client.post(
            "/data/sync",
            json={
                "symbols": ["EURUSD"],
                "timeframes": ["1m"],
                "start": "2024-01-15T00:00:00Z",
                "end": "2024-01-15T01:00:00Z",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "IG credentials not configured" in data["message"]

    def test_sync_invalid_timeframe(self, test_client: TestClient) -> None:
        """POST /data/sync with invalid timeframe should return 400."""
        response = test_client.post(
            "/data/sync",
            json={
                "symbols": ["EURUSD"],
                "timeframes": ["invalid"],
                "start": "2024-01-15T00:00:00Z",
                "end": "2024-01-15T01:00:00Z",
            },
        )

        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]

    def test_sync_empty_symbols(self, test_client: TestClient) -> None:
        """POST /data/sync with empty symbols should return 422."""
        response = test_client.post(
            "/data/sync",
            json={
                "symbols": [],  # Empty
                "timeframes": ["1m"],
                "start": "2024-01-15T00:00:00Z",
                "end": "2024-01-15T01:00:00Z",
            },
        )

        assert response.status_code == 422  # Validation error


class TestSyncWithMockedIG:
    """Tests for sync with mocked IG client."""

    def test_sync_starts_job(self, temp_data_dir: Path) -> None:
        """POST /data/sync should start a background job."""
        # Reset singletons first
        from solat_engine.api import data_routes

        data_routes._parquet_store = None
        data_routes._catalogue_store = None

        from solat_engine.main import app

        # Mock settings, IG client, catalogue, and job runner
        with (
            patch("solat_engine.api.data_routes.get_settings") as mock_settings,
            patch("solat_engine.api.data_routes.get_ig_client") as mock_ig,
            patch("solat_engine.api.data_routes.get_catalogue_store") as mock_cat,
            patch("solat_engine.api.data_routes.get_job_runner") as mock_runner,
        ):
            # Setup settings mock
            settings = MagicMock()
            settings.mode.value = "DEMO"
            settings.env.value = "development"
            settings.data_dir = temp_data_dir
            settings.host = "localhost"
            settings.port = 8000
            settings.log_level = "INFO"
            settings.has_ig_credentials = True
            settings.history_max_rows_per_call = 5000
            settings.quality_gap_tolerance_multiplier = 1.5
            mock_settings.return_value = settings

            # Setup IG client mock
            mock_client = MagicMock()
            mock_ig.return_value = mock_client

            # Setup catalogue mock
            mock_store = MagicMock()
            mock_store.load.return_value = []
            mock_cat.return_value = mock_store

            # Mock job runner to return a run_id
            mock_job_runner = MagicMock()
            mock_job_runner.start_sync_job = AsyncMock(return_value="test-run-id")
            mock_runner.return_value = mock_job_runner

            with TestClient(app) as client:
                response = client.post(
                    "/data/sync",
                    json={
                        "symbols": ["EURUSD"],
                        "timeframes": ["1m"],
                        "start": "2024-01-15T00:00:00Z",
                        "end": "2024-01-15T01:00:00Z",
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is True
                assert data["run_id"] != ""


# =============================================================================
# GET /data/sync/{run_id} Tests
# =============================================================================


class TestGetSyncResult:
    """Tests for GET /data/sync/{run_id} endpoint."""

    def test_get_sync_result_not_found(self, test_client: TestClient) -> None:
        """GET /data/sync/{run_id} for unknown job should return 404."""
        response = test_client.get("/data/sync/nonexistent-run-id")

        assert response.status_code == 404


# =============================================================================
# POST /data/sync/quick Tests
# =============================================================================


class TestQuickSync:
    """Tests for POST /data/sync/quick endpoint."""

    def test_quick_sync_without_ig_credentials(self, test_client: TestClient) -> None:
        """POST /data/sync/quick without IG credentials should fail gracefully."""
        response = test_client.post("/data/sync/quick")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "IG credentials not configured" in data["message"]

    def test_quick_sync_no_enriched_symbols(self, temp_data_dir: Path) -> None:
        """POST /data/sync/quick with no enriched symbols should fail."""
        from solat_engine.api.data_routes import get_catalogue_store
        from solat_engine.config import get_settings_dep
        from solat_engine.main import app

        # Setup mocked settings
        settings = MagicMock()
        settings.mode.value = "DEMO"
        settings.env.value = "development"
        settings.data_dir = temp_data_dir
        settings.host = "localhost"
        settings.port = 8000
        settings.log_level = "INFO"
        settings.has_ig_credentials = True
        settings.history_max_rows_per_call = 5000
        settings.quality_gap_tolerance_multiplier = 1.5

        # Setup mocked catalogue
        mock_catalogue = MagicMock()
        mock_catalogue.load.return_value = [] # Empty catalogue

        # Apply overrides
        app.dependency_overrides[get_settings_dep] = lambda: settings
        app.dependency_overrides[get_catalogue_store] = lambda: mock_catalogue

        try:
            with TestClient(app) as client:
                response = client.post("/data/sync/quick")

                assert response.status_code == 200
                data = response.json()
                assert data["ok"] is False
                assert "No enriched instruments" in data["message"]
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests
# =============================================================================


class TestDataEndpointsIntegration:
    """Integration tests for data endpoints."""

    def test_write_then_read_flow(self, temp_data_dir: Path) -> None:
        """Writing data then reading should return consistent results."""
        # Create store and write data
        store = ParquetStore(temp_data_dir)
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = []
        for i in range(50):
            bar = HistoricalBar(
                timestamp_utc=start + timedelta(minutes=i),
                instrument_symbol="GBPUSD",
                timeframe=SupportedTimeframe.M1,
                open=1.2500 + i * 0.0001,
                high=1.2510 + i * 0.0001,
                low=1.2490 + i * 0.0001,
                close=1.2505 + i * 0.0001,
                volume=200.0 + i,
            )
            bars.append(bar)
        store.write_bars(bars)

        # Create client with this store
        with patch("solat_engine.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.mode.value = "DEMO"
            settings.env.value = "development"
            settings.data_dir = temp_data_dir
            settings.host = "localhost"
            settings.port = 8000
            settings.log_level = "INFO"
            settings.has_ig_credentials = False
            settings.history_max_rows_per_call = 5000
            settings.quality_gap_tolerance_multiplier = 1.5
            mock_settings.return_value = settings

            from solat_engine.api import data_routes

            data_routes._parquet_store = store
            data_routes._catalogue_store = None

            from solat_engine.main import app

            with TestClient(app) as client:
                # Read via API
                response = client.get(
                    "/data/bars",
                    params={"symbol": "GBPUSD", "timeframe": "1m"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["count"] == 50
                assert data["symbol"] == "GBPUSD"

                # Check summary
                response = client.get("/data/summary")
                assert response.status_code == 200
                summary = response.json()
                assert summary["total_bars"] == 50
