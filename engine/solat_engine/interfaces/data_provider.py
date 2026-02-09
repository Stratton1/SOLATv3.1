"""
DataProvider interface.

Defines the contract for market data access.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from solat_engine.domain import Bar, Instrument, Timeframe


class DataProvider(ABC):
    """
    Abstract base class for market data providers.

    Implementations handle fetching, storing, and serving
    historical and real-time market data.
    """

    # =========================================================================
    # Historical Data
    # =========================================================================

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """
        Get historical bars for a symbol.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe
            start: Start datetime (UTC)
            end: End datetime (UTC, default=now)
            limit: Maximum number of bars to return

        Returns:
            List of bars, oldest first.
        """
        pass

    @abstractmethod
    async def get_latest_bar(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> Bar | None:
        """
        Get the most recent complete bar.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe

        Returns:
            Latest complete bar, or None if not available.
        """
        pass

    @abstractmethod
    async def get_latest_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Bar]:
        """
        Get the N most recent complete bars.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe
            count: Number of bars to return

        Returns:
            List of bars, oldest first.
        """
        pass

    # =========================================================================
    # Real-time Data
    # =========================================================================

    @abstractmethod
    async def subscribe_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> AsyncIterator[Bar]:
        """
        Subscribe to real-time bar updates.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe

        Yields:
            Bars as they complete.
        """
        pass

    @abstractmethod
    async def unsubscribe_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> None:
        """
        Unsubscribe from bar updates.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe
        """
        pass

    # =========================================================================
    # Data Management
    # =========================================================================

    @abstractmethod
    async def has_data(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> bool:
        """
        Check if data exists for the given range.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe
            start: Start datetime
            end: End datetime

        Returns:
            True if data exists for the full range.
        """
        pass

    @abstractmethod
    async def fetch_and_store(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> int:
        """
        Fetch data from source and store locally.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe
            start: Start datetime
            end: End datetime

        Returns:
            Number of bars fetched and stored.
        """
        pass

    @abstractmethod
    async def get_available_range(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> tuple[datetime, datetime] | None:
        """
        Get the available data range for a symbol.

        Args:
            symbol: Instrument symbol
            timeframe: Bar timeframe

        Returns:
            Tuple of (start, end) datetimes, or None if no data.
        """
        pass

    # =========================================================================
    # Instrument Catalogue
    # =========================================================================

    @abstractmethod
    async def get_instruments(self) -> list[Instrument]:
        """
        Get all available instruments.

        Returns:
            List of all instruments in the catalogue.
        """
        pass

    @abstractmethod
    async def get_instrument(self, symbol: str) -> Instrument | None:
        """
        Get instrument by symbol.

        Args:
            symbol: Canonical symbol

        Returns:
            Instrument if found, None otherwise.
        """
        pass

    # =========================================================================
    # Timeframe Aggregation
    # =========================================================================

    @abstractmethod
    async def aggregate_bars(
        self,
        bars: list[Bar],
        target_timeframe: Timeframe,
    ) -> list[Bar]:
        """
        Aggregate bars to a higher timeframe.

        Args:
            bars: Source bars (must be complete)
            target_timeframe: Target timeframe (must be > source)

        Returns:
            Aggregated bars.
        """
        pass
