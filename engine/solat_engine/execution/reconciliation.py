"""
Reconciliation Service.

Periodically syncs local position state with broker (source of truth).
Detects and reports drift between local and broker positions.
"""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from solat_engine.execution.models import (
    ExecutionConfig,
    OrderSide,
    PositionSnapshot,
    PositionView,
    ReconciliationResult,
)
from solat_engine.logging import get_logger

if TYPE_CHECKING:
    from solat_engine.execution.ledger import ExecutionLedger

logger = get_logger(__name__)


class PositionStore:
    """
    In-memory store of positions (broker truth).

    Updated by reconciliation service.
    """

    def __init__(self) -> None:
        self._positions: dict[str, PositionView] = {}  # deal_id -> position
        self._last_updated: datetime | None = None

    @property
    def positions(self) -> list[PositionView]:
        """Get all positions."""
        return list(self._positions.values())

    @property
    def count(self) -> int:
        """Get position count."""
        return len(self._positions)

    @property
    def last_updated(self) -> datetime | None:
        """Get last update timestamp."""
        return self._last_updated

    def update_from_broker(self, positions: list[PositionView]) -> None:
        """Update positions from broker snapshot."""
        self._positions = {p.deal_id: p for p in positions}
        self._last_updated = datetime.now(UTC)

    def get_position(self, deal_id: str) -> PositionView | None:
        """Get position by deal ID."""
        return self._positions.get(deal_id)

    def get_positions_by_symbol(self, symbol: str) -> list[PositionView]:
        """Get positions for a symbol."""
        return [p for p in self._positions.values() if p.symbol == symbol]

    def get_positions_by_epic(self, epic: str) -> list[PositionView]:
        """Get positions for an epic."""
        return [p for p in self._positions.values() if p.epic == epic]

    def get_deal_ids(self) -> set[str]:
        """Get all deal IDs."""
        return set(self._positions.keys())

    def clear(self) -> None:
        """Clear all positions."""
        self._positions.clear()
        self._last_updated = None


