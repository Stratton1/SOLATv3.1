"""
Position domain model.

Represents a current holding in an instrument.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from solat_engine.domain.order import OrderSide


class Position(BaseModel):
    """
    A position (holding) in an instrument.

    Tracks quantity, entry price, P&L, and risk levels.
    """

    # Identification
    id: UUID = Field(
        default_factory=uuid4,
        description="Internal position identifier",
    )
    broker_id: str | None = Field(
        default=None,
        description="Broker-assigned position/deal identifier",
    )

    # Position details
    symbol: str = Field(
        ...,
        description="Instrument symbol",
    )
    side: OrderSide = Field(
        ...,
        description="Position side (BUY = long, SELL = short)",
    )
    quantity: Decimal = Field(
        ...,
        description="Position size",
        gt=0,
    )
    entry_price: Decimal = Field(
        ...,
        description="Average entry price",
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
        description="Trailing stop distance",
        gt=0,
    )

    # P&L tracking
    current_price: Decimal | None = Field(
        default=None,
        description="Current market price",
        gt=0,
    )
    unrealized_pnl: Decimal = Field(
        default=Decimal("0"),
        description="Unrealized P&L in account currency",
    )
    realized_pnl: Decimal = Field(
        default=Decimal("0"),
        description="Realized P&L from partial closes",
    )

    # Timestamps
    opened_at: datetime = Field(
        ...,
        description="Position open timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp",
    )

    # Metadata
    strategy_id: str | None = Field(
        default=None,
        description="Strategy that opened this position",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional position metadata",
    )

    @property
    def is_long(self) -> bool:
        """Check if this is a long position."""
        return self.side == OrderSide.BUY

    @property
    def is_short(self) -> bool:
        """Check if this is a short position."""
        return self.side == OrderSide.SELL

    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value at entry."""
        return self.quantity * self.entry_price

    @property
    def current_value(self) -> Decimal | None:
        """Calculate current notional value."""
        if self.current_price is None:
            return None
        return self.quantity * self.current_price

    @property
    def total_pnl(self) -> Decimal:
        """Calculate total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl

    def calculate_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """
        Calculate unrealized P&L at a given price.

        Args:
            current_price: Current market price

        Returns:
            Unrealized P&L in price units (multiply by point value for currency)
        """
        price_diff = current_price - self.entry_price
        if self.is_short:
            price_diff = -price_diff
        return price_diff * self.quantity

    def __hash__(self) -> int:
        return hash(self.id)
