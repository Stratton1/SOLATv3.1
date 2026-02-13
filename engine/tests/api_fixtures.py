"""
Shared API fixtures and dependency override helpers for testing.
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import get_ig_client as get_ig_client_exec
from solat_engine.api.ig_routes import get_ig_client as get_ig_client_api
from solat_engine.config import AppEnvironment, TradingMode, get_settings_dep
from solat_engine.main import app


@dataclass
class TestSettings:
    """Lightweight settings object for tests."""

    data_dir: Path
    mode: TradingMode = TradingMode.DEMO
    env: AppEnvironment = AppEnvironment.DEVELOPMENT

    # Execution settings
    execution_mode: str = "DEMO"
    live_trading_enabled: bool = False
    live_enable_token: str | None = None
    live_account_id: str | None = None
    live_max_order_size: float | None = None
    live_confirmation_ttl_s: int = 600
    live_prelive_max_age_s: int = 300
    execution_reconcile_interval_s: int = 5
    max_position_size: float = 1.0
    max_concurrent_positions: int = 5
    max_daily_loss_pct: float = 5.0
    max_trades_per_hour: int = 20
    per_symbol_exposure_cap: float = 10000.0
    require_sl: bool = False
    close_on_kill_switch: bool = False
    require_arm_confirmation: bool = True

    # IG settings
    ig_api_key: str | None = "test-api-key"
    ig_username: str | None = "test-user"
    ig_password: str | None = "test-password"
    ig_account_id: str | None = None
    ig_acc_type: TradingMode = TradingMode.DEMO
    ig_base_url_demo: str = "https://demo-api.ig.com/gateway/deal"
    ig_base_url_live: str = "https://api.ig.com/gateway/deal"
    ig_request_timeout: float = 10.0
    ig_max_retries: int = 3
    ig_rate_limit_rps: float = 2.0
    ig_rate_limit_burst: int = 10
    history_max_rows_per_call: int = 50000
    _has_ig_credentials_override: bool | None = field(default=None, repr=False)

    @property
    def has_ig_credentials(self) -> bool:
        if self._has_ig_credentials_override is not None:
            return self._has_ig_credentials_override
        return all([self.ig_api_key, self.ig_username, self.ig_password])

    @has_ig_credentials.setter
    def has_ig_credentials(self, value: bool) -> None:
        self._has_ig_credentials_override = bool(value)

    @property
    def has_live_token(self) -> bool:
        return self.live_enable_token is not None

    @property
    def has_live_account_lock(self) -> bool:
        return self.live_account_id is not None

    @property
    def has_live_risk_config(self) -> bool:
        return all([
            self.live_max_order_size is not None,
            self.max_daily_loss_pct > 0,
            self.max_concurrent_positions > 0,
            self.per_symbol_exposure_cap > 0,
            self.max_trades_per_hour > 0,
        ])

    def get_live_risk_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.live_max_order_size is None:
            blockers.append("LIVE_MAX_ORDER_SIZE not set")
        if self.max_daily_loss_pct <= 0:
            blockers.append("MAX_DAILY_LOSS_PCT must be positive")
        if self.max_concurrent_positions <= 0:
            blockers.append("MAX_CONCURRENT_POSITIONS must be positive")
        if self.per_symbol_exposure_cap <= 0:
            blockers.append("PER_SYMBOL_EXPOSURE_CAP must be positive")
        if self.max_trades_per_hour <= 0:
            blockers.append("MAX_TRADES_PER_HOUR must be positive")
        return blockers

    @property
    def ig_base_url(self) -> str:
        if self.ig_acc_type == TradingMode.DEMO:
            return self.ig_base_url_demo
        return self.ig_base_url_live

    @property
    def is_demo(self) -> bool:
        return self.mode == TradingMode.DEMO

    @property
    def is_live(self) -> bool:
        return self.mode == TradingMode.LIVE


class DependencyOverrider:
    """Helper to manage FastAPI dependency overrides in tests."""

    def __init__(self, app):
        self.app = app
        self.overrides = {}

    def override(self, dependency, value):
        """Register an override."""
        self.app.dependency_overrides[dependency] = value
        self.overrides[dependency] = value

    def clear(self):
        """Clear all overrides."""
        self.app.dependency_overrides.clear()
        self.overrides.clear()


@pytest.fixture
def overrider():
    """Fixture that provides a DependencyOverrider and clears it after the test."""
    overrider = DependencyOverrider(app)
    yield overrider
    overrider.clear()


@pytest.fixture
def settings_demo(tmp_path: Path) -> TestSettings:
    """Default DEMO settings with a real filesystem path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return TestSettings(data_dir=data_dir)


@pytest.fixture
def settings_live_disabled(settings_demo: TestSettings) -> TestSettings:
    """Explicitly keep LIVE trading disabled for tests."""
    settings_demo.live_trading_enabled = False
    settings_demo.live_enable_token = None
    settings_demo.live_account_id = None
    settings_demo.live_max_order_size = None
    return settings_demo


@pytest.fixture
def mock_settings(settings_demo: TestSettings) -> TestSettings:
    """Backward-compatible alias used by existing tests."""
    return settings_demo


@pytest.fixture
def mock_ig_client():
    """Default mock IG client for tests."""
    client = AsyncMock()
    # Mock common methods to return plain values instead of AsyncMocks to avoid warnings
    client.login = AsyncMock(return_value={})
    client.list_accounts = AsyncMock(return_value=[
        {"accountId": "ABC123", "balance": {"balance": 10000.0}},
    ])
    client.list_positions = AsyncMock(return_value=[])
    client.get_accounts = AsyncMock(return_value=[])
    client.search_markets = AsyncMock(return_value=[])
    client.get_market_details = AsyncMock(return_value={})

    # Live verification mock
    client.verify_account_for_live = AsyncMock(return_value={
        "verified": False,
        "is_live": False
    })

    # Status properties used by /ig/status
    client.is_authenticated = False
    client.session_age_seconds = 0
    client.rate_limiter_stats = {}

    return client


def create_test_client(
    overrider: DependencyOverrider,
    settings: TestSettings,
    ig_client: AsyncMock,
) -> TestClient:
    """Create a TestClient with common overrides applied."""
    overrider.override(get_settings_dep, lambda: settings)
    overrider.override(get_ig_client_api, lambda: ig_client)
    overrider.override(get_ig_client_exec, lambda: ig_client)
    return TestClient(app)


@pytest.fixture
def api_client(overrider, mock_settings, mock_ig_client):
    """TestClient with common overrides."""
    from solat_engine.api.execution_routes import reset_execution_state

    reset_execution_state()
    with create_test_client(overrider, mock_settings, mock_ig_client) as client:
        yield client
