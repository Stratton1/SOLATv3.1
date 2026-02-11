"""
Tests for GET /data/artefacts/index endpoint.
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
def index_client(tmp_path: Path, overrider):
    """Test client configured with a temp data_dir."""
    from tests.api_fixtures import TestSettings

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = TestSettings(data_dir=data_dir)
    overrider.override(get_settings_dep, lambda: settings)

    with TestClient(app) as client:
        yield client, data_dir


class TestArtefactIndex:
    """Tests for GET /data/artefacts/index."""

    def test_empty_dir(self, index_client):
        """Empty data dir returns empty lists."""
        client, _ = index_client
        resp = client.get("/data/artefacts/index")
        assert resp.status_code == 200
        body = resp.json()
        assert body["bars"] == []
        assert body["backtests"] == []
        assert body["sweeps"] == []
        assert "generated_at" in body

    def test_bars_populated(self, index_client):
        """Bars section reflects stored bar data."""
        client, data_dir = index_client
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)

        # Create bar data with manifest
        source_dir = (
            data_dir / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=1h"
        )
        source_dir.mkdir(parents=True)
        dates = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": dates,
            "open": range(100),
            "high": [x + 1 for x in range(100)],
            "low": [max(0, x - 1) for x in range(100)],
            "close": [x + 0.5 for x in range(100)],
            "volume": [100] * 100,
            "instrument_symbol": storage_sym,
            "timeframe": "1h",
        })
        df.to_parquet(source_dir / "data.parquet", index=False)

        manifest_dir = data_dir / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        with open(manifest_dir / f"{storage_sym}_1h.json", "w") as f:
            json.dump({
                "instrument_symbol": storage_sym,
                "timeframe": "1h",
                "row_count": 100,
                "first_available_from": "2024-01-01T00:00:00+00:00",
                "last_synced_to": "2024-01-05T04:00:00+00:00",
            }, f)

        resp = client.get("/data/artefacts/index")
        body = resp.json()
        assert len(body["bars"]) >= 1
        bar_entry = next(b for b in body["bars"] if b["symbol"] == symbol)
        assert bar_entry["timeframe"] == "1h"
        assert bar_entry["row_count"] == 100

    def test_with_backtest(self, index_client):
        """Backtest section picks up manifest.json."""
        client, data_dir = index_client

        bt_dir = data_dir / "backtests" / "bt_20240101_120000_abc12345"
        bt_dir.mkdir(parents=True)
        manifest = {
            "run_id": "bt_20240101_120000_abc12345",
            "created_at": "2024-01-01T12:00:00Z",
            "symbols": ["EURUSD"],
            "bots": ["CloudTwist"],
            "timeframe": "1h",
            "sharpe": 2.5,
            "total_trades": 42,
        }
        with open(bt_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        resp = client.get("/data/artefacts/index")
        body = resp.json()
        assert len(body["backtests"]) == 1
        bt = body["backtests"][0]
        assert bt["run_id"] == "bt_20240101_120000_abc12345"
        assert bt["sharpe"] == 2.5
        assert bt["total_trades"] == 42

    def test_with_sweep(self, index_client):
        """Sweep section picks up preflight.json + top_picks.json."""
        client, data_dir = index_client

        sweep_dir = data_dir / "sweep_results" / "sweep_live_20240101_120000"
        sweep_dir.mkdir(parents=True)

        preflight = {
            "generated_at": "2024-01-01T12:00:00Z",
            "scope": "live",
            "valid_combos": 80,
        }
        with open(sweep_dir / "preflight.json", "w") as f:
            json.dump(preflight, f)

        top_picks = {
            "picks": [
                {"bot": "CloudTwist", "symbol": "EURUSD", "metrics": {"sharpe": 3.5}},
                {"bot": "KumoBreaker", "symbol": "GBPUSD", "metrics": {"sharpe": 2.1}},
            ],
        }
        with open(sweep_dir / "top_picks.json", "w") as f:
            json.dump(top_picks, f)

        resp = client.get("/data/artefacts/index")
        body = resp.json()
        assert len(body["sweeps"]) == 1
        sw = body["sweeps"][0]
        assert sw["scope"] == "live"
        assert sw["total_combos"] == 80
        assert sw["top_sharpe"] == 3.5

    def test_response_shape(self, index_client):
        """Response includes all expected top-level fields."""
        client, _ = index_client
        resp = client.get("/data/artefacts/index")
        body = resp.json()
        assert "bars" in body
        assert "backtests" in body
        assert "sweeps" in body
        assert "generated_at" in body
