"""
Desktop API contract tests for normalized engine routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from solat_engine.api import ig_terminal_routes as terminal_routes
from solat_engine.api.execution_routes import get_execution_router, get_ig_client as get_exec_ig_client
from solat_engine.api.ig_routes import get_ig_client as get_ig_api_client
from solat_engine.api.ig_terminal_routes import get_catalogue_store, get_ig_client as get_terminal_ig_client
from solat_engine.config import get_settings_dep
from solat_engine.main import app


@dataclass
class _FakeMarketDetails:
    snapshot: dict[str, object]
    scaling_factor: int | None = None


class _FakeCatalogueStore:
    def load(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                symbol="EURUSD",
                epic="CS.D.EURUSD.MINI.IP",
                display_name="EUR/USD",
                asset_class=SimpleNamespace(value="fx"),
                dealing_rules=SimpleNamespace(min_deal_size=0.1),
                pip_size=0.0001,
                is_enriched=True,
                scaling_factor=1,
            )
        ]


class _FakeExecutionRouter:
    def __init__(self) -> None:
        self.state = SimpleNamespace(
            mode=SimpleNamespace(value="DEMO"),
            demo_arm_enabled=True,
            connected=True,
        )

    async def route_intent(self, _intent):  # noqa: ANN001
        return SimpleNamespace(
            status=SimpleNamespace(value="ACKNOWLEDGED"),
            intent_id=uuid4(),
            deal_id="DIAAA111",
            rejection_reason=None,
        )


@pytest.fixture
def desktop_contract_client(tmp_path: Path) -> TestClient:
    settings = SimpleNamespace(
        data_dir=tmp_path / "data",
        has_ig_credentials=True,
        mode="DEMO",
        execution_mode="DEMO",
        ig_configured=True,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    ig_client = AsyncMock()
    ig_client.get_account_details_with_balance = AsyncMock(
        return_value={
            "account_id": "ABC123",
            "account_type": "SPREADBET",
            "balance": 10000.0,
            "profit_loss": 50.0,
            "deposit": 250.0,
            "available": 9750.0,
            "currency": "USD",
            "status": "ENABLED",
        }
    )
    ig_client.get_market_details = AsyncMock(
        return_value=_FakeMarketDetails(
            snapshot={
                "bid": 1.10001,
                "offer": 1.10011,
                "updateTime": "2026-02-15T17:00:00Z",
                "marketStatus": "TRADEABLE",
            }
        )
    )

    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_ig_api_client] = lambda: ig_client
    app.dependency_overrides[get_exec_ig_client] = lambda: ig_client
    app.dependency_overrides[get_terminal_ig_client] = lambda: ig_client
    app.dependency_overrides[get_catalogue_store] = lambda: _FakeCatalogueStore()
    app.dependency_overrides[get_execution_router] = lambda: _FakeExecutionRouter()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_openapi_contains_desktop_contract_paths(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in ["/health", "/universe", "/quotes", "/account", "/orders/market"]:
        assert path in paths


def test_health_baseline(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "version" in body
    assert "uptime_seconds" in body


def test_universe_minimum_fields(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/universe")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["instruments"], list)
    assert body["count"] >= 1
    first = body["instruments"][0]
    for key in ["symbol", "display_name", "asset_class", "epic"]:
        assert key in first
    for key in ["history_row_count", "history_score", "history_supported"]:
        assert key in first


def test_bars_contract_includes_telemetry_fields(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/bars?symbol=EURUSD&tf=15m&limit=200")
    assert response.status_code == 200
    body = response.json()
    for key in ["symbol", "tf", "bars", "count", "requested_limit", "coverage_pct", "source"]:
        assert key in body
    assert body["requested_limit"] == 200


def test_bars_403_fallback_is_bounded(monkeypatch: pytest.MonkeyPatch, desktop_contract_client: TestClient) -> None:
    calls = {"count": 0}

    class _FakeFetcher:
        def __init__(self, _client):  # noqa: ANN001
            pass

        async def fetch_by_date_range(self, **_kwargs):  # noqa: ANN003
            calls["count"] += 1
            return [], ["Historical prices failed: status 403"]

    monkeypatch.setattr(terminal_routes, "IGHistoryFetcher", _FakeFetcher)
    terminal_routes._bars_fallback_blocked_until.clear()
    terminal_routes._bars_403_cooloff_until.clear()

    response = desktop_contract_client.get("/bars?symbol=EURUSD&tf=15m&limit=800")
    assert response.status_code == 200
    assert calls["count"] <= 16  # bounded retries (adaptive shrink, no runaway loops)
    assert "EURUSD:15m" in terminal_routes._bars_403_cooloff_until


def test_quotes_symbols_mapping_fields(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/quotes?symbols=EURUSD")
    assert response.status_code == 200
    body = response.json()
    assert "quotes" in body
    assert body["count"] == 1
    quote = next(iter(body["quotes"].values()))
    for key in ["bid", "ask", "last", "time"]:
        assert key in quote


def test_account_required_fields(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.get("/account")
    assert response.status_code == 200
    body = response.json()
    for key in ["account_id", "balance", "equity", "margin", "available", "currency"]:
        assert key in body


def test_market_order_demo_payload_and_response(desktop_contract_client: TestClient) -> None:
    response = desktop_contract_client.post(
        "/orders/market",
        json={
            "symbol": "EURUSD",
            "direction": "BUY",
            "size": 0.1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "ok" in body
    assert "status" in body


# =============================================================================
# Spread-bet quote normalization tests
# =============================================================================


class _FakeMarketDetailsSpreadbet:
    """Market details returning raw spread-bet prices (×10000)."""

    def __init__(self) -> None:
        self.snapshot = {
            "bid": 11854.3,
            "offer": 11856.1,
            "updateTime": "2026-02-16T10:00:00Z",
            "marketStatus": "TRADEABLE",
        }
        self.scaling_factor = 10000


class _FakeSpreadbetCatalogueStore:
    def load(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                symbol="EURUSD",
                epic="CS.D.EURUSD.TODAY.IP",
                display_name="EUR/USD",
                asset_class=SimpleNamespace(value="fx"),
                dealing_rules=SimpleNamespace(min_deal_size=0.5),
                pip_size=0.0001,
                is_enriched=True,
                scaling_factor=10000,
            )
        ]


@pytest.fixture
def spreadbet_contract_client(tmp_path: Path) -> TestClient:
    """Client with spread-bet scaling_factor=10000 on EURUSD."""
    settings = SimpleNamespace(
        data_dir=tmp_path / "data",
        has_ig_credentials=True,
        mode="DEMO",
        execution_mode="DEMO",
        ig_configured=True,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    ig_client = AsyncMock()
    ig_client.get_market_details = AsyncMock(
        return_value=_FakeMarketDetailsSpreadbet()
    )

    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_ig_api_client] = lambda: ig_client
    app.dependency_overrides[get_exec_ig_client] = lambda: ig_client
    app.dependency_overrides[get_terminal_ig_client] = lambda: ig_client
    app.dependency_overrides[get_catalogue_store] = lambda: _FakeSpreadbetCatalogueStore()
    app.dependency_overrides[get_execution_router] = lambda: _FakeExecutionRouter()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_quotes_spreadbet_normalization(spreadbet_contract_client: TestClient) -> None:
    """Verify spread-bet prices are divided by scaling_factor (10000)."""
    response = spreadbet_contract_client.get("/quotes?symbols=EURUSD")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    quote = next(iter(body["quotes"].values()))

    # Raw from IG: bid=11854.3, offer=11856.1
    # After ÷10000: bid≈1.18543, ask≈1.18561
    assert 1.0 < quote["bid"] < 2.0, f"bid should be normalized: got {quote['bid']}"
    assert 1.0 < quote["ask"] < 2.0, f"ask should be normalized: got {quote['ask']}"
    assert abs(quote["bid"] - 1.18543) < 0.001
    assert abs(quote["ask"] - 1.18561) < 0.001
    assert quote["scaling_factor"] == 10000


def test_quotes_no_scaling_when_factor_is_1(desktop_contract_client: TestClient) -> None:
    """Verify prices pass through unchanged when scaling_factor=1."""
    response = desktop_contract_client.get("/quotes?symbols=EURUSD")
    assert response.status_code == 200
    body = response.json()
    quote = next(iter(body["quotes"].values()))

    # Original mock returns bid=1.10001, offer=1.10011 with scaling_factor=1
    assert abs(quote["bid"] - 1.10001) < 0.0001
    assert abs(quote["ask"] - 1.10011) < 0.0001
    assert quote["scaling_factor"] == 1
