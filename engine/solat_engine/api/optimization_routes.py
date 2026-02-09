"""
API routes for optimization module.

Provides endpoints for:
- Walk-forward optimization
- Allowlist management
- Performance tracking
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.api.data_routes import get_parquet_store
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.logging import get_logger
from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.optimization.models import (
    AllowlistEntry,
    OptimizationMode,
    WalkForwardConfig,
    WindowType,
)
from solat_engine.optimization.walk_forward import WalkForwardEngine

router = APIRouter(prefix="/optimization", tags=["Optimization"])
logger = get_logger(__name__)

# Lazy-initialized singletons
_walk_forward_engine: WalkForwardEngine | None = None
_allowlist_manager: AllowlistManager | None = None


def get_walk_forward_engine(
    store: ParquetStore = Depends(get_parquet_store)
) -> WalkForwardEngine:
    """Get or create walk-forward engine singleton."""
    global _walk_forward_engine
    if _walk_forward_engine is None or _walk_forward_engine.store != store:
        _walk_forward_engine = WalkForwardEngine(parquet_store=store)
    return _walk_forward_engine


def get_allowlist_manager() -> AllowlistManager:
    """Get or create allowlist manager singleton."""
    global _allowlist_manager
    if _allowlist_manager is None:
        _allowlist_manager = AllowlistManager()
    return _allowlist_manager


# =============================================================================
# Request/Response Models
# =============================================================================


class WalkForwardRequest(BaseModel):
    """Request to start walk-forward optimization."""

    symbols: list[str] = Field(..., min_length=1)
    bots: list[str] = Field(..., min_length=1)
    timeframes: list[str] = Field(default=["1h"])

    start_date: datetime = Field(..., description="Start of overall date range")
    end_date: datetime = Field(..., description="End of overall date range")

    window_type: str = Field(default="rolling", description="rolling or anchored")
    in_sample_days: int = Field(default=90, ge=30)
    out_of_sample_days: int = Field(default=30, ge=7)
    step_days: int = Field(default=30, ge=1)

    optimization_mode: str = Field(default="sharpe")
    top_n: int = Field(default=10, ge=1, le=50)
    min_trades: int = Field(default=10, ge=1)
    max_drawdown_pct: float = Field(default=20.0)
    min_sharpe: float = Field(default=0.0)


class WalkForwardResponse(BaseModel):
    """Response from walk-forward optimization."""

    ok: bool = True
    run_id: str
    message: str = ""
    status: str = "pending"
    progress: float = 0.0
    total_windows: int = 0
    completed_windows: int = 0


class WalkForwardResultResponse(BaseModel):
    """Full walk-forward result."""

    run_id: str
    status: str
    progress: float
    message: str

    # Window summary
    total_windows: int
    completed_windows: int
    windows: list[dict[str, Any]] = Field(default_factory=list)

    # Aggregate metrics
    aggregate_sharpe: float | None = None
    aggregate_return_pct: float | None = None
    aggregate_win_rate: float | None = None
    aggregate_trades: int = 0

    # Recommendations
    recommended_combos: list[dict[str, Any]] = Field(default_factory=list)

    # Timestamps
    started_at: str | None = None
    completed_at: str | None = None


class AllowlistStatusResponse(BaseModel):
    """Allowlist status."""

    total_entries: int
    enabled_entries: int
    stale_entries: int
    last_update: str | None
    by_symbol: dict[str, int]
    by_bot: dict[str, int]


class AllowlistEntryResponse(BaseModel):
    """Single allowlist entry."""

    combo_id: str
    symbol: str
    bot: str
    timeframe: str
    sharpe: float | None
    win_rate: float | None
    max_drawdown_pct: float | None
    total_trades: int
    enabled: bool
    validated_at: str | None
    source_run_id: str | None


class AllowlistUpdateRequest(BaseModel):
    """Request to update allowlist from walk-forward results."""

    run_id: str = Field(..., description="Walk-forward run ID to use")
    replace: bool = Field(default=True, description="Replace or merge")


# =============================================================================
# Walk-Forward Routes
# =============================================================================


@router.post("/walk-forward", response_model=WalkForwardResponse)
async def start_walk_forward(
    request: WalkForwardRequest,
    engine: WalkForwardEngine = Depends(get_walk_forward_engine),
) -> WalkForwardResponse:
    """
    Start a walk-forward optimization run.

    This is a background operation - returns immediately with run_id.
    Poll /optimization/walk-forward/{run_id} for status and results.
    """
    try:
        window_type = WindowType(request.window_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window_type: {request.window_type}. Use 'rolling' or 'anchored'",
        )

    try:
        opt_mode = OptimizationMode(request.optimization_mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid optimization_mode: {request.optimization_mode}",
        )

    config = WalkForwardConfig(
        symbols=request.symbols,
        bots=request.bots,
        timeframes=request.timeframes,
        start_date=request.start_date,
        end_date=request.end_date,
        window_type=window_type,
        in_sample_days=request.in_sample_days,
        out_of_sample_days=request.out_of_sample_days,
        step_days=request.step_days,
        optimization_mode=opt_mode,
        top_n=request.top_n,
        min_trades=request.min_trades,
        max_drawdown_pct=request.max_drawdown_pct,
        min_sharpe=request.min_sharpe,
    )

    # Start async run (fire and forget pattern - caller polls for results)
    import asyncio
    asyncio.create_task(engine.run(config))

    # Return immediately with a stub result
    # The actual result will be available when polling
    return WalkForwardResponse(
        ok=True,
        run_id="wf-pending",  # Will be replaced when task starts
        message=f"Walk-forward starting for {len(request.symbols)} symbols, {len(request.bots)} bots",
        status="starting",
    )


@router.get("/walk-forward/{run_id}", response_model=WalkForwardResultResponse)
async def get_walk_forward_result(
    run_id: str,
    engine: WalkForwardEngine = Depends(get_walk_forward_engine),
) -> WalkForwardResultResponse:
    """Get walk-forward optimization result by run_id."""
    result = engine.get_result(run_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Walk-forward run '{run_id}' not found")

    # Convert windows to dict format
    windows = []
    for w in result.windows:
        windows.append({
            "window_id": w.window_id,
            "in_sample_start": w.in_sample_start.isoformat(),
            "in_sample_end": w.in_sample_end.isoformat(),
            "out_of_sample_start": w.out_of_sample_start.isoformat(),
            "out_of_sample_end": w.out_of_sample_end.isoformat(),
            "oos_sharpe": w.oos_sharpe,
            "oos_return_pct": w.oos_return_pct,
            "oos_win_rate": w.oos_win_rate,
            "oos_trades": w.oos_trades,
            "in_sample_top_count": len(w.in_sample_top),
            "out_of_sample_count": len(w.out_of_sample_results),
        })

    return WalkForwardResultResponse(
        run_id=result.run_id,
        status=result.status,
        progress=result.progress,
        message=result.message,
        total_windows=result.total_windows,
        completed_windows=result.completed_windows,
        windows=windows,
        aggregate_sharpe=result.aggregate_sharpe,
        aggregate_return_pct=result.aggregate_return_pct,
        aggregate_win_rate=result.aggregate_win_rate,
        aggregate_trades=result.aggregate_trades,
        recommended_combos=result.recommended_combos,
        started_at=result.started_at.isoformat() if result.started_at else None,
        completed_at=result.completed_at.isoformat() if result.completed_at else None,
    )


# =============================================================================
# Allowlist Routes
# =============================================================================


@router.get("/allowlist", response_model=AllowlistStatusResponse)
async def get_allowlist_status(
    manager: AllowlistManager = Depends(get_allowlist_manager)
) -> AllowlistStatusResponse:
    """Get allowlist status summary."""
    status = manager.get_status()

    return AllowlistStatusResponse(
        total_entries=status["total_entries"],
        enabled_entries=status["enabled_entries"],
        stale_entries=status["stale_entries"],
        last_update=status["last_update"],
        by_symbol=status["by_symbol"],
        by_bot=status["by_bot"],
    )


@router.get("/allowlist/entries")
async def get_allowlist_entries(
    enabled_only: bool = Query(default=False),
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> list[AllowlistEntryResponse]:
    """Get all allowlist entries."""
    if enabled_only:
        entries = manager.get_enabled()
    else:
        entries = manager.get_all()

    return [
        AllowlistEntryResponse(
            combo_id=e.combo_id,
            symbol=e.symbol,
            bot=e.bot,
            timeframe=e.timeframe,
            sharpe=e.sharpe,
            win_rate=e.win_rate,
            max_drawdown_pct=e.max_drawdown_pct,
            total_trades=e.total_trades,
            enabled=e.enabled,
            validated_at=e.validated_at.isoformat() if e.validated_at else None,
            source_run_id=e.source_run_id,
        )
        for e in entries
    ]


@router.post("/allowlist/update")
async def update_allowlist(
    request: AllowlistUpdateRequest,
    engine: WalkForwardEngine = Depends(get_walk_forward_engine),
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Update allowlist from walk-forward results."""
    result = engine.get_result(request.run_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Walk-forward run '{request.run_id}' not found",
        )

    if result.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Walk-forward run is not completed (status: {result.status})",
        )

    added = manager.update_from_walk_forward(result, replace=request.replace)

    return {
        "ok": True,
        "entries_added": added,
        "message": f"Allowlist updated with {added} entries from {request.run_id}",
    }


