"""
Backtest API routes.

Endpoints for running and querying backtests.
"""

import asyncio
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import (
    BacktestRequest,
    BacktestResult,
    MetricsSummary,
    SweepRequest,
    SweepResult,
)
from solat_engine.backtest.sweep import GrandSweep
from solat_engine.config import Settings, get_settings_dep
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus
from solat_engine.strategies.elite8 import get_available_bots

router = APIRouter(prefix="/backtest", tags=["Backtest"])
logger = get_logger(__name__)

# Job state storage
_active_jobs: dict[str, asyncio.Task[BacktestResult]] = {}
_job_results: dict[str, BacktestResult] = {}
_sweep_jobs: dict[str, asyncio.Task[SweepResult]] = {}
_sweep_results: dict[str, SweepResult] = {}

# Lazy-initialized store
_parquet_store: ParquetStore | None = None


def get_parquet_store(settings: Settings = Depends(get_settings_dep)) -> ParquetStore:
    """Get or create Parquet store singleton."""
    global _parquet_store
    if _parquet_store is None or _parquet_store._data_dir != settings.data_dir:
        _parquet_store = ParquetStore(settings.data_dir)
    return _parquet_store


async def _emit_backtest_event(event_type: EventType, data: dict[str, Any]) -> None:
    """Emit backtest event to EventBus."""
    bus = get_event_bus()
    event = Event(type=event_type, data=data)
    await bus.publish(event)


async def _run_backtest_job(
    run_id: str,
    request: BacktestRequest,
    settings: Settings,
) -> BacktestResult:
    """Run backtest in background."""
    store = ParquetStore(settings.data_dir)
    artefacts_dir = settings.data_dir

    async def progress_callback(data: dict[str, Any]) -> None:
        await _emit_backtest_event(EventType.BACKTEST_PROGRESS, {
            "run_id": run_id,
            **data,
        })

    # Emit started event
    await _emit_backtest_event(EventType.BACKTEST_STARTED, {
        "run_id": run_id,
        "symbols": request.symbols,
        "bots": request.bots,
        "timeframe": request.timeframe,
    })

    # Run engine (sync, but wrapped in executor for non-blocking)
    def sync_progress(data: dict[str, Any]) -> None:
        asyncio.create_task(progress_callback(data))

    engine = BacktestEngineV1(
        parquet_store=store,
        artefacts_dir=artefacts_dir,
        progress_callback=sync_progress,
    )

    # Run in executor to not block event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, engine.run, request)

    # Store result
    _job_results[run_id] = result

    # Emit completed event
    await _emit_backtest_event(EventType.BACKTEST_COMPLETED, {
        "run_id": run_id,
        "ok": result.ok,
        "trades_count": result.combined_metrics.total_trades if result.combined_metrics else 0,
        "sharpe": result.combined_metrics.sharpe_ratio if result.combined_metrics else 0.0,
    })

    return result


async def _run_sweep_job(
    sweep_id: str,
    request: SweepRequest,
    settings: Settings,
) -> SweepResult:
    """Run sweep in background."""
    store = ParquetStore(settings.data_dir)
    artefacts_dir = settings.data_dir

    async def progress_callback(data: dict[str, Any]) -> None:
        await _emit_backtest_event(EventType.BACKTEST_PROGRESS, {
            "sweep_id": sweep_id,
            **data,
        })

    def sync_progress(data: dict[str, Any]) -> None:
        asyncio.create_task(progress_callback(data))

    sweep = GrandSweep(
        parquet_store=store,
        artefacts_dir=artefacts_dir,
        progress_callback=sync_progress,
    )

    # Run in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sweep.run, request)

    # Store result
    _sweep_results[sweep_id] = result

    return result


# =============================================================================
# Response Models
# =============================================================================


class RunResponse(BaseModel):
    """Response from starting a backtest."""

    ok: bool = True
    run_id: str
    message: str = ""


class StatusResponse(BaseModel):
    """Backtest status response."""

    run_id: str
    status: str = Field(description="queued|running|done|failed")
    progress: float = Field(default=0.0, description="Progress 0-100")
    message: str = ""


