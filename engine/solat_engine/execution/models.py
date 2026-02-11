"""
Execution models for live trading.

All models are Pydantic-based for validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Execution environment mode."""

    DEMO = "DEMO"
    LIVE = "LIVE"  # Not enabled in v1


class OrderSide(str, Enum):
    """Order direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    """
    Order lifecycle status.

    Valid state transitions (order state machine):
    - PENDING -> SUBMITTED (order sent to broker)
    - SUBMITTED -> ACKNOWLEDGED (broker received)
    - SUBMITTED -> REJECTED (broker rejected)
    - SUBMITTED -> EXPIRED (timeout)
    - ACKNOWLEDGED -> FILLED (execution complete)
    - ACKNOWLEDGED -> REJECTED (late rejection)
    - ACKNOWLEDGED -> CANCELLED (user cancelled)
    - PENDING -> REJECTED (pre-flight rejection)

    Terminal states: FILLED, REJECTED, CANCELLED, EXPIRED
    """

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state."""
        return self in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        )

    @property
    def is_active(self) -> bool:
        """Check if order is still active (not terminal)."""
        return not self.is_terminal


# Valid order state transitions
ORDER_STATE_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.REJECTED},
    OrderStatus.SUBMITTED: {
        OrderStatus.ACKNOWLEDGED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.FILLED,  # Direct fill without ACK (some brokers)
    },
    OrderStatus.ACKNOWLEDGED: {
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    # Terminal states have no valid transitions
    OrderStatus.FILLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
}


def validate_order_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    """
    Validate if a state transition is allowed.

    Args:
        from_status: Current order status
        to_status: Proposed new status

    Returns:
        True if transition is valid, False otherwise.
    """
    valid_next = ORDER_STATE_TRANSITIONS.get(from_status, set())
    return to_status in valid_next


class ExecutionState(BaseModel):
    """Current execution system state."""

    mode: ExecutionMode = ExecutionMode.DEMO
    connected: bool = False
    armed: bool = False
    kill_switch_active: bool = False
    signals_enabled: bool = True
    demo_arm_enabled: bool = False
    last_error: str | None = None
    last_error_ts: datetime | None = None
    session_start: datetime | None = None
    account_id: str | None = None
    account_balance: float | None = None
    open_position_count: int = 0
    realized_pnl_today: float = 0.0
    trades_this_hour: int = 0


class OrderIntent(BaseModel):
    """
    Strategy's intent to place an order.

    Created by strategies, validated by RiskEngine, then submitted to broker.
    """

    intent_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    symbol: str
    epic: str | None = None  # IG epic, resolved if not provided
    side: OrderSide
    size: float
    order_type: OrderType = OrderType.MARKET
    stop_loss: float | None = None
    take_profit: float | None = None
    bot: str
    reason_codes: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskCheckResult(BaseModel):
    """Result of risk engine validation."""

    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    adjusted_size: float = 0.0
    original_size: float = 0.0
    rejection_reason: str | None = None


class OrderAck(BaseModel):
    """
    Acknowledgment from broker after order submission.

    Contains broker-specific references for tracking.
    """

    intent_id: UUID
    deal_reference: str | None = None  # Client-generated reference
    deal_id: str | None = None  # Broker-assigned ID after fill
    status: OrderStatus
    filled_size: float | None = None
    filled_price: float | None = None
    rejection_reason: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    raw_response: dict[str, Any] | None = None  # Redacted broker response


class PositionView(BaseModel):
    """
    View of a broker position.

    Represents the broker's truth about an open position.
    """

    deal_id: str
    epic: str
    symbol: str | None = None  # Resolved from epic
    direction: OrderSide
    size: float
    open_level: float
    current_level: float | None = None
    stop_level: float | None = None
    limit_level: float | None = None
    unrealized_pnl: float | None = None
    currency: str = "USD"
    created_at: datetime | None = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now())


class PositionSnapshot(BaseModel):
    """Snapshot of all positions at a point in time."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    positions: list[PositionView] = Field(default_factory=list)
    total_count: int = 0
    total_unrealized_pnl: float = 0.0


class ReconciliationResult(BaseModel):
    """Result of position reconciliation."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    broker_positions: int = 0
    local_positions: int = 0
    missing_locally: list[str] = Field(default_factory=list)  # deal_ids on broker but not local
    missing_on_broker: list[str] = Field(default_factory=list)  # deal_ids local but not on broker
    size_mismatches: list[str] = Field(default_factory=list)
    has_drift: bool = False
    error: str | None = None


class ExecutionConfig(BaseModel):
    """Configuration for execution engine."""

    mode: ExecutionMode = ExecutionMode.DEMO
    max_position_size: float = 1.0
    max_concurrent_positions: int = 5
    max_daily_loss_pct: float = 5.0
    max_trades_per_hour: int = 20
    per_symbol_exposure_cap: float = 10000.0
    require_sl: bool = False
    close_on_kill_switch: bool = False
    reconcile_interval_s: int = 5
    require_arm_confirmation: bool = True


