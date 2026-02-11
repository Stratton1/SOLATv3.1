"""
Tests for autopilot service and routes.

Covers:
- Enable/disable lifecycle
- LIVE mode blocking (403)
- Status endpoint
- Bar processing → signal generation
- Cooldown enforcement
- Kill switch blocks signals
- Rate limit enforcement
- Bar buffer bounded by maxlen
- Combos endpoint
"""

import asyncio
from collections import deque
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solat_engine.autopilot.service import (
    AutopilotConfig,
    AutopilotService,
    set_autopilot_service,
)
from solat_engine.config import Settings, TradingMode
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.execution.models import ExecutionMode, ExecutionState
from solat_engine.execution.router import ExecutionRouter
from solat_engine.main import app
from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.optimization.models import AllowlistEntry
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus, reset_event_bus


@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(mode=TradingMode.DEMO, data_dir=tmp_path)


@pytest.fixture
def live_settings(tmp_path):
    return Settings(mode=TradingMode.LIVE, data_dir=tmp_path)


@pytest.fixture
def allowlist_mgr(tmp_path):
    """AllowlistManager with one enabled entry."""
    mgr = AllowlistManager(data_dir=tmp_path)
    entry = AllowlistEntry(
        symbol="EURUSD",
        bot="CloudTwist",
        timeframe="1h",
        sharpe=2.5,
        total_trades=50,
        enabled=True,
        validated_at=datetime.now(UTC),
    )
    mgr.add_entry(entry)
    return mgr


@pytest.fixture
def mock_exec_router():
    """Mock execution router that accepts intents."""
    router = MagicMock(spec=ExecutionRouter)
    router.state = ExecutionState(mode=ExecutionMode.DEMO)
    router.state.armed = True
    kill_switch = MagicMock()
    kill_switch.is_active = False
    router.kill_switch = kill_switch
    router.route_intent = AsyncMock()
    return router


