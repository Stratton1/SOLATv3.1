"""
Tests for position reconciliation service.

Tests position drift detection with stubbed IG client.
"""

from unittest.mock import AsyncMock

import pytest

from solat_engine.execution.models import (
    ExecutionConfig,
    OrderSide,
    PositionView,
)
from solat_engine.execution.reconciliation import (
    PositionStore,
    ReconciliationService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_ig_client() -> AsyncMock:
    """Create mock IG client."""
    client = AsyncMock()
    client.list_positions = AsyncMock(return_value=[])
    return client


@pytest.fixture
def default_config() -> ExecutionConfig:
    """Create default execution config."""
    return ExecutionConfig(
        max_position_size=1.0,
        max_concurrent_positions=5,
        max_daily_loss_pct=5.0,
        max_trades_per_hour=20,
        per_symbol_exposure_cap=10000.0,
        reconcile_interval_s=5,
    )


@pytest.fixture
def position_store() -> PositionStore:
    """Create position store."""
    return PositionStore()


@pytest.fixture
def reconciliation_service(
    default_config: ExecutionConfig,
    position_store: PositionStore,
) -> ReconciliationService:
    """Create reconciliation service."""
    return ReconciliationService(default_config, position_store)


# =============================================================================
# PositionStore Tests
# =============================================================================


class TestPositionStore:
    """Tests for PositionStore."""

    def test_update_from_broker(self, position_store: PositionStore) -> None:
        """Should update positions from broker snapshot."""
        positions = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            ),
        ]

        position_store.update_from_broker(positions)

        assert position_store.get_position("deal_1") == positions[0]
        assert position_store.count == 1

    def test_update_replaces_existing(self, position_store: PositionStore) -> None:
        """Should replace existing positions on update."""
        positions1 = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            ),
        ]
        positions2 = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.3,  # Changed size
                open_level=1.1000,
            ),
        ]

        position_store.update_from_broker(positions1)
        position_store.update_from_broker(positions2)

        assert position_store.get_position("deal_1").size == 0.3
        assert position_store.count == 1

    def test_clear_positions(self, position_store: PositionStore) -> None:
        """Should clear all positions."""
        positions = [
            PositionView(
                deal_id=f"deal_{i}",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.1,
                open_level=1.1000,
            )
            for i in range(3)
        ]
        position_store.update_from_broker(positions)

        position_store.clear()

        assert position_store.count == 0

    def test_get_positions_by_epic(self, position_store: PositionStore) -> None:
        """Should filter positions by epic."""
        positions = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            ),
            PositionView(
                deal_id="deal_2",
                epic="CS.D.GBPUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.3,
                open_level=1.3000,
            ),
        ]
        position_store.update_from_broker(positions)

        eurusd_positions = position_store.get_positions_by_epic("CS.D.EURUSD.MINI.IP")
        assert len(eurusd_positions) == 1
        assert eurusd_positions[0].deal_id == "deal_1"

    def test_get_deal_ids(self, position_store: PositionStore) -> None:
        """Should return all deal IDs."""
        positions = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            ),
            PositionView(
                deal_id="deal_2",
                epic="CS.D.GBPUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.3,
                open_level=1.3000,
            ),
        ]
        position_store.update_from_broker(positions)

        deal_ids = position_store.get_deal_ids()
        assert deal_ids == {"deal_1", "deal_2"}


# =============================================================================
# ReconciliationService Tests
# =============================================================================


