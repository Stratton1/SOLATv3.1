"""
Event bus for internal pub/sub messaging.

Provides decoupled communication between engine components.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventType(str, Enum):
    """Types of events in the system."""

    # Lifecycle events
    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"

    # Data events
    BAR_RECEIVED = "data.bar_received"
    QUOTE_RECEIVED = "data.quote_received"

    # Signal events
    SIGNAL_GENERATED = "signal.generated"
    SIGNAL_REJECTED = "signal.rejected"

    # Order events
    ORDER_CREATED = "order.created"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_REJECTED = "order.rejected"
    ORDER_FILLED = "order.filled"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_CANCELLED = "order.cancelled"

    # Position events
    POSITION_OPENED = "position.opened"
    POSITION_UPDATED = "position.updated"
    POSITION_CLOSED = "position.closed"

    # Risk events
    RISK_LIMIT_REACHED = "risk.limit_reached"
    KILL_SWITCH_TRIGGERED = "risk.kill_switch"

    # Backtest events
    BACKTEST_STARTED = "backtest.started"
    BACKTEST_PROGRESS = "backtest.progress"
    BACKTEST_COMPLETED = "backtest.completed"

    # Data sync events
    SYNC_STARTED = "sync.started"
    SYNC_PROGRESS = "sync.progress"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"

    # Connection events
    BROKER_CONNECTED = "broker.connected"
    BROKER_DISCONNECTED = "broker.disconnected"
    BROKER_ERROR = "broker.error"

    # Execution events
    EXECUTION_STATUS = "execution.status"
    EXECUTION_INTENT_CREATED = "execution.intent_created"
    EXECUTION_ORDER_SUBMITTED = "execution.order_submitted"
    EXECUTION_ORDER_REJECTED = "execution.order_rejected"
    EXECUTION_ORDER_ACKNOWLEDGED = "execution.order_acknowledged"
    EXECUTION_POSITIONS_UPDATED = "execution.positions_updated"
    EXECUTION_RECONCILIATION_WARNING = "execution.reconciliation_warning"
    EXECUTION_KILL_SWITCH_ACTIVATED = "execution.kill_switch_activated"
    EXECUTION_KILL_SWITCH_RESET = "execution.kill_switch_reset"

    # Recommendation events
    RECOMMENDATION_GENERATED = "recommendation.generated"
    RECOMMENDATION_APPLIED = "recommendation.applied"

    # Autopilot events
    AUTOPILOT_ENABLED = "autopilot.enabled"
    AUTOPILOT_DISABLED = "autopilot.disabled"
    AUTOPILOT_SIGNAL = "autopilot.signal"

    # Derive events
    DERIVE_STARTED = "derive.started"
    DERIVE_PROGRESS = "derive.progress"
    DERIVE_COMPLETED = "derive.completed"

    # System events
    HEARTBEAT = "system.heartbeat"
    ERROR = "system.error"
    WARNING = "system.warning"


@dataclass
class Event:
    """
    An event in the system.

    Carries type, timestamp, and arbitrary payload data.
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None

    def __hash__(self) -> int:
        return hash(self.id)


# Type for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Simple async event bus for internal pub/sub.

    Supports:
    - Multiple handlers per event type
    - Wildcard subscriptions
    - Async handlers
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._wildcard_handlers: list[EventHandler] = []
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        event_type: EventType | None,
        handler: EventHandler,
    ) -> None:
        """
        Subscribe to events.

        Args:
            event_type: Event type to subscribe to, or None for all events
            handler: Async handler function
        """
        async with self._lock:
            if event_type is None:
                self._wildcard_handlers.append(handler)
            else:
                if event_type not in self._handlers:
                    self._handlers[event_type] = []
                self._handlers[event_type].append(handler)

    async def unsubscribe(
        self,
        event_type: EventType | None,
        handler: EventHandler,
    ) -> None:
        """
        Unsubscribe from events.

        Args:
            event_type: Event type, or None for wildcard
            handler: Handler to remove
        """
        async with self._lock:
            if event_type is None:
                if handler in self._wildcard_handlers:
                    self._wildcard_handlers.remove(handler)
            else:
                if event_type in self._handlers:
                    handlers = self._handlers[event_type]
                    if handler in handlers:
                        handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event: Event to publish
        """
        handlers: list[EventHandler] = []

        async with self._lock:
            # Get type-specific handlers
            if event.type in self._handlers:
                handlers.extend(self._handlers[event.type])
            # Add wildcard handlers
            handlers.extend(self._wildcard_handlers)

        # Invoke all handlers concurrently
        if handlers:
            await asyncio.gather(
                *[handler(event) for handler in handlers],
                return_exceptions=True,
            )

    async def clear(self) -> None:
        """Remove all handlers."""
        async with self._lock:
            self._handlers.clear()
            self._wildcard_handlers.clear()


# Global event bus instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _event_bus
    _event_bus = None