class ResultsResponse(BaseModel):
    """Backtest results response."""

    run_id: str
    ok: bool
    metrics: MetricsSummary | None = None
    per_bot_summary: list[dict[str, Any]] = Field(default_factory=list)
    artefact_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class TradesResponse(BaseModel):
    """Trades list response."""

    run_id: str
    trades: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class EquityResponse(BaseModel):
    """Equity curve response."""

    run_id: str
    points: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class BotsResponse(BaseModel):
    """Available bots response."""

    bots: list[dict[str, str]]


class SweepRunResponse(BaseModel):
    """Response from starting a sweep."""

    ok: bool = True
    sweep_id: str
    total_combos: int
    message: str = ""


class SweepStatusResponse(BaseModel):
    """Sweep status response."""

    sweep_id: str
    status: str
    completed_combos: int = 0
    total_combos: int = 0
    message: str = ""


class SweepResultsResponse(BaseModel):
    """Sweep results response."""

    sweep_id: str
    ok: bool
    completed_combos: int
    failed_combos: int
    top_performers: list[dict[str, Any]] = Field(default_factory=list)
    artefact_path: str | None = None


class RunSummary(BaseModel):
    """Summary of a single backtest run."""

    run_id: str
    status: str = Field(description="queued|running|done|failed")
    started_at: str | None = None
    symbols: list[str] = Field(default_factory=list)
    bots: list[str] = Field(default_factory=list)
    timeframe: str = ""
    trades_count: int = 0
    sharpe: float | None = None
    total_return: float | None = None


class RunsListResponse(BaseModel):
    """List of backtest runs response."""

    runs: list[RunSummary]
    total: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/bots", response_model=BotsResponse)
async def list_bots() -> BotsResponse:
    """List available strategy bots."""
    from solat_engine.strategies.elite8 import Elite8StrategyFactory

    bot_info = Elite8StrategyFactory.get_bot_info()
    return BotsResponse(bots=bot_info)


@router.get("/runs", response_model=RunsListResponse)
async def list_runs() -> RunsListResponse:
    """
    List all backtest runs (active and completed).

    Returns summary of each run including status, metrics, and configuration.
    """
    runs: list[RunSummary] = []

    # Add completed runs
    for run_id, result in _job_results.items():
        metrics = result.combined_metrics
        summary = RunSummary(
            run_id=run_id,
            status="done" if result.ok else "failed",
            started_at=result.started_at if hasattr(result, "started_at") else None,
            symbols=result.symbols if hasattr(result, "symbols") else [],
            bots=result.bots if hasattr(result, "bots") else [],
            timeframe=result.timeframe if hasattr(result, "timeframe") else "",
            trades_count=metrics.total_trades if metrics else 0,
            sharpe=metrics.sharpe_ratio if metrics else None,
            total_return=metrics.total_return if metrics else None,
        )
        runs.append(summary)

    # Add active/running jobs
    for run_id, task in _active_jobs.items():
        if run_id not in _job_results:  # Not already in completed
            status = "running" if not task.done() else "done"
            summary = RunSummary(
                run_id=run_id,
                status=status,
            )
            runs.append(summary)

    # Sort by run_id (most recent first, assuming UUIDs are time-ordered)
    runs.sort(key=lambda r: r.run_id, reverse=True)

    return RunsListResponse(runs=runs, total=len(runs))


