"""
Tests for backtest API endpoints.

Tests /backtest/run, /backtest/status, /backtest/results endpoints.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_client(temp_data_dir: Path):
    """Create a test client with mocked settings."""
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

        # Reset singletons
        from solat_engine.api import backtest_routes, data_routes

        data_routes._parquet_store = None
        data_routes._catalogue_store = None
        backtest_routes._parquet_store = None
        backtest_routes._job_results.clear()
        backtest_routes._active_jobs.clear()

        from solat_engine.main import app

        with TestClient(app) as client:
            yield client


@pytest.fixture
def populated_store(temp_data_dir: Path) -> ParquetStore:
    """Create a ParquetStore with test data."""
    store = ParquetStore(temp_data_dir)

    # Create test bars
    start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    bars = []
    for i in range(200):
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


# =============================================================================
# GET /backtest/bots Tests
# =============================================================================


class TestBotsEndpoint:
    """Tests for GET /backtest/bots endpoint."""

    def test_list_bots(self, test_client: TestClient) -> None:
        """Should return list of available bots."""
        response = test_client.get("/backtest/bots")

        assert response.status_code == 200
        data = response.json()
        assert "bots" in data
        assert len(data["bots"]) == 9  # Elite 8 + ChikouKaizen

        # Check bot structure
        bot = data["bots"][0]
        assert "name" in bot
        assert "description" in bot


# =============================================================================
# POST /backtest/run Tests
# =============================================================================


class TestRunEndpoint:
    """Tests for POST /backtest/run endpoint."""

    def test_run_returns_run_id(self, test_client: TestClient) -> None:
        """Should return run_id when starting backtest."""
        response = test_client.post(
            "/backtest/run",
            json={
                "symbols": ["EURUSD"],
                "timeframe": "1m",
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
                "bots": ["TKCrossSniper"],
                "initial_cash": 100000,
                "warmup_bars": 50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "run_id" in data
        assert len(data["run_id"]) > 0

    def test_run_invalid_bot_returns_400(self, test_client: TestClient) -> None:
        """Should return 400 for invalid bot name."""
        response = test_client.post(
            "/backtest/run",
            json={
                "symbols": ["EURUSD"],
                "timeframe": "1m",
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
                "bots": ["InvalidBotName"],
                "initial_cash": 100000,
            },
        )

        assert response.status_code == 400
        assert "Invalid bots" in response.json()["detail"]

    def test_run_empty_symbols_returns_422(self, test_client: TestClient) -> None:
        """Should return 422 for empty symbols."""
        response = test_client.post(
            "/backtest/run",
            json={
                "symbols": [],
                "timeframe": "1m",
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
                "bots": ["TKCrossSniper"],
                "initial_cash": 100000,
            },
        )

        assert response.status_code == 422


# =============================================================================
# GET /backtest/status Tests
# =============================================================================


class TestStatusEndpoint:
    """Tests for GET /backtest/status endpoint."""

    def test_status_not_found(self, test_client: TestClient) -> None:
        """Should return 404 for unknown run_id."""
        response = test_client.get("/backtest/status", params={"run_id": "nonexistent"})

        assert response.status_code == 404

    def test_status_returns_running(self, test_client: TestClient) -> None:
        """Should return running status for active job."""
        # Start a job
        run_response = test_client.post(
            "/backtest/run",
            json={
                "symbols": ["EURUSD"],
                "timeframe": "1m",
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
                "bots": ["TKCrossSniper"],
                "initial_cash": 100000,
                "warmup_bars": 50,
            },
        )

        run_id = run_response.json()["run_id"]

        # Check status (might be running or done depending on speed)
        response = test_client.get("/backtest/status", params={"run_id": run_id})

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["status"] in ["running", "done", "failed"]


# =============================================================================
# GET /backtest/results Tests
# =============================================================================


class TestResultsEndpoint:
    """Tests for GET /backtest/results endpoint."""

    def test_results_not_found(self, test_client: TestClient) -> None:
        """Should return 404 for unknown run_id."""
        response = test_client.get("/backtest/results", params={"run_id": "nonexistent"})

        assert response.status_code == 404


# =============================================================================
# Integration Tests with Mocked Engine
# =============================================================================


class TestBacktestIntegration:
    """Integration tests with mocked backtest engine."""

    def test_full_backtest_flow(self, temp_data_dir: Path) -> None:
        """Test complete backtest flow with populated data."""
        # Create populated store
        store = ParquetStore(temp_data_dir)
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = []
        for i in range(200):
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

        # Create test client with this data
        with patch("solat_engine.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.mode.value = "DEMO"
            settings.env.value = "development"
            settings.data_dir = temp_data_dir
            settings.host = "localhost"
            settings.port = 8000
            settings.log_level = "INFO"
            settings.has_ig_credentials = False
            mock_settings.return_value = settings

            # Reset singletons
            from solat_engine.api import backtest_routes, data_routes

            data_routes._parquet_store = None
            backtest_routes._parquet_store = None
            backtest_routes._job_results.clear()
            backtest_routes._active_jobs.clear()

            from solat_engine.main import app

            with TestClient(app) as client:
                # Start backtest
                run_response = client.post(
                    "/backtest/run",
                    json={
                        "symbols": ["EURUSD"],
                        "timeframe": "1m",
                        "start": "2024-01-15T10:00:00Z",
                        "end": "2024-01-15T13:20:00Z",
                        "bots": ["MomentumRider"],
                        "initial_cash": 100000,
                        "warmup_bars": 50,
                    },
                )

                assert run_response.status_code == 200
                run_id = run_response.json()["run_id"]

                # Wait a bit for job to complete (in test, runs synchronously)
                import time

                time.sleep(0.5)

                # Check status
                status_response = client.get("/backtest/status", params={"run_id": run_id})
                assert status_response.status_code == 200


# =============================================================================
# Sweep Endpoint Tests
# =============================================================================


class TestSweepEndpoint:
    """Tests for sweep endpoints."""

    def test_sweep_returns_sweep_id(self, test_client: TestClient) -> None:
        """Should return sweep_id when starting sweep."""
        response = test_client.post(
            "/backtest/sweep",
            json={
                "bots": ["TKCrossSniper"],
                "symbols": ["EURUSD"],
                "timeframes": ["1m"],
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
                "initial_cash": 100000,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "sweep_id" in data
        assert data["total_combos"] == 1  # 1 bot × 1 symbol × 1 timeframe

    def test_sweep_invalid_bot_returns_400(self, test_client: TestClient) -> None:
        """Should return 400 for invalid bot name."""
        response = test_client.post(
            "/backtest/sweep",
            json={
                "bots": ["InvalidBot"],
                "symbols": ["EURUSD"],
                "timeframes": ["1m"],
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T13:00:00Z",
            },
        )

        assert response.status_code == 400

    def test_sweep_status_not_found(self, test_client: TestClient) -> None:
        """Should return 404 for unknown sweep_id."""
        response = test_client.get("/backtest/sweep/status", params={"sweep_id": "nonexistent"})

        assert response.status_code == 404


# =============================================================================
# Event-loop Safety Tests
# =============================================================================


class TestNoRunningEventLoopFix:
    """Verify backtest completes without 'no running event loop' error."""

    def test_backtest_completes_without_event_loop_error(self, temp_data_dir: Path) -> None:
        """Full backtest must finish with status=done, never 'no running event loop'."""
        import time

        store = ParquetStore(temp_data_dir)
        start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        bars = []
        for i in range(200):
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

        with patch("solat_engine.config.get_settings") as mock_settings:
            settings = MagicMock()
            settings.mode.value = "DEMO"
            settings.env.value = "development"
            settings.data_dir = temp_data_dir
            settings.host = "localhost"
            settings.port = 8000
            settings.log_level = "INFO"
            settings.has_ig_credentials = False
            mock_settings.return_value = settings

            from solat_engine.api import backtest_routes, data_routes

            data_routes._parquet_store = None
            backtest_routes._parquet_store = None
            backtest_routes._job_results.clear()
            backtest_routes._active_jobs.clear()

            from solat_engine.main import app

            with TestClient(app) as client:
                run_resp = client.post(
                    "/backtest/run",
                    json={
                        "symbols": ["EURUSD"],
                        "timeframe": "1m",
                        "start": "2024-01-15T10:00:00Z",
                        "end": "2024-01-15T13:20:00Z",
                        "bots": ["MomentumRider"],
                        "initial_cash": 100000,
                        "warmup_bars": 50,
                    },
                )
                assert run_resp.status_code == 200
                run_id = run_resp.json()["run_id"]

                # Poll until done or failed (max 10s)
                final_status = None
                for _ in range(20):
                    time.sleep(0.5)
                    s = client.get("/backtest/status", params={"run_id": run_id})
                    assert s.status_code == 200
                    data = s.json()
                    if data["status"] in ("done", "failed"):
                        final_status = data
                        break

                assert final_status is not None, "Backtest did not complete within 10s"
                assert final_status["status"] == "done", (
                    f"Backtest failed: {final_status.get('message', '')} "
                    f"error_type={final_status.get('error_type', 'N/A')}"
                )

                # Verify results endpoint works too
                results_resp = client.get("/backtest/results", params={"run_id": run_id})
                assert results_resp.status_code == 200
                assert results_resp.json()["ok"] is True
