"""
WebSocket event throttler and batcher.

Provides intelligent throttling and compression for WebSocket event delivery:
- Quotes: max N updates/sec per symbol (handled by MarketDataPublisher)
- Bars: never dropped, always delivered
- Execution events: compressed to remove repeated 'status unchanged' noise
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from solat_engine.logging import get_logger
from solat_engine.runtime.event_bus import Event, EventType

logger = get_logger(__name__)


@dataclass
class ThrottleStats:
    """Throttle statistics."""

    events_received: int = 0
    events_delivered: int = 0
    events_compressed: int = 0
    events_dropped: int = 0
    last_delivery_ts: datetime | None = None


@dataclass
class ExecutionEventState:
    """Tracks the last state of execution events for compression."""

    # Last known execution status hash for dedup
    last_status_hash: str = ""
    last_status_ts: datetime | None = None

    # Positions - last known state per symbol
    last_positions: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Suppress duplicate status events within this window
    status_dedup_window_s: float = 2.0


class ExecutionEventCompressor:
    """
    Compresses execution events to reduce WS noise.

    Filters:
    - Duplicate EXECUTION_STATUS with identical content within window
    - EXECUTION_POSITIONS_UPDATED with no actual changes

    Never drops:
    - ORDER events (submitted, rejected, acknowledged)
    - INTENT events
    - KILL_SWITCH events
    - RECONCILIATION_WARNING events
    """

    # Events that are ALWAYS delivered (never compressed)
    CRITICAL_EVENTS = frozenset(
        {
            EventType.EXECUTION_INTENT_CREATED,
            EventType.EXECUTION_ORDER_SUBMITTED,
            EventType.EXECUTION_ORDER_REJECTED,
            EventType.EXECUTION_ORDER_ACKNOWLEDGED,
            EventType.EXECUTION_RECONCILIATION_WARNING,
            EventType.EXECUTION_KILL_SWITCH_ACTIVATED,
            EventType.EXECUTION_KILL_SWITCH_RESET,
        }
    )

    # Events that can be compressed (deduplicated)
    COMPRESSIBLE_EVENTS = frozenset(
        {
            EventType.EXECUTION_STATUS,
            EventType.EXECUTION_POSITIONS_UPDATED,
        }
    )

    def __init__(self, dedup_window_s: float = 2.0):
        """
        Initialize compressor.

        Args:
            dedup_window_s: Time window for deduplicating status events
        """
        self._state = ExecutionEventState(status_dedup_window_s=dedup_window_s)
        self._stats = ThrottleStats()

    def should_deliver(self, event: Event) -> bool:
        """
        Determine if an execution event should be delivered.

        Args:
            event: Event to check

        Returns:
            True if the event should be delivered, False to compress/drop
        """
        self._stats.events_received += 1

        # Critical events are always delivered
        if event.type in self.CRITICAL_EVENTS:
            self._stats.events_delivered += 1
            self._stats.last_delivery_ts = datetime.now(UTC)
            return True

        # Check for compressible events
        if event.type == EventType.EXECUTION_STATUS:
            return self._should_deliver_status(event)

        if event.type == EventType.EXECUTION_POSITIONS_UPDATED:
            return self._should_deliver_positions(event)

        # Unknown execution event - deliver to be safe
        self._stats.events_delivered += 1
        self._stats.last_delivery_ts = datetime.now(UTC)
        return True

    def _should_deliver_status(self, event: Event) -> bool:
        """Check if status event should be delivered."""
        # Create hash of status content for dedup
        status_hash = self._hash_status(event.data)
        now = datetime.now(UTC)

        # Check if this is a duplicate within the dedup window
        if (
            status_hash == self._state.last_status_hash
            and self._state.last_status_ts is not None
        ):
            elapsed = (now - self._state.last_status_ts).total_seconds()
            if elapsed < self._state.status_dedup_window_s:
                self._stats.events_compressed += 1
                return False

        # New status or outside dedup window - deliver
        self._state.last_status_hash = status_hash
        self._state.last_status_ts = now
        self._stats.events_delivered += 1
        self._stats.last_delivery_ts = now
        return True

    def _should_deliver_positions(self, event: Event) -> bool:
        """Check if positions update should be delivered."""
        # Extract positions from event
        positions = event.data.get("positions", {})

        # Check if positions actually changed
        if self._positions_unchanged(positions):
            self._stats.events_compressed += 1
            return False

        # Positions changed - update state and deliver
        self._state.last_positions = self._snapshot_positions(positions)
        self._stats.events_delivered += 1
        self._stats.last_delivery_ts = datetime.now(UTC)
        return True

    def _hash_status(self, data: dict[str, Any]) -> str:
        """Create a hash of status data for dedup comparison."""
        # Extract key fields that indicate actual state change
        key_fields = (
            data.get("running"),
            data.get("paused"),
            data.get("kill_switch_active"),
            data.get("open_position_count"),
            data.get("pending_intent_count"),
        )
        return str(key_fields)

    def _positions_unchanged(self, positions: dict[str, Any]) -> bool:
        """Check if positions are unchanged from last known state."""
        current = self._snapshot_positions(positions)
        return current == self._state.last_positions

    def _snapshot_positions(self, positions: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Create a snapshot of positions for comparison."""
        snapshot = {}
        if isinstance(positions, dict):
            for symbol, pos in positions.items():
                if isinstance(pos, dict):
                    snapshot[symbol] = {
                        "size": pos.get("size"),
                        "side": pos.get("side"),
                        "entry_price": pos.get("entry_price"),
                    }
        return snapshot

    def reset(self) -> None:
        """Reset compressor state."""
        self._state = ExecutionEventState(
            status_dedup_window_s=self._state.status_dedup_window_s
        )

    @property
    def stats(self) -> ThrottleStats:
        """Get compressor statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = ThrottleStats()


DeliveryCallback = Callable[[Event], Coroutine[Any, Any, None]]


class WSEventThrottler:
    """
    Unified WebSocket event throttler.

    Coordinates throttling across event types:
    - Execution events: compressed via ExecutionEventCompressor
    - Market data: delegated to MarketDataPublisher (separate concern)

    Features:
    - Per-event-type throttling
    - Batching with configurable flush interval
    - Statistics tracking
    """

    def __init__(
        self,
        execution_dedup_window_s: float = 2.0,
        batch_flush_interval_ms: int = 100,
        enable_batching: bool = False,
    ):
        """
        Initialize throttler.

        Args:
            execution_dedup_window_s: Dedup window for execution status
            batch_flush_interval_ms: Batch flush interval (if batching enabled)
            enable_batching: Enable event batching (combines events into arrays)
        """
        self._execution_compressor = ExecutionEventCompressor(
            dedup_window_s=execution_dedup_window_s
        )
        self._batch_interval_ms = batch_flush_interval_ms
        self._enable_batching = enable_batching

        # Pending batch (if batching enabled)
        self._pending_batch: list[dict[str, Any]] = []
        self._batch_lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None

        # Delivery callback (set by user)
        self._deliver: DeliveryCallback | None = None

        # Stats
        self._total_received = 0
        self._total_delivered = 0

    def set_delivery_callback(self, callback: DeliveryCallback) -> None:
        """Set the delivery callback for processed events."""
        self._deliver = callback

    async def start(self) -> None:
        """Start the throttler (starts batch flush task if batching enabled)."""
        if self._enable_batching and self._flush_task is None:
            self._flush_task = asyncio.create_task(self._batch_flush_loop())
            logger.info(
                "WSEventThrottler started with batching (flush interval: %dms)",
                self._batch_interval_ms,
            )
        else:
            logger.info("WSEventThrottler started (batching disabled)")

    async def stop(self) -> None:
        """Stop the throttler."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush any remaining batch
        await self._flush_batch()

    async def process_event(self, event: Event) -> bool:
        """
        Process an event for delivery.

        Applies appropriate throttling based on event type.

        Args:
            event: Event to process

        Returns:
            True if event was accepted for delivery
        """
        self._total_received += 1

        # Check if this is an execution event that should be compressed
        if event.type.value.startswith("execution.") and not self._execution_compressor.should_deliver(event):
            return False

        # If batching is enabled, add to batch
        if self._enable_batching:
            async with self._batch_lock:
                self._pending_batch.append(self._event_to_message(event))
            return True

        # Direct delivery
        if self._deliver is not None:
            await self._deliver(event)
            self._total_delivered += 1

        return True

    async def _batch_flush_loop(self) -> None:
        """Background task to flush batched events."""
        interval = self._batch_interval_ms / 1000.0

        while True:
            try:
                await asyncio.sleep(interval)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Batch flush error: %s", e)

    async def _flush_batch(self) -> None:
        """Flush pending batch to delivery callback."""
        async with self._batch_lock:
            if not self._pending_batch:
                return

            batch = self._pending_batch
            self._pending_batch = []

        if self._deliver is not None and batch:
            # Create a batch event
            batch_event = Event(
                type=EventType.HEARTBEAT,  # Placeholder type
                data={"batch": batch, "count": len(batch)},
            )
            await self._deliver(batch_event)
            self._total_delivered += len(batch)

    def _event_to_message(self, event: Event) -> dict[str, Any]:
        """Convert event to WS message format."""
        return {
            "type": event.type.value,
            "timestamp": event.timestamp.isoformat(),
            "run_id": event.run_id,
            **event.data,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get throttler statistics."""
        exec_stats = self._execution_compressor.stats
        return {
            "total_received": self._total_received,
            "total_delivered": self._total_delivered,
            "execution_events": {
                "received": exec_stats.events_received,
                "delivered": exec_stats.events_delivered,
                "compressed": exec_stats.events_compressed,
            },
            "batching_enabled": self._enable_batching,
            "batch_pending": len(self._pending_batch),
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._total_received = 0
        self._total_delivered = 0
        self._execution_compressor.reset_stats()


# Global throttler instance
_throttler: WSEventThrottler | None = None


def get_ws_throttler() -> WSEventThrottler:
    """Get global WS throttler instance."""
    global _throttler
    if _throttler is None:
        _throttler = WSEventThrottler()
    return _throttler


def reset_ws_throttler() -> None:
    """Reset global throttler (for testing)."""
    global _throttler
    _throttler = None
