"""
Bar (OHLCV) domain model.

Represents a single price bar with open, high, low, close, and volume.
Supports multiple timeframes and maintains strict immutability for backtesting.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class Timeframe(str, Enum):
    """Supported timeframes for price data."""

    M1 = "1m"  # 1 minute
    M5 = "5m"  # 5 minutes
    M15 = "15m"  # 15 minutes
    M30 = "30m"  # 30 minutes
    H1 = "1h"  # 1 hour
    H4 = "4h"  # 4 hours
    D1 = "1d"  # 1 day
    W1 = "1w"  # 1 week

    @property
    def minutes(self) -> int:
        """Return timeframe in minutes."""
        mapping = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080,
        }
        return mapping[self.value]

    @property
    def ig_resolution(self) -> str:
        """Return IG API resolution string."""
        mapping = {
            "1m": "MINUTE",
            "5m": "MINUTE_5",
            "15m": "MINUTE_15",
            "30m": "MINUTE_30",
            "1h": "HOUR",
            "4h": "HOUR_4",
            "1d": "DAY",
            "1w": "WEEK",
        }
        return mapping[self.value]


class Bar(BaseModel):
    """
    A single OHLCV bar.

    Immutable to ensure deterministic backtesting.
    Uses Decimal for precise price representation.
    """

    # Identification
    symbol: str = Field(
        ...,
        description="Instrument symbol",
    )
    timeframe: Timeframe = Field(
        ...,
        description="Bar timeframe",
    )
    timestamp: datetime = Field(
        ...,
        description="Bar open timestamp (UTC)",
    )

    # OHLCV data
    open: Decimal = Field(
        ...,
        description="Opening price",
        gt=0,
    )
    high: Decimal = Field(
        ...,
        description="Highest price",
        gt=0,
    )
    low: Decimal = Field(
        ...,
        description="Lowest price",
        gt=0,
    )
    close: Decimal = Field(
        ...,
        description="Closing price",
        gt=0,
    )
    volume: Decimal | None = Field(
        default=None,
        description="Trading volume (if available)",
        ge=0,
    )

    # Metadata
    is_complete: bool = Field(
        default=True,
        description="Whether bar is complete (not live/partial)",
    )

    class Config:
        frozen = True  # Immutable once created

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Validate high >= open and close."""
        data = info.data
        if "open" in data and v < data["open"]:
            raise ValueError("high must be >= open")
        if "close" in data and v < data["close"]:
            raise ValueError("high must be >= close")
        return v

    @field_validator("low")
    @classmethod
    def low_lte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Validate low <= open and close."""
        data = info.data
        if "open" in data and v > data["open"]:
            raise ValueError("low must be <= open")
        if "close" in data and v > data["close"]:
            raise ValueError("low must be <= close")
        return v

    @property
    def mid(self) -> Decimal:
        """Calculate mid price (HL average)."""
        return (self.high + self.low) / 2

    @property
    def typical(self) -> Decimal:
        """Calculate typical price (HLC average)."""
        return (self.high + self.low + self.close) / 3

    @property
    def range(self) -> Decimal:
        """Calculate bar range (high - low)."""
        return self.high - self.low

    @property
    def body(self) -> Decimal:
        """Calculate bar body (abs(close - open))."""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """Check if bar is bullish (close > open)."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if bar is bearish (close < open)."""
        return self.close < self.open

    def __hash__(self) -> int:
        return hash((self.symbol, self.timeframe, self.timestamp))
