"""
Fill domain model.

Represents an executed portion of an order.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FillType(str, Enum):
    """Type of fill."""

    FULL = "FULL"  # Complete fill of remaining quantity
    PARTIAL = "PARTIAL"  # Partial fill


class Fill(BaseModel):
    """
    An order fill/execution.

    Represents a (partial) execution of an order at a specific price.
    Immutable once created - fills are historical facts.
    """

    # Identification
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique fill identifier",
    )
    broker_id: str | None = Field(
        default=None,
        description="Broker-assigned fill/trade identifier",
    )
    order_id: UUID = Field(
        ...,
        description="ID of the order this fill belongs to",
    )

    # Fill details
    symbol: str = Field(
        ...,
        description="Instrument symbol",
    )
    quantity: Decimal = Field(
        ...,
        description="Filled quantity",
        gt=0,
    )
    price: Decimal = Field(
        ...,
        description="Execution price",
        gt=0,
    )
    fill_type: FillType = Field(
        ...,
        description="Type of fill (FULL/PARTIAL)",
    )

    # Costs
    commission: Decimal = Field(
        default=Decimal("0"),
        description="Commission charged",
        ge=0,
    )
    spread_cost: Decimal = Field(
        default=Decimal("0"),
        description="Estimated spread cost",
        ge=0,
    )
    slippage: Decimal = Field(
        default=Decimal("0"),
        description="Slippage from requested price",
    )

    # Timestamps
    timestamp: datetime = Field(
        ...,
        description="Fill execution timestamp (UTC)",
    )

    # Metadata
    is_simulated: bool = Field(
        default=False,
        description="Whether this fill is from backtesting",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional fill metadata",
    )

    class Config:
        frozen = True  # Immutable once created

    @property
    def total_cost(self) -> Decimal:
        """Calculate total transaction cost."""
        return self.commission + self.spread_cost

    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value of the fill."""
        return self.quantity * self.price

    def __hash__(self) -> int:
        return hash(self.id)
