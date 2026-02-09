"""
Background job runner for data sync operations.

Provides async job execution with progress events.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from solat_engine.broker.ig.client import AsyncIGClient, IGAPIError, IGAuthError
from solat_engine.catalog.store import CatalogueStore
from solat_engine.config import get_settings
from solat_engine.data.aggregate import aggregate_from_1m
from solat_engine.data.ig_history import IGHistoryFetcher
from solat_engine.data.models import (
    DataSyncRequest,
    DataSyncResult,
    SupportedTimeframe,
    SymbolSyncResult,
)
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.data.quality import check_data_quality
from solat_engine.logging import get_logger
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus

logger = get_logger(__name__)


class SyncJob:
    """A single data sync job."""

    def __init__(
        self,
        run_id: str,
        request: DataSyncRequest,
        ig_client: AsyncIGClient | None,
        catalogue_store: CatalogueStore,
        parquet_store: ParquetStore,
    ) -> None:
        """Initialize sync job."""
        self.run_id = run_id
        self.request = request
        self._ig_client = ig_client
        self._catalogue = catalogue_store
        self._store = parquet_store
        self._event_bus = get_event_bus()
        self._settings = get_settings()

    async def _emit_progress(
        self,
        symbol: str,
        timeframe: str,
        stage: str,
        done: int,
        total: int,
        message: str,
    ) -> None:
        """Emit a sync progress event."""
        await self._event_bus.publish(
            Event(
                type=EventType.SYNC_PROGRESS,
                data={
                    "run_id": self.run_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "stage": stage,
                    "done": done,
                    "total": total,
                    "message": message,
                },
                run_id=self.run_id,
            )
        )

    async def run(self) -> DataSyncResult:
        """
        Execute the sync job.

        Returns:
            DataSyncResult with per-symbol outcomes
        """
        result = DataSyncResult(
            run_id=self.run_id,
            request=self.request,
        )

        # Emit start event
        await self._event_bus.publish(
            Event(
                type=EventType.SYNC_STARTED,
                data={
                    "run_id": self.run_id,
                    "symbols": self.request.symbols,
                    "timeframes": [tf.value for tf in self.request.timeframes],
                },
                run_id=self.run_id,
            )
        )

        total_symbols = len(self.request.symbols)

        for i, symbol in enumerate(self.request.symbols):
            await self._emit_progress(
                symbol=symbol,
                timeframe="",
                stage="starting",
                done=i,
                total=total_symbols,
                message=f"Processing {symbol}",
            )

            symbol_result = await self._sync_symbol(symbol, i, total_symbols)
            result.add_symbol_result(symbol_result)

        result.completed_at = datetime.now(UTC)

        # Emit completion event
        event_type = EventType.SYNC_COMPLETED if result.ok else EventType.SYNC_FAILED
        await self._event_bus.publish(
            Event(
                type=event_type,
                data={
                    "run_id": self.run_id,
                    "ok": result.ok,
                    "total_bars_fetched": result.total_bars_fetched,
                    "total_bars_stored": result.total_bars_stored,
                    "errors": result.errors,
                },
                run_id=self.run_id,
            )
        )

        return result

    async def _sync_symbol(
        self,
        symbol: str,
        index: int,
        total: int,
    ) -> SymbolSyncResult:
        """Sync a single symbol."""
        result = SymbolSyncResult(symbol=symbol)

        # Look up epic from catalogue
        catalogue_item = self._catalogue.get(symbol)
        if not catalogue_item:
            result.error = f"Symbol '{symbol}' not found in catalogue"
            return result

        epic = catalogue_item.epic
        if not epic:
            if self.request.enrich_missing_epics:
                result.warnings.append(f"Symbol '{symbol}' has no epic - enrichment not implemented")
            result.error = f"Symbol '{symbol}' has no IG epic"
            return result

        result.epic = epic

        # Check if IG client is available
        if self._ig_client is None:
            result.error = "IG client not available (credentials not configured)"
            return result

        # Fetch 1m base data
        await self._emit_progress(
            symbol=symbol,
            timeframe="1m",
            stage="fetching",
            done=index,
            total=total,
            message=f"Fetching 1m data for {symbol}",
        )

        try:
            fetcher = IGHistoryFetcher(self._ig_client)
            m1_bars, fetch_warnings = await fetcher.fetch_by_date_range(
                epic=epic,
                symbol=symbol,
                resolution=SupportedTimeframe.M1,
                start=self.request.start,
                end=self.request.end,
            )
            result.warnings.extend(fetch_warnings)
            result.bars_fetched = len(m1_bars)

        except IGAuthError as e:
            result.error = f"Authentication failed: {e}"
            return result
        except IGAPIError as e:
            result.error = f"API error: {e}"
            return result
        except Exception as e:
            result.error = f"Fetch error: {e}"
            logger.exception("Sync error for %s", symbol)
            return result

        if not m1_bars:
            result.warnings.append("No data returned from IG")
            result.success = True  # Not an error, just no data
            return result

        # Store 1m bars
        await self._emit_progress(
            symbol=symbol,
            timeframe="1m",
            stage="storing",
            done=index,
            total=total,
            message=f"Storing {len(m1_bars)} 1m bars for {symbol}",
        )

        written, deduped = self._store.write_bars(m1_bars, self.run_id)
        result.bars_stored += written
        result.bars_deduplicated += deduped

        # Quality check
        quality_report = check_data_quality(
            bars=m1_bars,
            symbol=symbol,
            timeframe=SupportedTimeframe.M1,
            gap_tolerance_multiplier=self._settings.quality_gap_tolerance_multiplier,
        )
        result.quality_report = quality_report

        if quality_report.has_errors:
            result.warnings.append(f"Data quality issues found: {len(quality_report.issues)} issues")

        # Aggregate to derived timeframes
        derived_tfs = [tf for tf in self.request.timeframes if tf != SupportedTimeframe.M1]

        if derived_tfs:
            await self._emit_progress(
                symbol=symbol,
                timeframe="derived",
                stage="aggregating",
                done=index,
                total=total,
                message=f"Aggregating to {len(derived_tfs)} timeframes for {symbol}",
            )

            aggregated = aggregate_from_1m(m1_bars, list(derived_tfs))

            for tf, tf_bars in aggregated.items():
                if tf_bars:
                    tf_written, tf_deduped = self._store.write_bars(tf_bars, self.run_id)
                    result.bars_stored += tf_written
                    result.bars_deduplicated += tf_deduped
                    logger.debug(
                        "Stored %d %s bars for %s",
                        tf_written,
                        tf.value,
                        symbol,
                    )

        result.success = True
        return result


class JobRunner:
    """
    Manages background sync jobs.

    Jobs run asynchronously and emit progress events.
    """

    def __init__(self) -> None:
        """Initialize job runner."""
        self._active_jobs: dict[str, asyncio.Task[DataSyncResult]] = {}
        self._results: dict[str, DataSyncResult] = {}
        self._lock = asyncio.Lock()

    async def start_sync_job(
        self,
        request: DataSyncRequest,
        ig_client: AsyncIGClient | None,
        catalogue_store: CatalogueStore,
        parquet_store: ParquetStore,
    ) -> str:
        """
        Start a new sync job.

        Args:
            request: Sync request
            ig_client: IG client (may be None if not configured)
            catalogue_store: Catalogue store
            parquet_store: Parquet store

        Returns:
            Job run_id
        """
        run_id = str(uuid4())

        job = SyncJob(
            run_id=run_id,
            request=request,
            ig_client=ig_client,
            catalogue_store=catalogue_store,
            parquet_store=parquet_store,
        )

        # Create task
        task = asyncio.create_task(self._run_job(job))

        async with self._lock:
            self._active_jobs[run_id] = task

        logger.info("Started sync job %s", run_id)
        return run_id

    async def _run_job(self, job: SyncJob) -> DataSyncResult:
        """Run a job and store result."""
        try:
            result = await job.run()
        except Exception as e:
            logger.exception("Job %s failed", job.run_id)
            result = DataSyncResult(
                run_id=job.run_id,
                request=job.request,
                ok=False,
                errors=[str(e)],
            )
            result.completed_at = datetime.now(UTC)

        async with self._lock:
            self._results[job.run_id] = result
            self._active_jobs.pop(job.run_id, None)

        return result

    async def get_job_result(self, run_id: str) -> DataSyncResult | None:
        """Get result for a completed job."""
        async with self._lock:
            return self._results.get(run_id)

    async def is_job_active(self, run_id: str) -> bool:
        """Check if a job is still running."""
        async with self._lock:
            return run_id in self._active_jobs

    async def cancel_job(self, run_id: str) -> bool:
        """Cancel an active job."""
        async with self._lock:
            task = self._active_jobs.get(run_id)
            if task:
                task.cancel()
                return True
            return False

    async def list_active_jobs(self) -> list[str]:
        """Get list of active job run_ids."""
        async with self._lock:
            return list(self._active_jobs.keys())


# Global job runner instance
_job_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    """Get the global job runner instance."""
    global _job_runner
    if _job_runner is None:
        _job_runner = JobRunner()
    return _job_runner