@router.post("/run", response_model=RunResponse)
async def run_backtest(
    request: BacktestRequest,
    settings: Settings = Depends(get_settings_dep),
) -> RunResponse:
    """
    Start a backtest job.

    Returns immediately with run_id. Poll /status or /results for completion.
    """
    # Validate bots
    available_bots = get_available_bots()
    invalid_bots = [b for b in request.bots if b not in available_bots]
    if invalid_bots:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bots: {invalid_bots}. Available: {available_bots}",
        )

    # Generate run_id
    from uuid import uuid4

    run_id = str(uuid4())[:8]

    # Start background task
    task = asyncio.create_task(_run_backtest_job(run_id, request, settings))
    _active_jobs[run_id] = task

    logger.info("Started backtest job run_id=%s", run_id)

    return RunResponse(
        ok=True,
        run_id=run_id,
        message=f"Backtest started for {len(request.symbols)} symbols, {len(request.bots)} bots",
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(run_id: str = Query(..., description="Backtest run ID")) -> StatusResponse:
    """Get backtest job status."""
    # Check if completed
    if run_id in _job_results:
        result = _job_results[run_id]
        status = "done" if result.ok else "failed"
        return StatusResponse(
            run_id=run_id,
            status=status,
            progress=100.0,
            message="Backtest completed",
        )

    # Check if running
    if run_id in _active_jobs:
        task = _active_jobs[run_id]
        if task.done():
            # Task finished but result not stored yet
            try:
                result = task.result()
                _job_results[run_id] = result
                del _active_jobs[run_id]
                status = "done" if result.ok else "failed"
                return StatusResponse(
                    run_id=run_id,
                    status=status,
                    progress=100.0,
                    message="Backtest completed",
                )
            except Exception as e:
                return StatusResponse(
                    run_id=run_id,
                    status="failed",
                    progress=0.0,
                    message=str(e),
                )

        return StatusResponse(
            run_id=run_id,
            status="running",
            progress=50.0,  # Approximate
            message="Backtest in progress",
        )

    raise HTTPException(status_code=404, detail=f"Backtest '{run_id}' not found")


@router.get("/results", response_model=ResultsResponse)
async def get_results(run_id: str = Query(..., description="Backtest run ID")) -> ResultsResponse:
    """Get backtest results."""
    # Check active jobs first
    if run_id in _active_jobs:
        task = _active_jobs[run_id]
        if task.done():
            try:
                result = task.result()
                _job_results[run_id] = result
                del _active_jobs[run_id]
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    if run_id not in _job_results:
        # Check if still running
        if run_id in _active_jobs:
            raise HTTPException(
                status_code=202,
                detail="Backtest still running",
            )
        raise HTTPException(status_code=404, detail=f"Backtest '{run_id}' not found")

    result = _job_results[run_id]

    per_bot_summary = [
        {
            "bot": r.bot,
            "symbols_traded": r.symbols_traded,
            "trades_count": r.trades_count,
            "sharpe": r.metrics.sharpe_ratio,
            "max_drawdown": r.metrics.max_drawdown_pct,
            "win_rate": r.metrics.win_rate,
            "pnl": r.metrics.total_return,
        }
        for r in result.per_bot_results
    ]

    return ResultsResponse(
        run_id=run_id,
        ok=result.ok,
        metrics=result.combined_metrics,
        per_bot_summary=per_bot_summary,
        artefact_paths=result.artefact_paths,
        warnings=result.warnings[:50],
        errors=result.errors,
    )


@router.get("/trades", response_model=TradesResponse)
async def get_trades(
    run_id: str = Query(..., description="Backtest run ID"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings_dep),
) -> TradesResponse:
    """Get trades from a backtest."""
    if run_id not in _job_results:
        raise HTTPException(status_code=404, detail=f"Backtest '{run_id}' not found")

    result = _job_results[run_id]
    artefact_paths = result.artefact_paths

    if "trades" not in artefact_paths:
        return TradesResponse(
            run_id=run_id,
            trades=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    trades_path = settings.data_dir / artefact_paths["trades"]

    if not trades_path.exists():
        return TradesResponse(
            run_id=run_id,
            trades=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    trades_df = pd.read_parquet(trades_path)
    total = len(trades_df)

    # Apply pagination
    trades_df = trades_df.iloc[offset : offset + limit]

    # Convert to dicts
    trades = trades_df.to_dict(orient="records")

    # Convert timestamps to ISO strings
    for t in trades:
        for key in ["entry_time", "exit_time"]:
            if key in t and t[key] is not None:
                t[key] = t[key].isoformat() if hasattr(t[key], "isoformat") else str(t[key])

    return TradesResponse(
        run_id=run_id,
        trades=trades,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/equity", response_model=EquityResponse)
async def get_equity(
    run_id: str = Query(..., description="Backtest run ID"),
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings_dep),
) -> EquityResponse:
    """Get equity curve from a backtest."""
    if run_id not in _job_results:
        raise HTTPException(status_code=404, detail=f"Backtest '{run_id}' not found")

    result = _job_results[run_id]
    artefact_paths = result.artefact_paths

    if "equity_curve" not in artefact_paths:
        return EquityResponse(
            run_id=run_id,
            points=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    equity_path = settings.data_dir / artefact_paths["equity_curve"]

    if not equity_path.exists():
        return EquityResponse(
            run_id=run_id,
            points=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    equity_df = pd.read_parquet(equity_path)
    total = len(equity_df)

    # Apply pagination
    equity_df = equity_df.iloc[offset : offset + limit]

    # Convert to dicts
    points = equity_df.to_dict(orient="records")

    # Convert timestamps
    for p in points:
        if "timestamp" in p and p["timestamp"] is not None:
            p["timestamp"] = (
                p["timestamp"].isoformat() if hasattr(p["timestamp"], "isoformat") else str(p["timestamp"])
            )

    return EquityResponse(
        run_id=run_id,
        points=points,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Sweep Endpoints
# =============================================================================


@router.post("/sweep", response_model=SweepRunResponse)
async def run_sweep(
    request: SweepRequest,
    settings: Settings = Depends(get_settings_dep),
) -> SweepRunResponse:
    """
    Start a Grand Sweep batch backtest.

    Runs all combinations of bots × symbols × timeframes.
    """
    # Validate bots
    available_bots = get_available_bots()
    invalid_bots = [b for b in request.bots if b not in available_bots]
    if invalid_bots:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bots: {invalid_bots}. Available: {available_bots}",
        )

    from uuid import uuid4

    sweep_id = str(uuid4())[:8]
    total_combos = len(request.bots) * len(request.symbols) * len(request.timeframes)

    # Start background task
    task = asyncio.create_task(_run_sweep_job(sweep_id, request, settings))
    _sweep_jobs[sweep_id] = task

    logger.info("Started sweep job sweep_id=%s (%d combos)", sweep_id, total_combos)

    return SweepRunResponse(
        ok=True,
        sweep_id=sweep_id,
        total_combos=total_combos,
        message=f"Sweep started: {len(request.bots)} bots × {len(request.symbols)} symbols × {len(request.timeframes)} timeframes",
    )


@router.get("/sweep/status", response_model=SweepStatusResponse)
async def get_sweep_status(
    sweep_id: str = Query(..., description="Sweep ID"),
) -> SweepStatusResponse:
    """Get sweep job status."""
    # Check if completed
    if sweep_id in _sweep_results:
        result = _sweep_results[sweep_id]
        status = "done" if result.ok else "failed"
        return SweepStatusResponse(
            sweep_id=sweep_id,
            status=status,
            completed_combos=result.completed_combos,
            total_combos=result.total_combos,
            message="Sweep completed",
        )

    # Check if running
    if sweep_id in _sweep_jobs:
        task = _sweep_jobs[sweep_id]
        if task.done():
            try:
                result = task.result()
                _sweep_results[sweep_id] = result
                del _sweep_jobs[sweep_id]
                status = "done" if result.ok else "failed"
                return SweepStatusResponse(
                    sweep_id=sweep_id,
                    status=status,
                    completed_combos=result.completed_combos,
                    total_combos=result.total_combos,
                    message="Sweep completed",
                )
            except Exception as e:
                return SweepStatusResponse(
                    sweep_id=sweep_id,
                    status="failed",
                    message=str(e),
                )

        return SweepStatusResponse(
            sweep_id=sweep_id,
            status="running",
            message="Sweep in progress",
        )

    raise HTTPException(status_code=404, detail=f"Sweep '{sweep_id}' not found")


@router.get("/sweep/results", response_model=SweepResultsResponse)
async def get_sweep_results(
    sweep_id: str = Query(..., description="Sweep ID"),
) -> SweepResultsResponse:
    """Get sweep results."""
    # Check active jobs first
    if sweep_id in _sweep_jobs:
        task = _sweep_jobs[sweep_id]
        if task.done():
            try:
                result = task.result()
                _sweep_results[sweep_id] = result
                del _sweep_jobs[sweep_id]
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    if sweep_id not in _sweep_results:
        if sweep_id in _sweep_jobs:
            raise HTTPException(status_code=202, detail="Sweep still running")
        raise HTTPException(status_code=404, detail=f"Sweep '{sweep_id}' not found")

    result = _sweep_results[sweep_id]

    top_performers = [
        {
            "bot": r.bot,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "sharpe": r.sharpe,
            "max_drawdown": r.max_drawdown,
            "win_rate": r.win_rate,
            "total_trades": r.total_trades,
            "pnl": r.pnl,
        }
        for r in result.top_performers
    ]

    return SweepResultsResponse(
        sweep_id=sweep_id,
        ok=result.ok,
        completed_combos=result.completed_combos,
        failed_combos=result.failed_combos,
        top_performers=top_performers,
        artefact_path=result.artefact_path,
    )
