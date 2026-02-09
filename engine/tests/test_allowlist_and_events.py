"""
Tests for execution events, fills, orders, and allowlist endpoints.

Tests the following new endpoints:
- GET /execution/events
- GET /execution/fills
- GET /execution/orders
- POST /execution/allowlist
- GET /execution/allowlist
- Allowlist enforcement in ExecutionRouter.route_intent()
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.execution_routes import (
    get_execution_router,
    get_ig_client,
    reset_execution_state,
)
from solat_engine.config import get_settings_dep
from solat_engine.execution.models import (
    ExecutionConfig,
    ExecutionMode,
    LedgerEntry,
    OrderAck,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from solat_engine.execution.router import ExecutionRouter
from solat_engine.main import app
from tests.api_fixtures import DependencyOverrider, TestSettings


@pytest.fixture
def overrider():
    """Provide a DependencyOverrider and clean up after test."""
    ov = DependencyOverrider(app)
    yield ov
    ov.clear()


@pytest.fixture
def test_settings(tmp_path: Path) -> TestSettings:
    """Create test settings with temp data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return TestSettings(data_dir=data_dir)


@pytest.fixture
def exec_router(test_settings: TestSettings) -> ExecutionRouter:
    """Create a fresh ExecutionRouter for tests."""
    config = ExecutionConfig(mode=ExecutionMode.DEMO)
    return ExecutionRouter(config, test_settings.data_dir)


@pytest.fixture
def api_client(overrider, test_settings, exec_router):
    """TestClient with execution router override."""
    reset_execution_state()
    overrider.override(get_settings_dep, lambda: test_settings)
    overrider.override(get_execution_router, lambda: exec_router)
    overrider.override(get_ig_client, lambda: AsyncMock())
    with TestClient(app) as client:
        yield client


def _write_ledger_entry(router: ExecutionRouter, entry: LedgerEntry) -> None:
    """Write a ledger entry directly to the router's ledger file."""
    with open(router.ledger._ledger_path, "a") as f:
        f.write(entry.model_dump_json() + "\n")


# =============================================================================
# GET /execution/events
# =============================================================================


class TestEventsEndpoint:
    """Tests for GET /execution/events."""

    def test_events_empty_ledger(self, api_client: TestClient) -> None:
        """Should return empty list when ledger has no entries."""
        response = api_client.get("/execution/events")
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_events_returns_intent_entries(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should return intent entries as INTENT type."""
        intent_id = uuid4()
        entry = LedgerEntry(
            entry_type="intent",
            intent_id=intent_id,
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
            metadata={"bot": "CloudTwist", "order_type": "MARKET"},
        )
        _write_ledger_entry(exec_router, entry)

        response = api_client.get("/execution/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        event = data["events"][0]
        assert event["type"] == "INTENT"
        assert event["side"] == "BUY"
        assert event["bot"] == "CloudTwist"
        assert event["order_id"] == str(intent_id)

    def test_events_returns_rejection_entries(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should return rejection entries as REJECT type."""
        entry = LedgerEntry(
            entry_type="rejection",
            intent_id=uuid4(),
            symbol="GBPUSD",
            side=OrderSide.SELL,
            size=0.5,
            status=OrderStatus.REJECTED,
            reason_codes=["kill_switch_active"],
            error="Kill switch active",
        )
        _write_ledger_entry(exec_router, entry)

        response = api_client.get("/execution/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        event = data["events"][0]
        assert event["type"] == "REJECT"
        assert event["reason"] == "Kill switch active"

    def test_events_filter_by_symbol(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter events by symbol."""
        for symbol in ["EURUSD", "GBPUSD", "EURUSD"]:
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="intent",
                    intent_id=uuid4(),
                    symbol=symbol,
                    side=OrderSide.BUY,
                    size=0.1,
                    metadata={"bot": "Test"},
                ),
            )

        response = api_client.get("/execution/events?symbol=EURUSD")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_events_limit(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should respect limit parameter."""
        for i in range(5):
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="intent",
                    intent_id=uuid4(),
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    metadata={"bot": "Test"},
                ),
            )

        response = api_client.get("/execution/events?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 2
        assert data["total"] == 5

    def test_events_since_filter(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter events by since timestamp."""
        old_ts = datetime(2024, 1, 1, tzinfo=UTC)
        new_ts = datetime(2025, 6, 1, tzinfo=UTC)

        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                timestamp=old_ts,
                entry_type="intent",
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                metadata={"bot": "Test"},
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                timestamp=new_ts,
                entry_type="intent",
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                metadata={"bot": "Test"},
            ),
        )

        response = api_client.get("/execution/events?since=2025-01-01T00:00:00%2B00:00")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_events_skips_non_order_entries(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should skip reconciliation and kill_switch entries."""
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="reconciliation",
                metadata={"broker_count": 0, "local_count": 0, "drift_detected": False},
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="kill_switch",
                metadata={"activated": True, "reason": "test"},
            ),
        )

        response = api_client.get("/execution/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


# =============================================================================
# GET /execution/fills
# =============================================================================


class TestFillsEndpoint:
    """Tests for GET /execution/fills."""

    def test_fills_empty(self, api_client: TestClient) -> None:
        """Should return empty list when no fills."""
        response = api_client.get("/execution/fills")
        assert response.status_code == 200
        data = response.json()
        assert data["fills"] == []
        assert data["total"] == 0

    def test_fills_returns_ack_filled_entries(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should return only ack entries with FILLED status."""
        # Write an ack with FILLED status
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=uuid4(),
                deal_id="DEAL_123",
                deal_reference="REF_123",
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                status=OrderStatus.FILLED,
                metadata={"filled_size": 0.1, "filled_price": 1.0850},
            ),
        )
        # Write an ack with REJECTED status (should not appear)
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                status=OrderStatus.REJECTED,
            ),
        )
        # Write an intent (should not appear)
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="intent",
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                metadata={"bot": "Test"},
            ),
        )

        response = api_client.get("/execution/fills")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        fill = data["fills"][0]
        assert fill["deal_id"] == "DEAL_123"
        assert fill["price"] == 1.0850
        assert fill["size"] == 0.1

    def test_fills_filter_by_symbol(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter fills by symbol."""
        for sym in ["EURUSD", "GBPUSD"]:
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="ack",
                    intent_id=uuid4(),
                    deal_id=f"DEAL_{sym}",
                    symbol=sym,
                    side=OrderSide.BUY,
                    size=0.1,
                    status=OrderStatus.FILLED,
                    metadata={"filled_size": 0.1, "filled_price": 1.0},
                ),
            )

        response = api_client.get("/execution/fills?symbol=GBPUSD")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["fills"][0]["symbol"] == "GBPUSD"

    def test_fills_pagination(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should support pagination with limit and offset."""
        for i in range(5):
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="ack",
                    intent_id=uuid4(),
                    deal_id=f"DEAL_{i}",
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    status=OrderStatus.FILLED,
                    metadata={"filled_size": 0.1, "filled_price": 1.0 + i * 0.001},
                ),
            )

        response = api_client.get("/execution/fills?limit=2&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["fills"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 1

    def test_fills_filter_by_side(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter fills by side."""
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=uuid4(),
                deal_id="DEAL_BUY",
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                status=OrderStatus.FILLED,
                metadata={"filled_size": 0.1, "filled_price": 1.0},
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=uuid4(),
                deal_id="DEAL_SELL",
                symbol="EURUSD",
                side=OrderSide.SELL,
                size=0.2,
                status=OrderStatus.FILLED,
                metadata={"filled_size": 0.2, "filled_price": 1.1},
            ),
        )

        response = api_client.get("/execution/fills?side=SELL")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["fills"][0]["side"] == "SELL"


