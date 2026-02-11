"""
API routes for autopilot service.

Endpoints to enable/disable autopilot and query state.
DEMO-only — returns 403 in LIVE mode.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from solat_engine.autopilot.service import AutopilotService, get_autopilot_service
from solat_engine.config import Settings, TradingMode, get_settings_dep
from solat_engine.logging import get_logger

router = APIRouter(prefix="/autopilot", tags=["Autopilot"])
logger = get_logger(__name__)


def _get_service() -> AutopilotService:
    """Get autopilot service or raise 503."""
    svc = get_autopilot_service()
    if svc is None:
        raise HTTPException(status_code=503, detail="Autopilot service not initialised")
    return svc


@router.get("/status")
async def get_autopilot_status() -> dict[str, Any]:
    """Get autopilot state and metrics."""
    svc = get_autopilot_service()
    if svc is None:
        return {
            "enabled": False,
            "combo_count": 0,
            "cycle_count": 0,
            "signals_generated": 0,
            "intents_routed": 0,
            "blocked_reasons": ["Autopilot service not initialised"],
        }
    state = svc.get_state()
    return state.model_dump()


@router.post("/enable")
async def enable_autopilot(
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    """Enable autopilot (DEMO only)."""
    if settings.mode == TradingMode.LIVE:
        raise HTTPException(
            status_code=403,
            detail="Autopilot is DEMO-only. Cannot enable in LIVE mode.",
        )

    svc = _get_service()
    state = await svc.enable()

    if state.blocked_reasons:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot enable autopilot: {'; '.join(state.blocked_reasons)}",
        )

    return {"ok": True, "message": "Autopilot enabled", **state.model_dump()}


@router.post("/disable")
async def disable_autopilot() -> dict[str, Any]:
    """Disable autopilot."""
    svc = _get_service()
    state = await svc.disable()
    return {"ok": True, "message": "Autopilot disabled", **state.model_dump()}


@router.get("/combos")
async def get_autopilot_combos() -> dict[str, Any]:
    """Get active combos with buffer sizes."""
    svc = get_autopilot_service()
    if svc is None:
        return {"combos": [], "count": 0}
    combos = svc.get_combos()
    return {"combos": combos, "count": len(combos)}