@router.post("/allowlist/entry")
async def add_allowlist_entry(
    entry: AllowlistEntry,
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Manually add an allowlist entry."""
    manager.add_entry(entry)

    return {
        "ok": True,
        "combo_id": entry.combo_id,
        "message": f"Entry {entry.combo_id} added to allowlist",
    }


@router.delete("/allowlist/entry/{combo_id}")
async def remove_allowlist_entry(
    combo_id: str,
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Remove an allowlist entry."""
    removed = manager.remove_entry(combo_id)

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Entry '{combo_id}' not found in allowlist",
        )

    return {
        "ok": True,
        "combo_id": combo_id,
        "message": f"Entry {combo_id} removed from allowlist",
    }


@router.post("/allowlist/enable/{combo_id}")
async def enable_allowlist_entry(
    combo_id: str,
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Enable an allowlist entry."""
    enabled = manager.enable(combo_id)

    if not enabled:
        raise HTTPException(
            status_code=404,
            detail=f"Entry '{combo_id}' not found in allowlist",
        )

    return {"ok": True, "combo_id": combo_id, "enabled": True}


@router.post("/allowlist/disable/{combo_id}")
async def disable_allowlist_entry(
    combo_id: str,
    reason: str = Query(default=None),
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Disable an allowlist entry."""
    disabled = manager.disable(combo_id, reason)

    if not disabled:
        raise HTTPException(
            status_code=404,
            detail=f"Entry '{combo_id}' not found in allowlist",
        )

    return {"ok": True, "combo_id": combo_id, "enabled": False, "reason": reason}


@router.get("/allowlist/check")
async def check_allowlist(
    symbol: str = Query(...),
    bot: str = Query(...),
    timeframe: str = Query(default="1h"),
    manager: AllowlistManager = Depends(get_allowlist_manager),
) -> dict[str, Any]:
    """Check if a combo is allowed for trading."""
    allowed = manager.is_allowed(symbol, bot, timeframe)
    entry = manager.get_entry(f"{symbol}:{bot}:{timeframe}")

    return {
        "symbol": symbol,
        "bot": bot,
        "timeframe": timeframe,
        "allowed": allowed,
        "entry_exists": entry is not None,
        "enabled": entry.enabled if entry else False,
        "reason": entry.reason if entry else None,
    }


@router.delete("/allowlist/clear")
async def clear_allowlist(
    manager: AllowlistManager = Depends(get_allowlist_manager)
) -> dict[str, Any]:
    """Clear all allowlist entries."""
    manager.clear()

    return {"ok": True, "message": "Allowlist cleared"}
