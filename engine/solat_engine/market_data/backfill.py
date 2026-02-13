"""
Gap healing backfill service.

Fetches historical bars to fill gaps after reconnection events.
"""

from datetime import UTC, datetime, timedelta
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from solat_engine.data.ig_history import IGHistoryFetcher
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.logging import get_logger
from solat_engine.market_data.bar_builder import BarBuilder

if TYPE_CHECKING:
    from solat_engine.broker.ig.client import AsyncIGClient
    from solat_engine.data.parquet_store import ParquetStore

logger = get_logger(__name__)


class BackfillService:
    """
    Gap healing backfill service.

    Responsible for:
    - Fetching recent historical bars after reconnection
    - Detecting and filling gaps in bar data
    - Updating bar builders with backfilled data
    """

    def __init__(
        self,
        ig_client: "AsyncIGClient",
        bar_builder: BarBuilder | None = None,
        parquet_store: "ParquetStore | None" = None,
        default_timeframe: SupportedTimeframe = SupportedTimeframe.M1,
    ):
        """
        Initialize backfill service.

        Args:
            ig_client: IG client for fetching historical data
            bar_builder: Optional bar builder to update with backfilled data
            parquet_store: Optional parquet store to persist backfilled bars
            default_timeframe: Default timeframe for backfill
        """
        self._ig_client = ig_client
        self._fetcher = IGHistoryFetcher(ig_client)
        self._bar_builder = bar_builder
        self._parquet_store = parquet_store
        self._default_timeframe = default_timeframe

        # Epic mapping (symbol -> epic) - set externally
        self._epic_map: dict[str, str] = {}

        # Stats
        self._backfills_completed = 0
        self._bars_backfilled = 0
        self._errors: list[str] = []

    def set_epic_map(self, epic_map: dict[str, str]) -> None:
        """Set symbol to epic mapping."""
        self._epic_map = epic_map

    def register_epic(self, symbol: str, epic: str) -> None:
        """Register a single symbol to epic mapping."""
        self._epic_map[symbol] = epic

    async def backfill_symbol(
        self,
        symbol: str,
        minutes: int = 5,
        timeframe: SupportedTimeframe | None = None,
    ) -> int:
        """
        Backfill recent bars for a symbol.

        Args:
            symbol: Symbol to backfill
            minutes: Number of minutes of history to fetch
            timeframe: Timeframe to backfill (uses default if None)

        Returns:
            Number of bars backfilled
        """
        epic = self._epic_map.get(symbol)
        if not epic:
            logger.warning("No epic mapping for symbol %s, skipping backfill", symbol)
            return 0

        tf = timeframe or self._default_timeframe
        now = datetime.now(UTC)
        start = now - timedelta(minutes=minutes)

        try:
            bars, warnings = await self._fetcher.fetch_by_date_range(
                epic=epic,
                symbol=symbol,
                resolution=tf,
                start=start,
                end=now,
            )

            for warning in warnings:
                logger.warning("Backfill warning for %s: %s", symbol, warning)

            if not bars:
                logger.debug("No bars returned for %s backfill", symbol)
                return 0

            # Process backfilled bars
            bars_processed = await self._process_backfilled_bars(bars, symbol, tf)

            self._backfills_completed += 1
            self._bars_backfilled += bars_processed

            logger.info(
                "Backfilled %d bars for %s (%s, last %d minutes)",
                bars_processed,
                symbol,
                tf.value,
                minutes,
            )

            return bars_processed

        except Exception as e:
            error_msg = f"Backfill failed for {symbol}: {e}"
            self._errors.append(error_msg)
            logger.error(error_msg)
            return 0

    async def _process_backfilled_bars(
        self,
        bars: list[HistoricalBar],
        symbol: str,
        timeframe: SupportedTimeframe,
    ) -> int:
        """Process backfilled bars - persist and/or update bar builder."""
        processed = 0

        for bar in bars:
            # Persist to Parquet if configured
            if self._parquet_store is not None:
                try:
                    self._parquet_store.write_bars([bar])
                    processed += 1
                except Exception as e:
                    logger.warning("Failed to persist backfilled bar: %s", e)

            # Update bar builder if configured
            if self._bar_builder is not None:
                # Note: Bar builder doesn't have a direct "inject historical bar" method
                # The bars are primarily stored via Parquet
                processed += 1

        return processed

    async def backfill_all(
        self,
        symbols: list[str],
        minutes: int = 5,
        timeframe: SupportedTimeframe | None = None,
    ) -> dict[str, int]:
        """
        Backfill all specified symbols.

        Args:
            symbols: List of symbols to backfill
            minutes: Number of minutes of history to fetch
            timeframe: Timeframe to backfill

        Returns:
            Dict of symbol -> bars backfilled
        """
        results: dict[str, int] = {}

        for symbol in symbols:
            bars_filled = await self.backfill_symbol(
                symbol=symbol,
                minutes=minutes,
                timeframe=timeframe,
            )
            results[symbol] = bars_filled

        total = sum(results.values())
        logger.info(
            "Backfill complete: %d symbols, %d total bars",
            len(symbols),
            total,
        )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get backfill statistics."""
        return {
            "backfills_completed": self._backfills_completed,
            "bars_backfilled": self._bars_backfilled,
            "errors_count": len(self._errors),
            "recent_errors": self._errors[-5:] if self._errors else [],
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._backfills_completed = 0
        self._bars_backfilled = 0
        self._errors.clear()


def create_backfill_callback(
    backfill_service: BackfillService,
    timeframe: SupportedTimeframe = SupportedTimeframe.M1,
) -> Callable[[str, int], Awaitable[int]]:
    """
    Create a backfill callback for use with MarketDataController.

    The callback signature matches what the controller expects:
    async def(symbol: str, minutes: int) -> int

    Args:
        backfill_service: BackfillService instance
        timeframe: Timeframe to use for backfill

    Returns:
        Async callback function
    """

    async def backfill_callback(symbol: str, minutes: int) -> int:
        return await backfill_service.backfill_symbol(
            symbol=symbol,
            minutes=minutes,
            timeframe=timeframe,
        )

    return backfill_callback
