"""
Unified market data controller.

Orchestrates streaming and polling modes with automatic fallback,
stale detection, and gap healing on reconnect.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from solat_engine.logging import get_logger
from solat_engine.market_data.models import (
    MarketDataMode,
    MarketStreamStatus,
    Quote,
)

if TYPE_CHECKING:
    from solat_engine.broker.ig.client import AsyncIGClient
    from solat_engine.market_data.polling import PollingMarketSource
    from solat_engine.market_data.streaming import StreamingMarketSource

logger = get_logger(__name__)


class ControllerState(str, Enum):
    """Controller state."""

    STOPPED = "stopped"
    STARTING = "starting"
    STREAMING = "streaming"
    POLLING = "polling"
    FALLING_BACK = "falling_back"
    RECOVERING = "recovering"


@dataclass
class ControllerConfig:
    """Controller configuration."""

    # Stale detection
    stale_after_s: float = 10.0

    # Fallback thresholds
    max_stream_failures: int = 5
    stream_failure_window_s: float = 60.0

    # Auto-promote settings
    auto_promote_enabled: bool = True
    promote_stable_window_s: float = 120.0  # 2 minutes stable before promoting

    # Backfill settings
    backfill_on_reconnect: bool = True
    backfill_minutes: int = 5

    # Polling settings
    poll_cadence_ms: int = 1500


@dataclass
class ControllerStats:
    """Controller runtime statistics."""

    started_at: datetime | None = None
    current_mode: MarketDataMode = MarketDataMode.POLL
    state: ControllerState = ControllerState.STOPPED

    # Streaming stats
    stream_connects: int = 0
    stream_failures: int = 0
    stream_failures_in_window: int = 0
    last_stream_failure: datetime | None = None

    # Fallback stats
    fallback_count: int = 0
    last_fallback: datetime | None = None
    promote_count: int = 0
    last_promote: datetime | None = None

    # Quote stats
    quotes_received: int = 0
    last_quote_ts: datetime | None = None

    # Backfill stats
    backfills_triggered: int = 0
    bars_backfilled: int = 0


QuoteCallback = Callable[[Quote], Coroutine[Any, Any, None]]
StatusCallback = Callable[[MarketStreamStatus], Coroutine[Any, Any, None]]
BackfillCallback = Callable[[str, int], Coroutine[Any, Any, int]]


class MarketDataController:
    """
    Unified market data controller.

    Orchestrates streaming and polling modes with:
    - Automatic fallback from stream to poll on failures
    - Stale feed detection
    - Optional auto-promote from poll back to stream
    - Gap healing via backfill on reconnect
    """

    def __init__(
        self,
        ig_client: "AsyncIGClient",
        config: ControllerConfig | None = None,
        on_quote: QuoteCallback | None = None,
        on_status: StatusCallback | None = None,
        on_backfill: BackfillCallback | None = None,
    ):
        """
        Initialize controller.

        Args:
            ig_client: IG broker client
            config: Controller configuration
            on_quote: Async callback for quotes
            on_status: Async callback for status changes
            on_backfill: Async callback for backfill requests
                         Signature: async def(symbol: str, minutes: int) -> bars_filled
        """
        self._ig_client = ig_client
        self._config = config or ControllerConfig()
        self._on_quote = on_quote
        self._on_status = on_status
        self._on_backfill = on_backfill

        self._stats = ControllerStats()
        self._subscriptions: dict[str, str] = {}  # symbol -> epic

        # Mode sources
        self._streaming_source: StreamingMarketSource | None = None
        self._polling_source: PollingMarketSource | None = None
        self._active_source: Any = None

        # Tasks
        self._monitor_task: asyncio.Task[None] | None = None
        self._running = False
        self._lock = asyncio.Lock()

        # Failure tracking for fallback decisions
        self._stream_failure_times: list[datetime] = []

    @property
    def state(self) -> ControllerState:
        """Get current state."""
        return self._stats.state

    @property
    def mode(self) -> MarketDataMode:
        """Get current mode."""
        return self._stats.current_mode

    @property
    def is_running(self) -> bool:
        """Check if running."""
        return self._running

    @property
    def stats(self) -> ControllerStats:
        """Get runtime statistics."""
        return self._stats

    def get_status(self) -> MarketStreamStatus:
        """Get current status."""
        stale = False
        if self._stats.last_quote_ts:
            age = (datetime.now(UTC) - self._stats.last_quote_ts).total_seconds()
            stale = age > self._config.stale_after_s

        if self._active_source:
            source_status = self._active_source.get_status()
            return MarketStreamStatus(
                connected=source_status.connected,
                mode=self._stats.current_mode,
                last_tick_ts=self._stats.last_quote_ts,
                stale=stale,
                stale_threshold_s=int(self._config.stale_after_s),
                subscriptions=list(self._subscriptions.keys()),
                reconnect_attempts=source_status.reconnect_attempts,
                last_error=source_status.last_error,
            )

        return MarketStreamStatus(
            connected=False,
            mode=self._stats.current_mode,
            last_tick_ts=self._stats.last_quote_ts,
            stale=stale,
            stale_threshold_s=int(self._config.stale_after_s),
            subscriptions=list(self._subscriptions.keys()),
            reconnect_attempts=0,
            last_error=None,
        )

    async def start(self, preferred_mode: MarketDataMode = MarketDataMode.STREAM) -> None:
        """
        Start the controller.

        Args:
            preferred_mode: Preferred mode to start with
        """
        async with self._lock:
            if self._running:
                logger.warning("Controller already running")
                return

            self._running = True
            self._stats.started_at = datetime.now(UTC)
            self._stats.state = ControllerState.STARTING

            logger.info("Starting market data controller (preferred mode: %s)", preferred_mode)

            try:
                if preferred_mode == MarketDataMode.STREAM:
                    await self._start_streaming()
                else:
                    await self._start_polling()

                # Start monitoring task
                self._monitor_task = asyncio.create_task(self._monitor_loop())

            except Exception as e:
                logger.error("Failed to start controller: %s", e)
                self._stats.state = ControllerState.STOPPED
                self._running = False
                raise

    async def stop(self) -> None:
        """Stop the controller."""
        async with self._lock:
            if not self._running:
                return

            self._running = False
            self._stats.state = ControllerState.STOPPED

            logger.info("Stopping market data controller")

            # Cancel monitor task
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                self._monitor_task = None

            # Stop active source
            if self._streaming_source:
                await self._streaming_source.stop()
                self._streaming_source = None

            if self._polling_source:
                await self._polling_source.stop()
                self._polling_source = None

            self._active_source = None

    async def subscribe(self, symbol: str, epic: str) -> None:
        """
        Subscribe to a symbol.

        Args:
            symbol: Canonical symbol
            epic: IG epic identifier
        """
        self._subscriptions[symbol] = epic

        if self._active_source:
            await self._active_source.subscribe(symbol, epic)
            logger.info("Subscribed to %s via %s", symbol, self._stats.current_mode)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from a symbol."""
        if symbol in self._subscriptions:
            del self._subscriptions[symbol]

            if self._active_source:
                await self._active_source.unsubscribe(symbol)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all symbols."""
        self._subscriptions.clear()

        if self._active_source:
            await self._active_source.unsubscribe_all()

    async def force_mode(self, mode: MarketDataMode) -> None:
        """
        Force switch to a specific mode.

        Args:
            mode: Mode to switch to
        """
        async with self._lock:
            if mode == self._stats.current_mode:
                return

            logger.info("Forcing mode switch: %s -> %s", self._stats.current_mode, mode)

            if mode == MarketDataMode.STREAM:
                await self._switch_to_streaming()
            else:
                await self._switch_to_polling()

    # -------------------------------------------------------------------------
    # Internal: Streaming
    # -------------------------------------------------------------------------

    async def _start_streaming(self) -> None:
        """Start streaming mode."""
        from solat_engine.market_data.streaming import StreamingMarketSource

        self._streaming_source = StreamingMarketSource(
            ig_client=self._ig_client,
            on_quote=self._handle_quote,
            on_status_change=self._handle_status_change,
        )

        # Add existing subscriptions
        for symbol, epic in self._subscriptions.items():
            await self._streaming_source.subscribe(symbol, epic)

        await self._streaming_source.start()

        self._active_source = self._streaming_source
        self._stats.current_mode = MarketDataMode.STREAM
        self._stats.state = ControllerState.STREAMING
        self._stats.stream_connects += 1

        logger.info("Streaming mode started")

    async def _switch_to_streaming(self) -> None:
        """Switch from polling to streaming."""
        self._stats.state = ControllerState.RECOVERING

        # Stop polling
        if self._polling_source:
            await self._polling_source.stop()
            self._polling_source = None

        # Start streaming
        await self._start_streaming()

        self._stats.promote_count += 1
        self._stats.last_promote = datetime.now(UTC)

        logger.info("Promoted to streaming mode")

    # -------------------------------------------------------------------------
    # Internal: Polling
    # -------------------------------------------------------------------------

    async def _start_polling(self) -> None:
        """Start polling mode."""
        from solat_engine.market_data.polling import PollingMarketSource

        self._polling_source = PollingMarketSource(
            ig_client=self._ig_client,
            cadence_ms=self._config.poll_cadence_ms,
            on_quote=self._handle_quote,
            on_status_change=self._handle_status_change,
        )

        # Add existing subscriptions
        for symbol, epic in self._subscriptions.items():
            await self._polling_source.subscribe(symbol, epic)

        await self._polling_source.start()

        self._active_source = self._polling_source
        self._stats.current_mode = MarketDataMode.POLL
        self._stats.state = ControllerState.POLLING

        logger.info("Polling mode started")

    async def _switch_to_polling(self) -> None:
        """Switch from streaming to polling (fallback)."""
        self._stats.state = ControllerState.FALLING_BACK

        # Stop streaming
        if self._streaming_source:
            await self._streaming_source.stop()
            self._streaming_source = None

        # Start polling
        await self._start_polling()

        self._stats.fallback_count += 1
        self._stats.last_fallback = datetime.now(UTC)

        logger.warning("Fell back to polling mode")

        # Trigger backfill if enabled
        if self._config.backfill_on_reconnect:
            await self._trigger_backfill()

    # -------------------------------------------------------------------------
    # Internal: Callbacks
    # -------------------------------------------------------------------------

    async def _handle_quote(self, quote: Quote) -> None:
        """Handle incoming quote."""
        self._stats.quotes_received += 1
        self._stats.last_quote_ts = quote.ts_utc

        if self._on_quote:
            await self._on_quote(quote)

    async def _handle_status_change(self, status: MarketStreamStatus) -> None:
        """Handle status change from active source."""
        # Track streaming failures
        if (
            self._stats.current_mode == MarketDataMode.STREAM
            and not status.connected
            and status.last_error
        ):
            self._record_stream_failure()

        if self._on_status:
            await self._on_status(status)

    def _record_stream_failure(self) -> None:
        """Record a streaming failure for fallback decision."""
        now = datetime.now(UTC)
        self._stats.stream_failures += 1
        self._stats.last_stream_failure = now
        self._stream_failure_times.append(now)

        # Clean old failures outside window
        cutoff = now.timestamp() - self._config.stream_failure_window_s
        self._stream_failure_times = [
            t for t in self._stream_failure_times if t.timestamp() > cutoff
        ]

        self._stats.stream_failures_in_window = len(self._stream_failure_times)

    def _should_fallback(self) -> bool:
        """Check if we should fall back to polling."""
        return self._stats.stream_failures_in_window >= self._config.max_stream_failures

    def _should_promote(self) -> bool:
        """Check if we should promote back to streaming."""
        if not self._config.auto_promote_enabled:
            return False

        if self._stats.current_mode != MarketDataMode.POLL:
            return False

        # Need stable polling for promote_stable_window_s
        if not self._stats.last_fallback:
            return False

        elapsed = (datetime.now(UTC) - self._stats.last_fallback).total_seconds()
        return elapsed >= self._config.promote_stable_window_s

    # -------------------------------------------------------------------------
    # Internal: Monitor Loop
    # -------------------------------------------------------------------------

    async def _monitor_loop(self) -> None:
        """Monitor connection health and trigger fallback/promote."""
        check_interval = 5.0

        while self._running:
            try:
                await asyncio.sleep(check_interval)

                # Check for stale feed
                if self._stats.last_quote_ts:
                    age = (datetime.now(UTC) - self._stats.last_quote_ts).total_seconds()
                    if age > self._config.stale_after_s:
                        logger.warning("Feed stale: no ticks for %.1fs", age)

                # Check for fallback condition (streaming -> polling)
                if (
                    self._stats.current_mode == MarketDataMode.STREAM
                    and self._should_fallback()
                ):
                    logger.warning(
                        "Streaming unstable (%d failures in %.0fs), falling back to polling",
                        self._stats.stream_failures_in_window,
                        self._config.stream_failure_window_s,
                    )
                    await self._switch_to_polling()

                # Check for promote condition (polling -> streaming)
                elif self._should_promote():
                    logger.info("Polling stable, attempting to promote back to streaming")
                    try:
                        await self._switch_to_streaming()
                        # Clear failure history on successful promote
                        self._stream_failure_times.clear()
                        self._stats.stream_failures_in_window = 0
                    except Exception as e:
                        logger.warning("Failed to promote to streaming: %s", e)
                        self._record_stream_failure()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor loop error: %s", e)

    # -------------------------------------------------------------------------
    # Internal: Backfill
    # -------------------------------------------------------------------------

    async def _trigger_backfill(self) -> None:
        """Trigger backfill for subscribed symbols."""
        if not self._on_backfill:
            logger.debug("No backfill callback configured")
            return

        self._stats.backfills_triggered += 1
        minutes = self._config.backfill_minutes

        logger.info("Triggering backfill for %d symbols (%d minutes)", len(self._subscriptions), minutes)

        total_bars = 0
        for symbol in self._subscriptions:
            try:
                bars_filled = await self._on_backfill(symbol, minutes)
                total_bars += bars_filled
                logger.debug("Backfilled %d bars for %s", bars_filled, symbol)
            except Exception as e:
                logger.warning("Backfill failed for %s: %s", symbol, e)

        self._stats.bars_backfilled += total_bars
        logger.info("Backfill complete: %d bars total", total_bars)
