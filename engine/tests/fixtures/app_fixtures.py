"""
App-level fixtures and dependency injection overrides.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client as get_ig_client_exec
from solat_engine.api.ig_routes import get_ig_client as get_ig_client_api
from solat_engine.config import AppEnvironment, TradingMode, get_settings_dep
from solat_engine.main import app


@pytest.fixture(autouse=True)
def mock_psutil():
    """Mock psutil to avoid OS calls during tests."""
    with MagicMock() as mock:
        import psutil
        
        # Mock Process
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 5.0
        mock_process.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
        
        # Mock psutil functions
        psutil.Process = MagicMock(return_value=mock_process)
        psutil.disk_usage = MagicMock()
        psutil.disk_usage.return_value.free = 500 * 1024 * 1024 * 1024  # 500GB
        
        yield psutil


@pytest.fixture
def app_client(overrider, mock_settings, mock_ig_client):
    """Clean TestClient with standard overrides."""
    from solat_engine.api.execution_routes import reset_execution_state
    reset_execution_state()
    
    # Apply standard overrides
    app.dependency_overrides[get_settings_dep] = lambda: mock_settings
    app.dependency_overrides[get_ig_client_api] = lambda: mock_ig_client
    app.dependency_overrides[get_ig_client_exec] = lambda: mock_ig_client
    
    with TestClient(app) as client:
        yield client
    
    # Clear overrides after test
    app.dependency_overrides.clear()
