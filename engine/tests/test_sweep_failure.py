"""
Tests for sweep failure handling with structured errors.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_sweep_validates_bots():
    """Sweep endpoint should reject invalid bot names with 400."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_data_dir = Path(tmpdir)

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

            from solat_engine.api import backtest_routes, data_routes

            data_routes._parquet_store = None
            backtest_routes._parquet_store = None
            backtest_routes._sweep_jobs.clear()
            backtest_routes._sweep_results.clear()

            from solat_engine.main import app

            with TestClient(app) as client:
                # Try to start sweep with invalid bot
                resp = client.post(
                    "/backtest/sweep",
                    json={
                        "bots": ["InvalidBotName"],
                        "symbols": ["EURUSD"],
                        "timeframes": ["1h"],
                        "start": "2024-01-15T10:00:00Z",
                        "end": "2024-01-15T13:00:00Z",
                    },
                )

                # Should fail validation at endpoint level
                assert resp.status_code == 400
                assert "Invalid bots" in resp.json()["detail"]
