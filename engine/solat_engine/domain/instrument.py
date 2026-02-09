"""
Instrument domain model.

Represents a tradeable asset with its properties and IG-specific metadata.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class InstrumentType(str, Enum):
    """Type of financial instrument."""

    FOREX = "FOREX"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    CRYPTO = "CRYPTO"
    SHARE = "SHARE"


class Instrument(BaseModel):
    """
    A tradeable financial instrument.

    Stores both the canonical symbol (e.g., "EURUSD") and the
    broker-specific identifier (e.g., IG epic "CS.D.EURUSD.CFD.IP").
    """

    # Core identifiers
    symbol: str = Field(
        ...,
        description="Canonical symbol (e.g., EURUSD, AAPL)",
        min_length=1,
        max_length=32,
    )
    epic: str = Field(
        ...,
        description="IG-specific epic identifier",
        min_length=1,
    )
    name: str = Field(
        ...,
        description="Human-readable instrument name",
    )
    instrument_type: InstrumentType = Field(
        ...,
        description="Type of instrument",
    )

    # Trading specifications
    min_deal_size: Decimal = Field(
        default=Decimal("0.01"),
        description="Minimum deal size",
        ge=0,
    )
    size_increment: Decimal = Field(
        default=Decimal("0.01"),
        description="Size increment (step size)",
        gt=0,
    )
    pip_size: Decimal = Field(
        default=Decimal("0.0001"),
        description="Pip size for this instrument",
        gt=0,
    )
    margin_factor: Decimal | None = Field(
        default=None,
        description="Margin factor (if applicable)",
        ge=0,
    )

    # Market hours (UTC)
    market_open: str | None = Field(
        default=None,
        description="Market open time (HH:MM UTC)",
    )
    market_close: str | None = Field(
        default=None,
        description="Market close time (HH:MM UTC)",
    )

    # Metadata
    currency: str = Field(
        default="USD",
        description="Base currency for P&L calculation",
        min_length=3,
        max_length=3,
    )
    is_active: bool = Field(
        default=True,
        description="Whether instrument is currently tradeable",
    )
    last_updated: datetime | None = Field(
        default=None,
        description="Last time instrument data was updated",
    )

    class Config:
        frozen = True  # Immutable once created

    def __hash__(self) -> int:
        return hash((self.symbol, self.epic))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self.symbol == other.symbol and self.epic == other.epic
