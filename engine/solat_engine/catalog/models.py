"""
Pydantic models for instrument catalogue.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    """Asset class categories."""

    FX = "fx"
    INDEX = "index"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    STOCK = "stock"


class DealingRulesSummary(BaseModel):
    """Summary of dealing rules for an instrument."""

    min_deal_size: Decimal | None = Field(default=None, alias="minDealSize")
    max_deal_size: Decimal | None = Field(default=None, alias="maxDealSize")
    min_size_increment: Decimal | None = Field(default=None, alias="minSizeIncrement")
    min_stop_distance: Decimal | None = Field(default=None, alias="minStopDistance")
    max_stop_distance: Decimal | None = Field(default=None, alias="maxStopDistance")

    class Config:
        populate_by_name = True


class InstrumentCatalogueItem(BaseModel):
    """
    A canonical instrument in the catalogue.

    Combines our internal symbol with IG-specific identifiers and dealing rules.
    """

    # Core identification
    symbol: str = Field(
        ...,
        description="Internal canonical symbol (e.g., EURUSD)",
        min_length=1,
        max_length=32,
    )
    epic: str | None = Field(
        default=None,
        description="IG epic identifier",
    )
    display_name: str = Field(
        ...,
        description="Human-readable display name",
    )
    asset_class: AssetClass = Field(
        ...,
        description="Asset class category",
    )

    # Trading specifications
    currency: str = Field(
        default="USD",
        description="Quote currency",
        min_length=3,
        max_length=3,
    )
    pip_size: Decimal | None = Field(
        default=None,
        description="Pip/point size",
    )
    point_value: Decimal | None = Field(
        default=None,
        description="Value per point",
    )
    lot_size: Decimal | None = Field(
        default=None,
        description="Standard lot size",
    )
    margin_factor: Decimal | None = Field(
        default=None,
        description="Margin factor percentage",
    )

    # Dealing rules (from IG)
    dealing_rules: DealingRulesSummary | None = Field(
        default=None,
        description="Dealing rules summary",
    )

    # Metadata
    search_hint: str | None = Field(
        default=None,
        description="Search hint for IG market search",
    )
    is_enriched: bool = Field(
        default=False,
        description="Whether this has been enriched from IG",
    )
    enrichment_error: str | None = Field(
        default=None,
        description="Error message if enrichment failed",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp",
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v),
        }


class CatalogueSeedItem(BaseModel):
    """
    Seed data for an instrument (minimal info for bootstrapping).
    """

    symbol: str
    display_name: str
    asset_class: AssetClass
    search_hint: str
    currency: str = "USD"
    pip_size: Decimal | None = None
    # IG epics differ between DEMO and LIVE accounts
    demo_epic: str | None = None  # e.g., CS.D.EURUSD.MINI.IP
    live_epic: str | None = None  # e.g., CS.D.EURUSD.TODAY.IP
