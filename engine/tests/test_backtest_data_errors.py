"""
Tests for backtest validation and error handling edge cases.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_backtest_rejects_invalid_bot_names():
    """Backtest should reject invalid bot names with 400 error."""
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
            backtest_routes._active_jobs.clear()
            backtest_routes._job_results.clear()

            from solat_engine.main import app

            with TestClient(app) as client:
                # Try to start backtest with invalid bot name
                resp = client.post(
                    "/backtest/run",
                    json={
                        "bots": ["InvalidBotThatDoesNotExist"],
                        "symbols": ["EURUSD"],
                        "timeframe": "1h",
                        "start": "2024-01-01T00:00:00Z",
                        "end": "2024-01-31T23:59:59Z",
                        "initial_balance": 10000.0,
                    },
                )

                # Should fail validation at endpoint level
                assert resp.status_code == 400
                assert "Invalid bots" in resp.json()["detail"]
