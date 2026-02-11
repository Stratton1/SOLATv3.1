"""
API routes for recommendation sets.

Endpoints to generate, list, retrieve, and apply recommended
strategy/symbol/timeframe combos from WFO results.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from solat_engine.config import Settings, TradingMode, get_settings_dep
from solat_engine.logging import get_logger
from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.optimization.recommended_set import RecommendedSetManager
from solat_engine.optimization.walk_forward import WalkForwardEngine

router = APIRouter(prefix="/optimization/recommendations", tags=["Recommendations"])
logger = get_logger(__name__)


def get_wf_engine_for_recommendations(
    settings: Settings = Depends(get_settings_dep),
) -> WalkForwardEngine:
    """
    Dependency: get WalkForwardEngine for recommendation generation.

    Tests can override via app.dependency_overrides[get_wf_engine_for_recommendations].
    """
    from solat_engine.data.parquet_store import ParquetStore

    store = ParquetStore(settings.data_dir)
    return WalkForwardEngine(parquet_store=store)

# Lazy singleton
_recommended_set_manager: RecommendedSetManager | None = None


def get_recommended_set_manager() -> RecommendedSetManager:
    """Get or create recommendation set manager singleton."""
    global _recommended_set_manager
    if _recommended_set_manager is None:
        _recommended_set_manager = RecommendedSetManager()
    return _recommended_set_manager


def set_recommended_set_manager(mgr: RecommendedSetManager | None) -> None:
    """Set the recommendation set manager (for testing)."""
    global _recommended_set_manager
    _recommended_set_manager = mgr


# =============================================================================
# Request/Response Models
# =============================================================================


class GenerateRequest(BaseModel):
    """Request to generate a recommended set from WFO results."""

    wfo_run_ids: list[str] = Field(..., min_length=1)
    max_combos: int = Field(default=15, ge=1, le=50)
    max_per_symbol: int = Field(default=3, ge=1)
    max_per_bot: int = Field(default=5, ge=1)
    min_oos_sharpe: float = Field(default=0.3)
    min_oos_trades: int = Field(default=20, ge=1)
    min_folds_profitable_pct: float = Field(default=0.5, ge=0, le=1)
    max_sharpe_cv: float = Field(default=2.0, ge=0)


class RecommendedSetResponse(BaseModel):
    """Response for a recommended set."""

    id: str
    generated_at: str
    criteria: dict[str, Any]
    combos: list[dict[str, Any]]
    rejected_count: int
    source_run_ids: list[str]
    status: str
    applied_at: str | None


class RecommendedSetSummary(BaseModel):
    """Summary of a recommended set for list endpoints."""

    id: str
    generated_at: str
    combos_count: int
    status: str
    source_run_ids: list[str]


# =============================================================================
# Routes
# =============================================================================


def _to_response(rs: Any) -> RecommendedSetResponse:
    """Convert RecommendedSet model to response."""
    return RecommendedSetResponse(
        id=rs.id,
        generated_at=rs.generated_at.isoformat(),
        criteria=rs.criteria,
        combos=rs.combos,
        rejected_count=rs.rejected_count,
        source_run_ids=rs.source_run_ids,
        status=rs.status,
        applied_at=rs.applied_at.isoformat() if rs.applied_at else None,
    )


@router.post("/generate", response_model=RecommendedSetResponse)
async def generate_recommendations(
    request: GenerateRequest,
    mgr: RecommendedSetManager = Depends(get_recommended_set_manager),
    wf_engine: WalkForwardEngine = Depends(get_wf_engine_for_recommendations),
) -> RecommendedSetResponse:
    """Generate a recommended set by running selector on WFO results."""
    from solat_engine.optimization.selector import SelectionConstraints

    results = []
    for run_id in request.wfo_run_ids:
        result = wf_engine.get_result(run_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Walk-forward run '{run_id}' not found",
            )
        if result.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Walk-forward run '{run_id}' not completed (status: {result.status})",
            )
        results.append(result)

    constraints = SelectionConstraints(
        max_combos=request.max_combos,
        max_per_symbol=request.max_per_symbol,
        max_per_bot=request.max_per_bot,
        min_oos_sharpe=request.min_oos_sharpe,
        min_oos_trades=request.min_oos_trades,
        min_folds_profitable_pct=request.min_folds_profitable_pct,
        max_sharpe_cv=request.max_sharpe_cv,
    )

    rs = mgr.generate(results, constraints)
    return _to_response(rs)


@router.get("/latest", response_model=RecommendedSetResponse)
async def get_latest_recommendation(
    mgr: RecommendedSetManager = Depends(get_recommended_set_manager),
) -> RecommendedSetResponse:
    """Get the most recent recommendation set."""
    rs = mgr.get_latest()
    if rs is None:
        raise HTTPException(status_code=404, detail="No recommendations found")
    return _to_response(rs)


@router.get("/{rec_id}", response_model=RecommendedSetResponse)
async def get_recommendation(
    rec_id: str,
    mgr: RecommendedSetManager = Depends(get_recommended_set_manager),
) -> RecommendedSetResponse:
    """Get a recommendation set by ID."""
    rs = mgr.get(rec_id)
    if rs is None:
        raise HTTPException(status_code=404, detail=f"Recommendation '{rec_id}' not found")
    return _to_response(rs)


@router.get("", response_model=list[RecommendedSetSummary])
async def list_recommendations(
    mgr: RecommendedSetManager = Depends(get_recommended_set_manager),
) -> list[RecommendedSetSummary]:
    """List all recommendation sets (summary)."""
    return [
        RecommendedSetSummary(
            id=rs.id,
            generated_at=rs.generated_at.isoformat(),
            combos_count=len(rs.combos),
            status=rs.status,
            source_run_ids=rs.source_run_ids,
        )
        for rs in mgr.list_all()
    ]


@router.post("/{rec_id}/apply-demo")
async def apply_recommendation_demo(
    rec_id: str,
    mgr: RecommendedSetManager = Depends(get_recommended_set_manager),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """
    Apply a recommendation set to the allowlist (DEMO only).

    Returns 403 if in LIVE mode.
    """
    from solat_engine.api.optimization_routes import get_allowlist_manager

    # Service-level LIVE check
    if settings.mode == TradingMode.LIVE:
        raise HTTPException(
            status_code=403,
            detail="Cannot apply recommendations in LIVE mode",
        )

    allowlist_mgr = get_allowlist_manager()

    try:
        rs = await mgr.apply_to_demo(rec_id, allowlist_mgr, settings)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if rs is None:
        raise HTTPException(status_code=404, detail=f"Recommendation '{rec_id}' not found")

    return {
        "ok": True,
        "recommendation_id": rs.id,
        "combos_applied": len(rs.combos),
        "status": rs.status,
        "message": f"Applied {len(rs.combos)} combos to allowlist",
    }
