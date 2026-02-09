"""
Pydantic models for IG API responses.

All models are designed to be safe for logging and API responses -
sensitive fields are excluded or redacted.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IGAccountType(str, Enum):
    """IG account types."""

    CFD = "CFD"
    PHYSICAL = "PHYSICAL"
    SPREADBET = "SPREADBET"


class IGAccountStatus(str, Enum):
    """IG account status."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    SUSPENDED_FROM_DEALING = "SUSPENDED_FROM_DEALING"


class IGAccount(BaseModel):
    """
    IG trading account (redacted for API responses).

    Does NOT include sensitive balance/margin information.
    """

    account_id: str = Field(..., alias="accountId")
    account_name: str = Field(..., alias="accountName")
    account_type: IGAccountType = Field(..., alias="accountType")
    status: IGAccountStatus = Field(default=IGAccountStatus.ENABLED)
    currency: str | None = Field(default=None)  # Optional - not always returned by IG
    preferred: bool = False

    class Config:
        populate_by_name = True


class IGLoginResponse(BaseModel):
    """
    IG login response (redacted).

    Tokens (CST, X-SECURITY-TOKEN) are deliberately excluded -
    they should never be serialized or returned via API.
    """

    client_id: str | None = Field(default=None, alias="clientId")
    account_id: str | None = Field(default=None, alias="accountId")
    timezone_offset: int | None = Field(default=None, alias="timezoneOffset")
    lightstreamer_endpoint: str | None = Field(default=None, alias="lightstreamerEndpoint")
    accounts: list[IGAccount] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class IGInstrumentType(str, Enum):
    """IG instrument types."""

    CURRENCIES = "CURRENCIES"
    INDICES = "INDICES"
    COMMODITIES = "COMMODITIES"
    SHARES = "SHARES"
    CRYPTOCURRENCIES = "CRYPTOCURRENCIES"
    RATES = "RATES"
    OPTIONS = "OPTIONS"
    SECTORS = "SECTORS"
    BINARY = "BINARY"


class IGMarketStatus(str, Enum):
    """IG market trading status."""

    TRADEABLE = "TRADEABLE"
    CLOSED = "CLOSED"
    EDITS_ONLY = "EDITS_ONLY"
    OFFLINE = "OFFLINE"
    ON_AUCTION = "ON_AUCTION"
    ON_AUCTION_NO_EDITS = "ON_AUCTION_NO_EDITS"
    SUSPENDED = "SUSPENDED"


class IGMarketSearchItem(BaseModel):
    """
    Market search result item (minimal fields).
    """

    epic: str
    instrument_name: str = Field(..., alias="instrumentName")
    instrument_type: str | None = Field(default=None, alias="instrumentType")
    expiry: str | None = Field(default=None)
    high: Decimal | None = Field(default=None)
    low: Decimal | None = Field(default=None)
    percentage_change: Decimal | None = Field(default=None, alias="percentageChange")
    net_change: Decimal | None = Field(default=None, alias="netChange")
    bid: Decimal | None = Field(default=None)
    offer: Decimal | None = Field(default=None)
    update_time: str | None = Field(default=None, alias="updateTime")
    update_time_utc: str | None = Field(default=None, alias="updateTimeUTC")
    market_status: str | None = Field(default=None, alias="marketStatus")
    scaling_factor: int | None = Field(default=None, alias="scalingFactor")

    class Config:
        populate_by_name = True


class IGMarketSearchResponse(BaseModel):
    """IG market search response."""

    markets: list[IGMarketSearchItem] = Field(default_factory=list)


class IGDealingRules(BaseModel):
    """IG dealing rules for an instrument."""

    min_deal_size: Decimal | None = Field(default=None, alias="minDealSize")
    max_deal_size: Decimal | None = Field(default=None, alias="maxDealSize")
    min_size_increment: Decimal | None = Field(default=None, alias="minSizeIncrement")
    min_controlled_risk_stop_distance: Decimal | None = Field(
        default=None, alias="minControlledRiskStopDistance"
    )
    min_normal_stop_or_limit_distance: Decimal | None = Field(
        default=None, alias="minNormalStopOrLimitDistance"
    )
    max_stop_or_limit_distance: Decimal | None = Field(
        default=None, alias="maxStopOrLimitDistance"
    )
    market_order_preference: str | None = Field(default=None, alias="marketOrderPreference")

    class Config:
        populate_by_name = True


class IGMarketDetails(BaseModel):
    """
    IG market details (minimal fields for catalogue enrichment).
    """

    epic: str
    instrument_name: str = Field(default="", alias="instrumentName")
    instrument_type: str | None = Field(default=None, alias="instrumentType")
    expiry: str | None = Field(default=None)
    lot_size: Decimal | None = Field(default=None, alias="lotSize")
    currency: str | None = Field(default=None)
    margin_factor: Decimal | None = Field(default=None, alias="marginFactor")
    margin_factor_unit: str | None = Field(default=None, alias="marginFactorUnit")
    one_pip_means: str | None = Field(default=None, alias="onePipMeans")
    pip_value: str | None = Field(default=None, alias="pipValue")
    contract_size: str | None = Field(default=None, alias="contractSize")
    controlled_risk_allowed: bool = Field(default=False, alias="controlledRiskAllowed")
    streaming_prices_available: bool = Field(default=False, alias="streamingPricesAvailable")
    market_status: str | None = Field(default=None, alias="marketStatus")
    dealing_rules: IGDealingRules | None = Field(default=None, alias="dealingRules")
    snapshot: dict[str, Any] | None = Field(default=None)

    class Config:
        populate_by_name = True


class IGTestLoginResult(BaseModel):
    """Result of a test login attempt (safe for API response)."""

    ok: bool
    mode: str  # "DEMO" or "LIVE"
    accounts_count: int = 0
    current_account_id: str | None = None
    lightstreamer_endpoint: str | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    message: str = ""

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