class TestReconciliationService:
    """Tests for ReconciliationService."""

    @pytest.mark.asyncio
    async def test_reconcile_no_drift(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should detect no drift when positions match."""
        # Setup: broker has one position
        broker_position = {
            "position": {
                "dealId": "deal_1",
                "direction": "BUY",
                "size": 0.5,
                "openLevel": 1.1000,
            },
            "market": {
                "epic": "CS.D.EURUSD.MINI.IP",
                "instrumentName": "EUR/USD",
            },
        }
        mock_ig_client.list_positions.return_value = [broker_position]

        # Pre-populate local store with same position
        position_store.update_from_broker([
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            )
        ])

        # Reconcile
        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert not result.error
        assert not result.has_drift
        assert len(result.missing_locally) == 0
        assert len(result.missing_on_broker) == 0

    @pytest.mark.asyncio
    async def test_reconcile_detects_new_position(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should detect new position from broker."""
        # Broker has a position not in local store
        broker_position = {
            "position": {
                "dealId": "deal_new",
                "direction": "BUY",
                "size": 0.5,
                "openLevel": 1.1000,
            },
            "market": {
                "epic": "CS.D.EURUSD.MINI.IP",
                "instrumentName": "EUR/USD",
            },
        }
        mock_ig_client.list_positions.return_value = [broker_position]

        # Reconcile with empty local store
        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert not result.error
        assert result.has_drift
        assert "deal_new" in result.missing_locally
        # Position should now be in local store
        assert position_store.get_position("deal_new") is not None

    @pytest.mark.asyncio
    async def test_reconcile_detects_removed_position(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should detect position removed at broker."""
        # Local store has position
        position_store.update_from_broker([
            PositionView(
                deal_id="deal_closed",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            )
        ])

        # Broker returns empty (position closed externally)
        mock_ig_client.list_positions.return_value = []

        # Reconcile
        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert not result.error
        assert result.has_drift
        assert "deal_closed" in result.missing_on_broker
        # Position should be removed from local store
        assert position_store.get_position("deal_closed") is None

    @pytest.mark.asyncio
    async def test_reconcile_detects_size_change(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should detect position size change."""
        # Local store has position with size 0.5
        position_store.update_from_broker([
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            )
        ])

        # Broker shows different size (partial close externally)
        broker_position = {
            "position": {
                "dealId": "deal_1",
                "direction": "BUY",
                "size": 0.3,  # Changed
                "openLevel": 1.1000,
            },
            "market": {
                "epic": "CS.D.EURUSD.MINI.IP",
                "instrumentName": "EUR/USD",
            },
        }
        mock_ig_client.list_positions.return_value = [broker_position]

        # Reconcile
        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert not result.error
        assert result.has_drift
        assert "deal_1" in result.size_mismatches
        # Local store should be updated
        updated = position_store.get_position("deal_1")
        assert updated.size == 0.3

    @pytest.mark.asyncio
    async def test_reconcile_handles_api_error(
        self,
        reconciliation_service: ReconciliationService,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should handle API error gracefully."""
        mock_ig_client.list_positions.side_effect = Exception("API timeout")

        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert result.error is not None
        assert "API timeout" in result.error
        assert result.has_drift  # Error = potential drift

    @pytest.mark.asyncio
    async def test_reconcile_multiple_positions(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should handle multiple positions correctly."""
        # Local store has 2 positions
        position_store.update_from_broker([
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.5,
                open_level=1.1000,
            ),
            PositionView(
                deal_id="deal_2",
                epic="CS.D.GBPUSD.MINI.IP",
                direction=OrderSide.SELL,
                size=0.3,
                open_level=1.3000,
            ),
        ])

        # Broker returns: deal_1 unchanged, deal_2 closed, deal_3 new
        mock_ig_client.list_positions.return_value = [
            {
                "position": {
                    "dealId": "deal_1",
                    "direction": "BUY",
                    "size": 0.5,
                    "openLevel": 1.1000,
                },
                "market": {
                    "epic": "CS.D.EURUSD.MINI.IP",
                    "instrumentName": "EUR/USD",
                },
            },
            {
                "position": {
                    "dealId": "deal_3",
                    "direction": "BUY",
                    "size": 0.2,
                    "openLevel": 150.00,
                },
                "market": {
                    "epic": "CS.D.USDJPY.MINI.IP",
                    "instrumentName": "USD/JPY",
                },
            },
        ]

        result = await reconciliation_service.reconcile_once(mock_ig_client)

        assert result.has_drift
        assert "deal_3" in result.missing_locally
        assert "deal_2" in result.missing_on_broker
        assert len(result.size_mismatches) == 0

    def test_properties(
        self,
        reconciliation_service: ReconciliationService,
    ) -> None:
        """Should expose properties correctly."""
        assert reconciliation_service.is_running is False
        assert reconciliation_service.last_result is None


# =============================================================================
# Position Conversion Tests
# =============================================================================


class TestPositionConversion:
    """Tests for broker position to PositionView conversion."""

    @pytest.mark.asyncio
    async def test_converts_broker_position_format(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should correctly convert IG position format."""
        broker_position = {
            "position": {
                "dealId": "DIAAAAA123456",
                "direction": "BUY",
                "size": 1.5,
                "openLevel": 1.10523,
                "stopLevel": 1.10000,
                "limitLevel": 1.11500,
                "currency": "USD",
                "contractSize": 10000,
            },
            "market": {
                "epic": "CS.D.EURUSD.MINI.IP",
                "instrumentName": "EUR/USD Mini",
                "instrumentType": "CURRENCIES",
            },
        }
        mock_ig_client.list_positions.return_value = [broker_position]

        await reconciliation_service.reconcile_once(mock_ig_client)

        position = position_store.get_position("DIAAAAA123456")
        assert position is not None
        assert position.deal_id == "DIAAAAA123456"
        assert position.epic == "CS.D.EURUSD.MINI.IP"
        assert position.direction == OrderSide.BUY
        assert position.size == 1.5
        assert position.open_level == 1.10523

    @pytest.mark.asyncio
    async def test_handles_sell_direction(
        self,
        reconciliation_service: ReconciliationService,
        position_store: PositionStore,
        mock_ig_client: AsyncMock,
    ) -> None:
        """Should correctly parse SELL direction."""
        broker_position = {
            "position": {
                "dealId": "deal_sell",
                "direction": "SELL",
                "size": 0.5,
                "openLevel": 1.1000,
            },
            "market": {
                "epic": "CS.D.EURUSD.MINI.IP",
                "instrumentName": "EUR/USD",
            },
        }
        mock_ig_client.list_positions.return_value = [broker_position]

        await reconciliation_service.reconcile_once(mock_ig_client)

        position = position_store.get_position("deal_sell")
        assert position.direction == OrderSide.SELL