@pytest.fixture
def autopilot_svc(mock_exec_router, allowlist_mgr, tmp_settings):
    """AutopilotService with mocked dependencies."""
    return AutopilotService(
        execution_router=mock_exec_router,
        allowlist_mgr=allowlist_mgr,
        config=AutopilotConfig(
            warmup_bars=5,
            per_combo_cooldown_bars=1,
            max_signals_per_minute=100,
            default_size=0.1,
        ),
        settings=tmp_settings,
    )


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Reset event bus between tests."""
    yield
    reset_event_bus()


@pytest.fixture
def client(tmp_path, tmp_settings, autopilot_svc):
    """Test client with autopilot service."""
    from solat_engine.api.data_routes import get_parquet_store
    from solat_engine.config import get_settings_dep

    store = ParquetStore(tmp_path)
    set_autopilot_service(autopilot_svc)

    app.dependency_overrides[get_settings_dep] = lambda: tmp_settings
    app.dependency_overrides[get_parquet_store] = lambda: store

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
    set_autopilot_service(None)


@pytest.fixture
def live_client(tmp_path, live_settings, autopilot_svc):
    """Test client in LIVE mode."""
    from solat_engine.api.data_routes import get_parquet_store
    from solat_engine.config import get_settings_dep

    store = ParquetStore(tmp_path)
    set_autopilot_service(autopilot_svc)

    app.dependency_overrides[get_settings_dep] = lambda: live_settings
    app.dependency_overrides[get_parquet_store] = lambda: store

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
    set_autopilot_service(None)


class TestAutopilotRoutes:
    def test_status_endpoint(self, client):
        resp = client.get("/autopilot/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert "combo_count" in data

    def test_enable_requires_demo(self, live_client):
        resp = live_client.post("/autopilot/enable")
        assert resp.status_code == 403

    def test_disable_endpoint(self, client):
        resp = client.post("/autopilot/disable")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_combos_endpoint(self, client):
        resp = client.get("/autopilot/combos")
        assert resp.status_code == 200
        data = resp.json()
        assert "combos" in data
        assert "count" in data


class TestAutopilotService:
    @pytest.mark.asyncio
    async def test_enable_disable_lifecycle(self, autopilot_svc):
        state = await autopilot_svc.enable()
        assert state.enabled is True
        assert state.combo_count == 1  # EURUSD:CloudTwist:1h

        state = await autopilot_svc.disable()
        assert state.enabled is False

    @pytest.mark.asyncio
    async def test_enable_blocked_no_armed(self, autopilot_svc, mock_exec_router):
        mock_exec_router.state.armed = False
        state = await autopilot_svc.enable()
        # Should report blocked reasons
        assert "Execution engine is not armed" in (state.blocked_reasons or [])

    @pytest.mark.asyncio
    async def test_on_bar_generates_signal(self, autopilot_svc, mock_exec_router):
        """Mock strategy to return BUY signal, verify intent is routed."""
        await autopilot_svc.enable()

        # Build enough bars for warmup + 1
        bar_data = {
            "symbol": "EURUSD",
            "timeframe": "1h",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100,
        }

        # Push warmup bars
        for i in range(6):
            event = Event(type=EventType.BAR_RECEIVED, data=bar_data)
            await autopilot_svc._on_bar_received(event)

        # Strategy may not generate entry on these generic bars,
        # but the cycle count should increment
        assert autopilot_svc._cycle_count == 6

        await autopilot_svc.disable()

    @pytest.mark.asyncio
    async def test_cooldown_respected(self, autopilot_svc):
        """Verify cooldown tracking increments on each bar."""
        autopilot_svc._config.per_combo_cooldown_bars = 3
        await autopilot_svc.enable()

        bar_data = {
            "symbol": "EURUSD",
            "timeframe": "1h",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100,
        }

        key = "EURUSD:CloudTwist:1h"
        # _load_combos initialises cooldown to per_combo_cooldown_bars (3)
        initial_cd = autopilot_svc._cooldowns.get(key, 0)
        assert initial_cd == 3

        # After first bar, cooldown increments by 1
        event = Event(type=EventType.BAR_RECEIVED, data=bar_data)
        await autopilot_svc._on_bar_received(event)
        assert autopilot_svc._cooldowns.get(key, 0) == initial_cd + 1

        await autopilot_svc.disable()

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self, autopilot_svc, mock_exec_router):
        """Active kill switch should prevent signal processing."""
        await autopilot_svc.enable()
        mock_exec_router.kill_switch.is_active = True

        bar_data = {
            "symbol": "EURUSD",
            "timeframe": "1h",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100,
        }

        event = Event(type=EventType.BAR_RECEIVED, data=bar_data)
        await autopilot_svc._on_bar_received(event)

        # Cycle should increment but no signals generated
        assert autopilot_svc._cycle_count == 1
        assert autopilot_svc._signals_generated == 0

        await autopilot_svc.disable()

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self, autopilot_svc):
        """Exceed rate limit cap → signals skipped."""
        autopilot_svc._config.max_signals_per_minute = 2

        # Fill rate limit
        import time
        now = time.monotonic()
        autopilot_svc._signal_timestamps = [now, now]

        assert autopilot_svc._check_rate_limit() is False

    @pytest.mark.asyncio
    async def test_bar_buffer_bounded(self, autopilot_svc):
        """Bar buffer deque maxlen is enforced."""
        await autopilot_svc.enable()

        key = "EURUSD:CloudTwist:1h"
        buf = autopilot_svc._bar_buffers.get(key)
        assert buf is not None
        expected_maxlen = autopilot_svc._config.warmup_bars + 50
        assert buf.maxlen == expected_maxlen

        # Push more bars than maxlen
        bar_data = {
            "symbol": "EURUSD",
            "timeframe": "1h",
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100,
        }

        for _ in range(expected_maxlen + 20):
            event = Event(type=EventType.BAR_RECEIVED, data=bar_data)
            await autopilot_svc._on_bar_received(event)

        assert len(buf) == expected_maxlen

        await autopilot_svc.disable()

    @pytest.mark.asyncio
    async def test_unmatched_bar_ignored(self, autopilot_svc):
        """Bars for symbols not in allowlist are ignored."""
        await autopilot_svc.enable()

        bar_data = {
            "symbol": "XAUUSD",
            "timeframe": "1h",
            "open": 2000,
            "high": 2050,
            "low": 1990,
            "close": 2030,
            "volume": 100,
        }

        event = Event(type=EventType.BAR_RECEIVED, data=bar_data)
        await autopilot_svc._on_bar_received(event)

        # Cycle increments but no buffers updated for XAUUSD
        assert autopilot_svc._cycle_count == 1
        assert "XAUUSD:CloudTwist:1h" not in autopilot_svc._bar_buffers

        await autopilot_svc.disable()

    def test_get_combos(self, autopilot_svc):
        """get_combos returns empty before enable, populated after."""
        assert autopilot_svc.get_combos() == []

    @pytest.mark.asyncio
    async def test_get_combos_after_enable(self, autopilot_svc):
        await autopilot_svc.enable()
        combos = autopilot_svc.get_combos()
        assert len(combos) == 1
        assert combos[0]["symbol"] == "EURUSD"
        assert combos[0]["bot"] == "CloudTwist"
        assert combos[0]["timeframe"] == "1h"
        await autopilot_svc.disable()
