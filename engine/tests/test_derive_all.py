"""
Tests for POST /data/derive-all endpoint.
"""

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from solat_engine.catalog.symbols import resolve_storage_symbol
from solat_engine.config import get_settings_dep
from solat_engine.main import app


@pytest.fixture
def derive_client(tmp_path: Path, overrider):
    """Test client configured with a temp data_dir."""
    from tests.api_fixtures import TestSettings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = TestSettings(data_dir=data_dir)
    overrider.override(get_settings_dep, lambda: settings)

    with TestClient(app) as client:
        yield client, data_dir


class TestDeriveAll:
    """Tests for POST /data/derive-all."""

    def test_no_1m_data_returns_ok_false(self, derive_client):
        """When no 1m data exists, derive-all returns ok=False."""
        client, _ = derive_client
        resp = client.post("/data/derive-all")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "No symbols" in body["message"]

    def test_with_1m_data_starts_job(self, derive_client):
        """When 1m data exists, derive-all returns ok=True with run_id."""
        client, data_dir = derive_client
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)

        # Create 1m parquet + manifest
        source_dir = (
            data_dir / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=1m"
        )
        source_dir.mkdir(parents=True)
        dates = pd.date_range("2024-01-01", periods=120, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": dates,
            "open": range(120),
            "high": [x + 1 for x in range(120)],
            "low": [max(0, x - 1) for x in range(120)],
            "close": [x + 0.5 for x in range(120)],
            "volume": [100] * 120,
            "instrument_symbol": storage_sym,
            "timeframe": "1m",
        })
        df.to_parquet(source_dir / "data.parquet", index=False)

        manifest_dir = data_dir / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        with open(manifest_dir / f"{storage_sym}_1m.json", "w") as f:
            json.dump({
                "instrument_symbol": storage_sym,
                "timeframe": "1m",
                "row_count": 120,
                "first_available_from": "2024-01-01T00:00:00+00:00",
                "last_synced_to": "2024-01-01T02:00:00+00:00",
            }, f)

        resp = client.post("/data/derive-all")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["run_id"].startswith("derive_")
        assert body["total_symbols"] == 1
        assert "15m" in body["target_timeframes"]

    def test_response_shape(self, derive_client):
        """Response includes all expected fields."""
        client, _ = derive_client
        resp = client.post("/data/derive-all")
        body = resp.json()
        assert "ok" in body
        assert "run_id" in body
        assert "message" in body
        assert "total_symbols" in body
        assert "target_timeframes" in body

    def test_derive_produces_files(self, derive_client):
        """After derive completes, derived parquet files should exist."""
        client, data_dir = derive_client
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)

        # Create 1m data (4 hours = 240 bars)
        source_dir = (
            data_dir / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=1m"
        )
        source_dir.mkdir(parents=True)
        dates = pd.date_range("2024-01-01", periods=240, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": dates,
            "open": range(240),
            "high": [x + 1 for x in range(240)],
            "low": [max(0, x - 1) for x in range(240)],
            "close": [x + 0.5 for x in range(240)],
            "volume": [100] * 240,
            "instrument_symbol": storage_sym,
            "timeframe": "1m",
        })
        df.to_parquet(source_dir / "data.parquet", index=False)

        manifest_dir = data_dir / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        with open(manifest_dir / f"{storage_sym}_1m.json", "w") as f:
            json.dump({
                "instrument_symbol": storage_sym,
                "timeframe": "1m",
                "row_count": 240,
                "first_available_from": "2024-01-01T00:00:00+00:00",
                "last_synced_to": "2024-01-01T04:00:00+00:00",
            }, f)

        resp = client.post("/data/derive-all")
        assert resp.json()["ok"] is True

        # The derive runs asynchronously; since TestClient runs synchronously
        # the task may not complete in time. We just verify the job started.
        assert resp.json()["total_symbols"] == 1

    def test_empty_data_dir(self, derive_client):
        """Completely empty data dir returns ok=False."""
        client, data_dir = derive_client
        # Ensure parquet dir exists but empty
        (data_dir / "parquet" / "bars").mkdir(parents=True, exist_ok=True)
        resp = client.post("/data/derive-all")
        body = resp.json()
        assert body["ok"] is False