# =============================================================================
# GET /execution/orders
# =============================================================================


class TestOrdersEndpoint:
    """Tests for GET /execution/orders."""

    def test_orders_empty(self, api_client: TestClient) -> None:
        """Should return empty list when no orders."""
        response = api_client.get("/execution/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    def test_orders_returns_intent_submission_ack(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should return intent, submission, and ack entries."""
        intent_id = uuid4()
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="intent",
                intent_id=intent_id,
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                metadata={"bot": "CloudTwist", "order_type": "MARKET"},
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="submission",
                intent_id=intent_id,
                deal_reference="REF_ABC",
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                status=OrderStatus.SUBMITTED,
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=intent_id,
                deal_id="DEAL_ABC",
                deal_reference="REF_ABC",
                status=OrderStatus.FILLED,
                metadata={"filled_size": 0.1, "filled_price": 1.085},
            ),
        )
        # reconciliation entry should not appear
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="reconciliation",
                metadata={"broker_count": 0, "local_count": 0, "drift_detected": False},
            ),
        )

        response = api_client.get("/execution/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3  # intent + submission + ack

    def test_orders_filter_by_symbol(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter orders by symbol."""
        for sym in ["EURUSD", "GBPUSD"]:
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="intent",
                    intent_id=uuid4(),
                    symbol=sym,
                    side=OrderSide.BUY,
                    size=0.1,
                    metadata={"bot": "Test", "order_type": "MARKET"},
                ),
            )

        response = api_client.get("/execution/orders?symbol=EURUSD")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_orders_filter_by_status(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should filter orders by status."""
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="submission",
                intent_id=uuid4(),
                symbol="EURUSD",
                side=OrderSide.BUY,
                size=0.1,
                status=OrderStatus.SUBMITTED,
            ),
        )
        _write_ledger_entry(
            exec_router,
            LedgerEntry(
                entry_type="ack",
                intent_id=uuid4(),
                deal_id="D1",
                status=OrderStatus.FILLED,
                metadata={"filled_size": 0.1, "filled_price": 1.0},
            ),
        )

        response = api_client.get("/execution/orders?status=FILLED")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["orders"][0]["status"] == "FILLED"

    def test_orders_pagination(
        self, api_client: TestClient, exec_router: ExecutionRouter
    ) -> None:
        """Should support pagination."""
        for i in range(4):
            _write_ledger_entry(
                exec_router,
                LedgerEntry(
                    entry_type="submission",
                    intent_id=uuid4(),
                    symbol="EURUSD",
                    side=OrderSide.BUY,
                    size=0.1,
                    status=OrderStatus.SUBMITTED,
                    deal_reference=f"REF_{i}",
                ),
            )

        response = api_client.get("/execution/orders?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert len(data["orders"]) == 2
        assert data["offset"] == 2


# =============================================================================
# POST/GET /execution/allowlist
# =============================================================================


class TestAllowlistEndpoints:
    """Tests for allowlist endpoints."""

    def test_get_allowlist_empty_by_default(self, api_client: TestClient) -> None:
        """Should return empty allowlist when not set."""
        response = api_client.get("/execution/allowlist")
        assert response.status_code == 200
        data = response.json()
        assert data["symbols"] == []
        assert data["active"] is False

    def test_set_allowlist(self, api_client: TestClient) -> None:
        """Should set allowlist and return count."""
        response = api_client.post(
            "/execution/allowlist",
            json={"symbols": ["EURUSD", "GBPUSD"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["count"] == 2

    def test_get_allowlist_after_set(self, api_client: TestClient) -> None:
        """Should return set allowlist."""
        api_client.post(
            "/execution/allowlist",
            json={"symbols": ["EURUSD", "GBPUSD"]},
        )

        response = api_client.get("/execution/allowlist")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert set(data["symbols"]) == {"EURUSD", "GBPUSD"}

    def test_clear_allowlist_with_empty_list(self, api_client: TestClient) -> None:
        """Should clear allowlist when empty list is provided."""
        # Set allowlist first
        api_client.post(
            "/execution/allowlist",
            json={"symbols": ["EURUSD"]},
        )

        # Clear it
        response = api_client.post(
            "/execution/allowlist",
            json={"symbols": []},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["count"] == 0

        # Verify cleared
        get_response = api_client.get("/execution/allowlist")
        assert get_response.json()["active"] is False

    def test_allowlist_normalizes_to_uppercase(self, api_client: TestClient) -> None:
        """Should normalize symbols to uppercase."""
        api_client.post(
            "/execution/allowlist",
            json={"symbols": ["eurusd", "GbpUsd"]},
        )

        response = api_client.get("/execution/allowlist")
        data = response.json()
        assert set(data["symbols"]) == {"EURUSD", "GBPUSD"}


# =============================================================================
# Allowlist enforcement in route_intent
# =============================================================================


class TestAllowlistEnforcement:
    """Tests for allowlist enforcement in ExecutionRouter.route_intent()."""

    @pytest.mark.asyncio
    async def test_route_intent_rejected_when_not_allowlisted(
        self, exec_router: ExecutionRouter
    ) -> None:
        """Should reject intents for symbols not on the allowlist."""
        exec_router._symbol_allowlist = {"GBPUSD", "USDJPY"}

        intent = OrderIntent(
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
            bot="TestBot",
        )

        ack = await exec_router.route_intent(intent)
        assert ack.status == OrderStatus.REJECTED
        assert ack.rejection_reason == "SYMBOL_NOT_ALLOWLISTED"

    @pytest.mark.asyncio
    async def test_route_intent_allowed_when_on_allowlist(
        self, exec_router: ExecutionRouter
    ) -> None:
        """Should allow intents for symbols on the allowlist (not armed, so PENDING)."""
        exec_router._symbol_allowlist = {"EURUSD", "GBPUSD"}

        intent = OrderIntent(
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
            bot="TestBot",
        )

        ack = await exec_router.route_intent(intent)
        # Not armed, so should be PENDING (not REJECTED)
        assert ack.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_route_intent_allowed_when_no_allowlist(
        self, exec_router: ExecutionRouter
    ) -> None:
        """Should allow all symbols when allowlist is None."""
        assert exec_router._symbol_allowlist is None

        intent = OrderIntent(
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
            bot="TestBot",
        )

        ack = await exec_router.route_intent(intent)
        assert ack.status == OrderStatus.PENDING  # Not armed

    @pytest.mark.asyncio
    async def test_rejected_intent_recorded_in_ledger(
        self, exec_router: ExecutionRouter
    ) -> None:
        """Should record the rejection in the ledger."""
        exec_router._symbol_allowlist = {"GBPUSD"}

        intent = OrderIntent(
            symbol="EURUSD",
            side=OrderSide.BUY,
            size=0.1,
            bot="TestBot",
        )

        await exec_router.route_intent(intent)

        entries = exec_router.ledger.get_entries(entry_type="rejection")
        assert len(entries) == 1
        assert entries[0].error == "SYMBOL_NOT_ALLOWLISTED"
        assert "symbol_not_allowlisted" in entries[0].reason_codes
