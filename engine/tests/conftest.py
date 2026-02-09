"""
Pytest configuration and shared fixtures.
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

# Import shared fixtures from api_fixtures
from tests.api_fixtures import *  # noqa: F403

# Set test environment variables before importing app modules
os.environ.setdefault("SOLAT_MODE", "DEMO")
os.environ.setdefault("SOLAT_ENV", "development")


@pytest.fixture(scope="session")
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no real credentials leak into tests from local .env."""
    # List of sensitive env vars to clear
    ig_vars = [
        "IG_USERNAME",
        "IG_PASSWORD",
        "IG_API_KEY",
        "IG_ACC_TYPE",
        "LIVE_ENABLE_TOKEN",
        "LIVE_ACCOUNT_ID",
    ]
    for var in ig_vars:
        monkeypatch.delenv(var, raising=False)

    # Force test environment
    monkeypatch.setenv("ENV", "test")


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    """Reset module-level singletons between tests."""
    # Run the test
    yield

    # Reset singletons after each test
    from solat_engine.api import (
        backtest_routes,
        catalog_routes,
        data_routes,
        ig_routes,
        market_data_routes,
    )
    from solat_engine.market_data import publisher

    catalog_routes._catalogue_store = None
    ig_routes._ig_client = None
    data_routes._parquet_store = None
    data_routes._catalogue_store = None
    backtest_routes._parquet_store = None
    backtest_routes._job_results.clear()
    backtest_routes._active_jobs.clear()
    backtest_routes._sweep_results.clear()
    backtest_routes._sweep_jobs.clear()
    market_data_routes._market_service = None
    market_data_routes._catalogue_store = None
    publisher.reset_publisher()