class LedgerEntry(BaseModel):
    """Single entry in the execution ledger."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    entry_type: str  # intent, submission, ack, error, reconciliation, kill_switch
    intent_id: UUID | None = None
    deal_reference: str | None = None
    deal_id: str | None = None
    symbol: str | None = None
    side: OrderSide | None = None
    size: float | None = None
    status: OrderStatus | None = None
    reason_codes: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderTracker(BaseModel):
    """
    Tracks an order through its lifecycle for idempotency and state validation.

    Used to:
    - Prevent duplicate order submission (deal_reference tracking)
    - Validate state transitions
    - Correlate broker responses with intents
    """

    intent_id: UUID
    deal_reference: str
    deal_id: str | None = None
    symbol: str
    side: OrderSide
    size: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    submitted_at: datetime | None = None
    acked_at: datetime | None = None
    filled_at: datetime | None = None
    terminal_at: datetime | None = None
    status_history: list[tuple[OrderStatus, datetime]] = Field(default_factory=list)
    broker_responses: list[dict[str, Any]] = Field(default_factory=list)

    def transition_to(self, new_status: OrderStatus) -> bool:
        """
        Attempt to transition to a new status.

        Returns True if transition was valid and applied.
        Returns False if transition was invalid (no state change).
        """
        if new_status == self.status:
            return True  # Already in this state

        if not validate_order_transition(self.status, new_status):
            return False

        now = datetime.now()
        self.status_history.append((self.status, now))
        self.status = new_status

        # Update specific timestamps
        if new_status == OrderStatus.SUBMITTED:
            self.submitted_at = now
        elif new_status == OrderStatus.ACKNOWLEDGED:
            self.acked_at = now
        elif new_status == OrderStatus.FILLED:
            self.filled_at = now
            self.terminal_at = now
        elif new_status.is_terminal:
            self.terminal_at = now

        return True

    @property
    def is_complete(self) -> bool:
        """Check if order reached a terminal state."""
        return self.status.is_terminal

    @property
    def age_seconds(self) -> float:
        """Get order age in seconds."""
        return (datetime.now() - self.created_at).total_seconds()


class OrderRegistry:
    """
    Registry of active orders for idempotency and lifecycle tracking.

    Thread-safe registry to prevent duplicate submissions and track order state.
    """

    def __init__(self, max_pending_age_s: int = 300) -> None:
        """
        Initialize registry.

        Args:
            max_pending_age_s: Maximum age for pending orders before cleanup
        """
        self._orders: dict[str, OrderTracker] = {}  # deal_reference -> tracker
        self._intent_map: dict[UUID, str] = {}  # intent_id -> deal_reference
        self._deal_id_map: dict[str, str] = {}  # deal_id -> deal_reference
        self._max_pending_age_s = max_pending_age_s

    def register(self, tracker: OrderTracker) -> bool:
        """
        Register a new order.

        Returns False if deal_reference already exists (duplicate).
        """
        if tracker.deal_reference in self._orders:
            return False  # Duplicate

        self._orders[tracker.deal_reference] = tracker
        self._intent_map[tracker.intent_id] = tracker.deal_reference
        return True

    def get_by_reference(self, deal_reference: str) -> OrderTracker | None:
        """Get order by deal reference."""
        return self._orders.get(deal_reference)

    def get_by_intent(self, intent_id: UUID) -> OrderTracker | None:
        """Get order by intent ID."""
        ref = self._intent_map.get(intent_id)
        return self._orders.get(ref) if ref else None

    def get_by_deal_id(self, deal_id: str) -> OrderTracker | None:
        """Get order by broker deal ID."""
        ref = self._deal_id_map.get(deal_id)
        return self._orders.get(ref) if ref else None

    def set_deal_id(self, deal_reference: str, deal_id: str) -> bool:
        """Associate broker deal_id with order."""
        tracker = self._orders.get(deal_reference)
        if not tracker:
            return False
        tracker.deal_id = deal_id
        self._deal_id_map[deal_id] = deal_reference
        return True

    def has_reference(self, deal_reference: str) -> bool:
        """Check if deal reference is already registered."""
        return deal_reference in self._orders

    def has_intent(self, intent_id: UUID) -> bool:
        """Check if intent ID is already registered."""
        return intent_id in self._intent_map

    def get_pending_count(self) -> int:
        """Get count of non-terminal orders."""
        return sum(1 for o in self._orders.values() if not o.is_complete)

    def cleanup_stale(self) -> int:
        """
        Remove stale completed orders.

        Returns count of orders cleaned up.
        """
        stale_refs = []
        now = datetime.now()

        for ref, tracker in self._orders.items():
            # Keep non-terminal orders
            if not tracker.is_complete:
                continue

            # Remove if terminal and old
            if tracker.terminal_at:
                age = (now - tracker.terminal_at).total_seconds()
                if age > self._max_pending_age_s:
                    stale_refs.append(ref)

        for ref in stale_refs:
            tracker = self._orders.pop(ref, None)
            if tracker:
                self._intent_map.pop(tracker.intent_id, None)
                if tracker.deal_id:
                    self._deal_id_map.pop(tracker.deal_id, None)

        return len(stale_refs)
