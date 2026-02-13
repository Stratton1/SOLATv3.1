"""
Order domain model.

Represents a trading order sent to the broker.
Tracks full lifecycle from creation to fill/cancel.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """Order side (direction)."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"  # Execute at current market price
    LIMIT = "LIMIT"  # Execute at specified price or better
    STOP = "STOP"  # Execute when price reaches stop level


class OrderStatus(str, Enum):
    """Order lifecycle status."""

    PENDING = "PENDING"  # Created but not yet submitted
    SUBMITTED = "SUBMITTED"  # Sent to broker
    ACCEPTED = "ACCEPTED"  # Acknowledged by broker
    WORKING = "WORKING"  # Active in market (limit/stop orders)
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Some quantity filled
    FILLED = "FILLED"  # Fully executed
    CANCELLED = "CANCELLED"  # Cancelled before fill
    REJECTED = "REJECTED"  # Rejected by broker
    EXPIRED = "EXPIRED"  # Expired without fill


class Order(BaseModel):
    """
    A trading order.

    Represents the intent to buy/sell an instrument.
    Mutable to track status changes through lifecycle.
    """

    # Identification
    id: UUID = Field(
        default_factory=uuid4,
        description="Internal order identifier",
    )
    broker_id: str | None = Field(
        default=None,
        description="Broker-assigned order identifier",
    )
    signal_id: UUID | None = Field(
        default=None,
        description="ID of signal that generated this order",
    )

    # Order specification
    symbol: str = Field(
        ...,
        description="Instrument symbol",
    )
    side: OrderSide = Field(
        ...,
        description="Order side (BUY/SELL)",
    )
    order_type: OrderType = Field(
        default=OrderType.MARKET,
        description="Order type",
    )
    quantity: Decimal = Field(
        ...,
        description="Order quantity/size",
        gt=0,
    )
    limit_price: Decimal | None = Field(
        default=None,
        description="Limit price (for LIMIT orders)",
        gt=0,
    )
    stop_price: Decimal | None = Field(
        default=None,
        description="Stop price (for STOP orders)",
        gt=0,
    )

    # Risk management
    stop_loss: Decimal | None = Field(
        default=None,
        description="Stop loss price",
        gt=0,
    )
    take_profit: Decimal | None = Field(
        default=None,
        description="Take profit price",
        gt=0,
    )
    trailing_stop_distance: Decimal | None = Field(
        default=None,
        description="Trailing stop distance (in price units)",
        gt=0,
    )
    guaranteed_stop: bool = Field(
        default=False,
        description="Whether to use guaranteed stop (IG-specific)",
    )

    # Status tracking
    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        description="Current order status",
    )
    filled_quantity: Decimal = Field(
        default=Decimal("0"),
        description="Quantity filled so far",
        ge=0,
    )
    average_fill_price: Decimal | None = Field(
        default=None,
        description="Average fill price",
        gt=0,
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="Order creation timestamp",
    )
    submitted_at: datetime | None = Field(
        default=None,
        description="Timestamp when submitted to broker",
    )
    filled_at: datetime | None = Field(
        default=None,
        description="Timestamp when fully filled",
    )
    cancelled_at: datetime | None = Field(
        default=None,
        description="Timestamp when cancelled",
    )

    # Metadata
    reason: str | None = Field(
        default=None,
        description="Reason for order (for audit trail)",
    )
    reject_reason: str | None = Field(
        default=None,
        description="Reason for rejection (if rejected)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional order metadata",
    )

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def is_open(self) -> bool:
        """Check if order is still open/active."""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.WORKING,
            OrderStatus.PARTIALLY_FILLED,
        )

    @property
    def is_closed(self) -> bool:
        """Check if order is closed/terminal."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.side == OrderSide.SELL

    def __hash__(self) -> int:
        return hash(self.id)