class ReconciliationService:
    """
    Background service for position reconciliation.

    Periodically fetches broker positions and compares with local state.
    Broker is always the source of truth.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        position_store: PositionStore,
        ledger: "ExecutionLedger | None" = None,
    ):
        """
        Initialize reconciliation service.

        Args:
            config: Execution configuration
            position_store: Position store to update
            ledger: Optional execution ledger for audit
        """
        self._config = config
        self._position_store = position_store
        self._ledger = ledger
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_result: ReconciliationResult | None = None
        self._event_callback: Any = None  # Set by router for WS events

    @property
    def is_running(self) -> bool:
        """Check if reconciliation loop is running."""
        return self._running

    @property
    def last_result(self) -> ReconciliationResult | None:
        """Get last reconciliation result."""
        return self._last_result

    @property
    def last_reconcile_time(self) -> datetime | None:
        """Get timestamp of last successful reconciliation."""
        return self._position_store.last_updated

    def get_discrepancies(self) -> list[dict[str, Any]]:
        """
        Get list of discrepancies from last reconciliation.

        Returns empty list if no drift detected.
        """
        if self._last_result is None:
            return []

        discrepancies: list[dict[str, Any]] = []

        # Missing locally (on broker but not tracked)
        for deal_id in self._last_result.missing_locally:
            discrepancies.append({
                "type": "missing_locally",
                "deal_id": deal_id,
                "message": f"Position {deal_id} exists on broker but not tracked locally",
            })

        # Missing on broker (tracked but not on broker)
        for deal_id in self._last_result.missing_on_broker:
            discrepancies.append({
                "type": "missing_on_broker",
                "deal_id": deal_id,
                "message": f"Position {deal_id} tracked locally but not on broker",
            })

        # Size mismatches
        for deal_id in self._last_result.size_mismatches:
            discrepancies.append({
                "type": "size_mismatch",
                "deal_id": deal_id,
                "message": f"Position {deal_id} has different size locally vs broker",
            })

        return discrepancies

    def get_warnings(self) -> list[str]:
        """
        Get list of reconciliation warnings.

        Returns warnings about potential issues.
        """
        warnings: list[str] = []

        if self._last_result is None:
            warnings.append("No reconciliation has been performed")
            return warnings

        if self._last_result.error:
            warnings.append(f"Last reconciliation error: {self._last_result.error}")

        if self._last_result.has_drift:
            warnings.append("Position drift detected - local state differs from broker")

        # Check staleness
        last_time = self.last_reconcile_time
        if last_time:
            age = (datetime.now(UTC) - last_time).total_seconds()
            if age > 300:
                warnings.append(f"Reconciliation is stale ({age:.0f}s old)")

        return warnings

    def set_event_callback(self, callback: Any) -> None:
        """Set callback for emitting WS events."""
        self._event_callback = callback

    async def start(self, broker_adapter: Any) -> None:
        """
        Start reconciliation loop.

        Args:
            broker_adapter: Broker adapter with list_positions method
        """
        if self._running:
            logger.warning("Reconciliation service already running")
            return

        self._running = True
        self._task = asyncio.create_task(
            self._reconciliation_loop(broker_adapter)
        )
        logger.info(
            "Reconciliation service started (interval: %ds)",
            self._config.reconcile_interval_s,
        )

    async def stop(self) -> None:
        """Stop reconciliation loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Reconciliation service stopped")

    async def _reconciliation_loop(self, broker_adapter: Any) -> None:
        """Main reconciliation loop."""
        while self._running:
            try:
                result = await self.reconcile_once(broker_adapter)
                self._last_result = result

                # Emit event if callback set
                if self._event_callback:
                    await self._event_callback({
                        "type": "positions_updated",
                        "count": result.broker_positions,
                        "has_drift": result.has_drift,
                    })

                if result.has_drift:
                    logger.warning(
                        "Position drift detected: missing_locally=%s, missing_on_broker=%s",
                        result.missing_locally,
                        result.missing_on_broker,
                    )
                    if self._event_callback:
                        await self._event_callback({
                            "type": "reconciliation_warning",
                            "drift": True,
                            "details": result.model_dump(),
                        })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Reconciliation error: %s", e)
                self._last_result = ReconciliationResult(
                    error=str(e),
                    has_drift=True,
                )

            await asyncio.sleep(self._config.reconcile_interval_s)

    async def reconcile_once(self, broker_adapter: Any) -> ReconciliationResult:
        """
        Perform single reconciliation.

        Args:
            broker_adapter: Broker adapter with list_positions method

        Returns:
            ReconciliationResult with drift details
        """
        # Get broker positions
        try:
            broker_positions = await broker_adapter.list_positions()
        except Exception as e:
            logger.error("Failed to fetch broker positions: %s", e)
            return ReconciliationResult(
                error=str(e),
                has_drift=True,
            )

        # Convert to PositionView if needed
        positions = self._convert_broker_positions(broker_positions)

        # Get local deal IDs before update
        local_deal_ids = self._position_store.get_deal_ids()
        broker_deal_ids = {p.deal_id for p in positions}

        # Detect drift
        missing_locally = list(broker_deal_ids - local_deal_ids)
        missing_on_broker = list(local_deal_ids - broker_deal_ids)

        # Check for size mismatches on common positions
        size_mismatches = []
        for deal_id in broker_deal_ids & local_deal_ids:
            local_pos = self._position_store.get_position(deal_id)
            broker_pos = next((p for p in positions if p.deal_id == deal_id), None)
            if local_pos and broker_pos and abs(local_pos.size - broker_pos.size) > 0.0001:
                size_mismatches.append(deal_id)

        # Update local store (broker is truth)
        self._position_store.update_from_broker(positions)

        # Create snapshot for ledger
        snapshot = PositionSnapshot(
            positions=positions,
            total_count=len(positions),
            total_unrealized_pnl=sum(p.unrealized_pnl or 0 for p in positions),
        )
        if self._ledger:
            self._ledger.record_position_snapshot(snapshot)

        has_drift = bool(missing_locally or missing_on_broker or size_mismatches)

        result = ReconciliationResult(
            broker_positions=len(positions),
            local_positions=len(local_deal_ids),
            missing_locally=missing_locally,
            missing_on_broker=missing_on_broker,
            size_mismatches=size_mismatches,
            has_drift=has_drift,
        )

        # Log to ledger
        if self._ledger:
            self._ledger.record_reconciliation(
                broker_count=len(positions),
                local_count=len(local_deal_ids),
                drift_detected=has_drift,
                details={
                    "missing_locally": missing_locally,
                    "missing_on_broker": missing_on_broker,
                    "size_mismatches": size_mismatches,
                },
            )

        return result

    def _convert_broker_positions(
        self,
        broker_positions: list[dict[str, Any]],
    ) -> list[PositionView]:
        """Convert broker position dicts to PositionView models."""
        positions = []
        for pos in broker_positions:
            # Handle IG position format
            position_data = pos.get("position", pos)
            market_data = pos.get("market", {})

            direction_str = position_data.get("direction", "BUY")
            direction = OrderSide.BUY if direction_str == "BUY" else OrderSide.SELL

            positions.append(PositionView(
                deal_id=position_data.get("dealId", ""),
                epic=market_data.get("epic", position_data.get("epic", "")),
                symbol=market_data.get("instrumentName", position_data.get("symbol")),
                direction=direction,
                size=float(position_data.get("size", position_data.get("dealSize", 0))),
                open_level=float(position_data.get("openLevel", position_data.get("level", 0))),
                current_level=float(market_data.get("bid", 0)) if market_data else None,
                stop_level=float(position_data.get("stopLevel", 0)) if position_data.get("stopLevel") else None,
                limit_level=float(position_data.get("limitLevel", 0)) if position_data.get("limitLevel") else None,
                unrealized_pnl=float(position_data.get("profit", 0)) if position_data.get("profit") else None,
                currency=position_data.get("currency", "USD"),
            ))

        return positions

    def update_config(self, config: ExecutionConfig) -> None:
        """Update configuration."""
        self._config = config
