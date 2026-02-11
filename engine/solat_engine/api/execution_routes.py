"""
Execution API routes.

Endpoints for live execution control, monitoring, and safety.

LIVE Trading Safety:
- All LIVE operations require multi-layer gate validation
- Endpoints support the UI GoLive modal workflow
- Fail-closed design: any uncertainty blocks LIVE trading
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.broker.ig.client import AsyncIGClient
from solat_engine.config import Settings, get_settings_dep
from solat_engine.execution.gates import GateMode, get_trading_gates
from solat_engine.execution.models import (
    ExecutionConfig,
    ExecutionMode,
    LedgerEntry,
    OrderIntent,
    OrderSide,
    OrderType,
)
from solat_engine.execution.router import ExecutionRouter
from solat_engine.logging import get_logger

router = APIRouter(prefix="/execution", tags=["Execution"])
logger = get_logger(__name__)

# Singleton execution router
_execution_router: ExecutionRouter | None = None
_ig_client: AsyncIGClient | None = None


def get_execution_config(settings: Settings = Depends(get_settings_dep)) -> ExecutionConfig:
    """Get execution configuration from settings."""
    return ExecutionConfig(
        mode=ExecutionMode(settings.execution_mode),
        max_position_size=settings.max_position_size,
        max_concurrent_positions=settings.max_concurrent_positions,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_trades_per_hour=settings.max_trades_per_hour,
        per_symbol_exposure_cap=settings.per_symbol_exposure_cap,
        require_sl=settings.require_sl,
        close_on_kill_switch=settings.close_on_kill_switch,
        reconcile_interval_s=settings.execution_reconcile_interval_s,
        require_arm_confirmation=settings.require_arm_confirmation,
    )


def get_execution_router(
    settings: Settings = Depends(get_settings_dep),
    config: ExecutionConfig = Depends(get_execution_config),
) -> ExecutionRouter:
    """Get or create execution router singleton."""
    global _execution_router
    # In tests, if settings.data_dir changed, we MUST recreate the router
    if _execution_router is None or _execution_router._data_dir != settings.data_dir:
        _execution_router = ExecutionRouter(config, settings.data_dir)
    else:
        # Update config reference in case it was overridden
        _execution_router.config = config
    return _execution_router


def get_ig_client(settings: Settings = Depends(get_settings_dep)) -> AsyncIGClient:
    """Get or create IG client singleton."""
    global _ig_client
    if _ig_client is None:
        _ig_client = AsyncIGClient(settings, logger)
    else:
        # Update settings reference
        _ig_client.settings = settings
    return _ig_client


# =============================================================================
# Request/Response Models
# =============================================================================


class ConnectResponse(BaseModel):
    """Response from connect endpoint."""

    ok: bool
    account_id: str | None = None
    balance: float | None = None
    mode: str | None = None
    error: str | None = None


class ArmRequest(BaseModel):
    """Request to arm execution."""

    confirm: bool = Field(
        default=False,
        description="Must be true to arm (safety confirmation)",
    )
    live_mode: bool = Field(
        default=False,
        description="If true, attempt to arm in LIVE mode (requires all gates)",
    )


class ArmResponse(BaseModel):
    """Response from arm endpoint."""

    ok: bool
    armed: bool = False
    mode: str | None = None
    live: bool = False
    error: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StatusResponse(BaseModel):
    """Execution status response."""

    mode: str
    connected: bool
    armed: bool
    kill_switch_active: bool
    signals_enabled: bool = True
    demo_arm_enabled: bool = False
    account_id: str | None = None
    account_balance: float | None = None
    open_position_count: int = 0
    realized_pnl_today: float = 0.0
    trades_this_hour: int = 0
    last_error: str | None = None


class KillSwitchRequest(BaseModel):
    """Kill switch activation request."""

    reason: str = Field(default="manual", description="Reason for activation")


class KillSwitchResponse(BaseModel):
    """Kill switch response."""

    ok: bool
    message: str = ""
    activated_at: str | None = None
    reason: str | None = None
    close_positions: bool = False


class ClosePositionRequest(BaseModel):
    """Request to close a position."""

    deal_id: str
    size: float | None = None


class ClosePositionResponse(BaseModel):
    """Response from close position."""

    ok: bool
    error: str | None = None
    result: dict[str, Any] | None = None


class PositionsResponse(BaseModel):
    """Positions list response."""

    positions: list[dict[str, Any]]
    count: int


class RunOnceRequest(BaseModel):
    """Request for run-once cycle."""

    symbol: str
    bot: str
    side: str = Field(description="BUY or SELL")
    size: float = Field(default=0.1)
    stop_loss: float | None = None
    take_profit: float | None = None


class RunOnceResponse(BaseModel):
    """Response from run-once cycle."""

    ok: bool
    intent_id: str | None = None
    status: str | None = None
    deal_id: str | None = None
    error: str | None = None


class GateStatusResponse(BaseModel):
    """
    Response from gate status endpoint.

    Shows current trading gate evaluation for LIVE mode.
    """

    allowed: bool
    mode: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    confirmation_status: dict[str, Any] = Field(default_factory=dict)
    account_status: dict[str, Any] = Field(default_factory=dict)


class LiveConfirmRequest(BaseModel):
    """
    Request to confirm LIVE trading mode.

    All fields are required and validated:
    - phrase: Must match "ENABLE LIVE TRADING"
    - token: Must match LIVE_ENABLE_TOKEN from config
    - account_id: Must match verified broker account
    """

    phrase: str = Field(description="Confirmation phrase (ENABLE LIVE TRADING)")
    token: str = Field(description="LIVE_ENABLE_TOKEN from .env")
    account_id: str = Field(description="Broker account ID to trade on")


class LiveConfirmResponse(BaseModel):
    """Response from LIVE confirmation."""

    ok: bool
    message: str = ""
    mode: str | None = None
    confirmed_at: str | None = None
    expires_in_seconds: int | None = None


class LiveRevokeResponse(BaseModel):
    """Response from LIVE revoke."""

    ok: bool
    message: str = ""


class PreliveCheckResult(BaseModel):
    """Pre-live check result."""

    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    timestamp: str | None = None


class ReconciliationReportResponse(BaseModel):
    """Response from reconciliation report endpoint."""

    ok: bool
    last_reconcile_at: str | None = None
    position_count: int = 0
    sync_status: str = "unknown"
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EventItem(BaseModel):
    """Single execution event for chart markers."""

    ts: str
    type: str  # INTENT, SUBMIT, FILL, REJECT
    side: str | None = None  # BUY or SELL
    price: float | None = None
    size: float | None = None
    reason: str | None = None
    order_id: str | None = None
    bot: str | None = None


class EventsResponse(BaseModel):
    """Response from execution events endpoint."""

    events: list[EventItem] = Field(default_factory=list)
    total: int = 0


class FillItem(BaseModel):
    """Single fill for blotter."""

    ts: str
    symbol: str | None = None
    side: str | None = None
    price: float | None = None
    size: float | None = None
    pnl: float | None = None
    bot: str | None = None
    order_id: str | None = None
    deal_id: str | None = None


class FillsResponse(BaseModel):
    """Response from fills endpoint."""

    fills: list[FillItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class OrderItem(BaseModel):
    """Single order for blotter."""

    ts: str
    symbol: str | None = None
    side: str | None = None
    size: float | None = None
    status: str | None = None
    order_type: str | None = None
    bot: str | None = None
    intent_id: str | None = None
    deal_reference: str | None = None


class OrdersResponse(BaseModel):
    """Response from orders endpoint."""

    orders: list[OrderItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class ModeGetResponse(BaseModel):
    """Response for GET /execution/mode."""

    signals_enabled: bool
    demo_arm_enabled: bool
    mode: str


class ModeSetRequest(BaseModel):
    """Request to set execution mode flags."""

    signals_enabled: bool | None = None
    demo_arm_enabled: bool | None = None


class ModeSetResponse(BaseModel):
    """Response for POST /execution/mode."""

    ok: bool = True
    signals_enabled: bool
    demo_arm_enabled: bool
    mode: str


class SignalItem(BaseModel):
    """Single signal entry for the signals panel."""

    ts: str
    symbol: str | None = None
    bot: str | None = None
    timeframe: str | None = None
    side: str | None = None
    size: float | None = None
    confidence: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    source: str | None = None
    intent_id: str | None = None


class SignalsResponse(BaseModel):
    """Response from signals endpoint."""

    signals: list[SignalItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 100


class AllowlistSetRequest(BaseModel):
    """Request to set symbol allowlist."""

    symbols: list[str]


class AllowlistSetResponse(BaseModel):
    """Response from setting allowlist."""

    ok: bool = True
    count: int = 0


class AllowlistGetResponse(BaseModel):
    """Response from getting allowlist."""

    symbols: list[str] = Field(default_factory=list)
    active: bool = False


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/status", response_model=StatusResponse)
async def get_status(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> StatusResponse:
    """Get current execution status."""
    state = exec_router.state

    return StatusResponse(
        mode=state.mode.value,
        connected=state.connected,
        armed=state.armed,
        kill_switch_active=state.kill_switch_active,
        signals_enabled=state.signals_enabled,
        demo_arm_enabled=state.demo_arm_enabled,
        account_id=state.account_id,
        account_balance=state.account_balance,
        open_position_count=state.open_position_count,
        realized_pnl_today=state.realized_pnl_today,
        trades_this_hour=state.trades_this_hour,
        last_error=state.last_error,
    )


@router.get("/state", response_model=StatusResponse)
async def get_state_compat(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> StatusResponse:
    """
    Compatibility alias for legacy clients still calling /execution/state.

    Keep behavior identical to /execution/status so mixed UI versions do not
    generate persistent 404 noise during polling.
    """
    return await get_status(exec_router)


@router.post("/connect", response_model=ConnectResponse)
async def connect(
    settings: Settings = Depends(get_settings_dep),
    config: ExecutionConfig = Depends(get_execution_config),
    exec_router: ExecutionRouter = Depends(get_execution_router),
    ig_client: AsyncIGClient = Depends(get_ig_client),
) -> ConnectResponse:
    """
    Connect to IG broker.

    Requires IG credentials to be configured in environment.
    LIVE mode requires all trading gates to pass.
    """
    # Check credentials
    if not settings.has_ig_credentials:
        raise HTTPException(
            status_code=400,
            detail="IG credentials not configured",
        )

    # For LIVE mode, verify trading gates allow it
    if config.mode == ExecutionMode.LIVE:
        gates = get_trading_gates()
        gate_status = gates.evaluate(GateMode.LIVE)
        if not gate_status.allowed:
            raise HTTPException(
                status_code=400,
                detail=f"LIVE mode blocked: {'; '.join(gate_status.blockers[:3])}",
            )

    # Login to IG
    try:
        await ig_client.login()
    except Exception as e:
        logger.error("IG login failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")

    # Connect execution router
    result = await exec_router.connect(ig_client, settings=settings)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Connection failed"))

    return ConnectResponse(
        ok=True,
        account_id=result.get("account_id"),
        balance=result.get("balance"),
        mode=result.get("mode"),
    )


@router.post("/disconnect", response_model=dict[str, Any])
async def disconnect(
    exec_router: ExecutionRouter = Depends(get_execution_router),
    ig_client: AsyncIGClient = Depends(get_ig_client),
) -> dict[str, Any]:
    """Disconnect from broker."""
    result = await exec_router.disconnect()

    # Close IG client
    await ig_client.close()

    global _ig_client
    _ig_client = None

    return result


@router.post("/arm", response_model=ArmResponse)
async def arm(
    request: ArmRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ArmResponse:
    """
    Arm execution (enable order submission).

    Requires confirmation (confirm=true) for safety.

    For LIVE mode (live_mode=true):
    - All trading gates must pass
    - UI confirmation must be valid (not expired)
    - Account must be verified and match LIVE_ACCOUNT_ID
    - Pre-live check must have passed recently
    """
    result = await exec_router.arm(confirm=request.confirm, live_mode=request.live_mode)

    return ArmResponse(
        ok=result.get("ok", False),
        armed=result.get("armed", False),
        mode=result.get("mode"),
        live=result.get("live", False),
        error=result.get("error"),
        blockers=result.get("blockers", []),
        warnings=result.get("warnings", []),
    )


@router.post("/disarm", response_model=ArmResponse)
async def disarm(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ArmResponse:
    """Disarm execution (disable order submission)."""
    result = await exec_router.disarm()

    return ArmResponse(
        ok=result.get("ok", False),
        armed=result.get("armed", False),
    )


@router.post("/kill-switch/activate", response_model=KillSwitchResponse)
async def activate_kill_switch(
    request: KillSwitchRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> KillSwitchResponse:
    """
    Activate kill switch.

    Immediately disarms trading and blocks all new orders.
    Optionally closes all positions (if configured).
    """
    result = await exec_router.activate_kill_switch(reason=request.reason)

    return KillSwitchResponse(
        ok=result.get("ok", False),
        message=result.get("message", ""),
        activated_at=result.get("activated_at"),
        reason=result.get("reason"),
        close_positions=result.get("close_positions", False),
    )


@router.post("/kill-switch/reset", response_model=KillSwitchResponse)
async def reset_kill_switch(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> KillSwitchResponse:
    """Reset kill switch (re-enable trading)."""
    result = await exec_router.reset_kill_switch()

    return KillSwitchResponse(
        ok=result.get("ok", False),
        message=result.get("message", ""),
    )


@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> PositionsResponse:
    """Get current broker positions."""
    if not exec_router.state.connected:
        raise HTTPException(status_code=400, detail="Not connected")

    positions = exec_router.get_positions()

    return PositionsResponse(
        positions=[p.model_dump() for p in positions],
        count=len(positions),
    )


@router.post("/close-position", response_model=ClosePositionResponse)
async def close_position(
    request: ClosePositionRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ClosePositionResponse:
    """Close a specific position."""
    if not exec_router.state.connected:
        raise HTTPException(status_code=400, detail="Not connected")

    result = await exec_router.close_position(
        deal_id=request.deal_id,
        size=request.size,
    )

    return ClosePositionResponse(
        ok=result.get("ok", False),
        error=result.get("error"),
        result=result.get("result"),
    )


@router.post("/run-once", response_model=RunOnceResponse)
async def run_once(
    request: RunOnceRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> RunOnceResponse:
    """
    Run a single execution cycle (for testing).

    Creates an order intent and routes it through the execution pipeline.
    Restricted to DEMO mode with demo_arm_enabled.
    """
    if exec_router.state.mode != ExecutionMode.DEMO:
        raise HTTPException(status_code=403, detail="Run-once is DEMO-only")

    if not exec_router.state.demo_arm_enabled:
        raise HTTPException(status_code=400, detail="DEMO arm must be enabled for run-once")

    if not exec_router.state.connected:
        raise HTTPException(status_code=400, detail="Not connected")

    # Create intent
    side = OrderSide.BUY if request.side.upper() == "BUY" else OrderSide.SELL
    intent = OrderIntent(
        symbol=request.symbol,
        side=side,
        size=request.size,
        order_type=OrderType.MARKET,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        bot=request.bot,
        reason_codes=["manual_test"],
    )

    # Route intent
    ack = await exec_router.route_intent(intent)

    return RunOnceResponse(
        ok=ack.status.value in ("FILLED", "ACKNOWLEDGED", "PENDING"),
        intent_id=str(ack.intent_id),
        status=ack.status.value,
        deal_id=ack.deal_id,
        error=ack.rejection_reason,
    )


# =============================================================================
# LIVE Trading Gates
# =============================================================================


@router.get("/gates", response_model=GateStatusResponse)
async def get_gates() -> GateStatusResponse:
    """
    Get current trading gate status.

    Returns the evaluation of all LIVE trading gates:
    - Config gate: LIVE_TRADING_ENABLED
    - Token gate: LIVE_ENABLE_TOKEN configured
    - Risk gate: All mandatory risk settings
    - Account gate: Account locked and verified
    - UI gate: User confirmation (with TTL)
    - Prelive gate: Pre-live check passed recently

    For DEMO mode, allowed is always True.
    For LIVE mode, all gates must pass.
    """
    gates = get_trading_gates()

    # Evaluate for LIVE mode to show all potential blockers
    gate_status = gates.evaluate(GateMode.LIVE)

    return GateStatusResponse(
        allowed=gate_status.allowed,
        mode=gate_status.mode.value,
        blockers=gate_status.blockers,
        warnings=gate_status.warnings,
        details=gate_status.details,
        confirmation_status=gates.get_confirmation_status(),
        account_status=gates.get_account_status(),
    )


@router.post("/live/confirm", response_model=LiveConfirmResponse)
async def confirm_live(
    request: LiveConfirmRequest,
    settings: Settings = Depends(get_settings_dep),
) -> LiveConfirmResponse:
    """
    Confirm LIVE trading mode.

    This is the final step in the UI GoLive workflow.
    All validations must pass:
    1. Phrase must match exactly: "ENABLE LIVE TRADING"
    2. Token must match LIVE_ENABLE_TOKEN
    3. Account must be verified with broker
    4. Pre-live check must have passed recently

    Confirmation is time-limited (default 10 minutes TTL).
    """
    gates = get_trading_gates()

    # Validate phrase (case-insensitive but must match exactly)
    expected_phrase = "ENABLE LIVE TRADING"
    phrase_matched = request.phrase.strip().upper() == expected_phrase

    if not phrase_matched:
        return LiveConfirmResponse(
            ok=False,
            message="Phrase does not match. Type exactly: ENABLE LIVE TRADING",
        )

    # Validate token using constant-time comparison
    token_matched = gates.verify_token(request.token)
    if not token_matched:
        logger.warning("LIVE confirmation rejected: invalid token")
        return LiveConfirmResponse(
            ok=False,
            message="Token does not match LIVE_ENABLE_TOKEN",
        )

    # Verify account is configured and matches
    if not settings.has_live_account_lock:
        return LiveConfirmResponse(
            ok=False,
            message="LIVE_ACCOUNT_ID not configured",
        )

    if settings.live_account_id != request.account_id:
        logger.warning(
            "LIVE confirmation rejected: account mismatch (expected=%s, got=%s)",
            settings.live_account_id,
            request.account_id,
        )
        return LiveConfirmResponse(
            ok=False,
            message="Account ID does not match configured LIVE_ACCOUNT_ID",
        )

    # Check account verification status
    account_status = gates.get_account_status()
    if not account_status.get("verified"):
        return LiveConfirmResponse(
            ok=False,
            message="Account not verified with broker. Connect first.",
        )

    # Check prelive gate
    gate_status = gates.evaluate(GateMode.LIVE)
    prelive_passed = "Pre-live check has never passed" not in gate_status.blockers
    prelive_passed = prelive_passed and not any(
        "Pre-live check too old" in b for b in gate_status.blockers
    )

    if not prelive_passed:
        return LiveConfirmResponse(
            ok=False,
            message="Pre-live check required before LIVE confirmation",
        )

    # All checks passed - set confirmation
    confirmation = gates.set_ui_confirmation(
        account_id=request.account_id,
        phrase_matched=phrase_matched,
        token_matched=token_matched,
        prelive_passed=prelive_passed,
    )

    logger.warning(
        "LIVE trading confirmed for account %s (TTL: %ds)",
        request.account_id,
        confirmation.ttl_seconds,
    )

    return LiveConfirmResponse(
        ok=True,
        message="LIVE trading confirmed",
        mode="LIVE",
        confirmed_at=confirmation.confirmed_at.isoformat(),
        expires_in_seconds=confirmation.ttl_seconds,
    )


@router.post("/live/revoke", response_model=LiveRevokeResponse)
async def revoke_live(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> LiveRevokeResponse:
    """
    Revoke LIVE trading confirmation.

    Immediately revokes the UI confirmation for LIVE trading.
    This blocks all LIVE trading until re-confirmed.
    Use this to quickly return to DEMO mode.
    """
    gates = get_trading_gates()

    # Revoke confirmation
    gates.revoke_ui_confirmation()

    # Also disarm if currently armed
    if exec_router.state.armed:
        await exec_router.disarm()

    logger.info("LIVE trading confirmation revoked")

    return LiveRevokeResponse(
        ok=True,
        message="LIVE confirmation revoked. Trading is now in DEMO mode.",
    )


@router.post("/prelive/run", response_model=PreliveCheckResult)
async def run_prelive_check(
    settings: Settings = Depends(get_settings_dep),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> PreliveCheckResult:
    """
    Run pre-live system check.

    Validates system readiness for LIVE trading:
    - Config validation
    - Broker connectivity
    - Account verification
    - Risk settings
    - Safety guard status

    Results are cached for use in LIVE confirmation.
    """
    from datetime import UTC, datetime

    gates = get_trading_gates()

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []

    # Check 1: Config validation
    config_ok = settings.live_trading_enabled and settings.has_live_token
    checks.append({
        "name": "Config validation",
        "passed": config_ok,
        "details": {
            "live_enabled": settings.live_trading_enabled,
            "has_token": settings.has_live_token,
        },
    })
    if not config_ok:
        blockers.append("Config: LIVE_TRADING_ENABLED or LIVE_ENABLE_TOKEN not set")

    # Check 2: Risk settings
    risk_blockers = settings.get_live_risk_blockers()
    risk_ok = len(risk_blockers) == 0
    checks.append({
        "name": "Risk settings",
        "passed": risk_ok,
        "details": {"blockers": risk_blockers},
    })
    if not risk_ok:
        blockers.extend(risk_blockers)

    # Check 3: Broker connectivity
    broker_ok = exec_router.state.connected
    checks.append({
        "name": "Broker connectivity",
        "passed": broker_ok,
        "details": {"connected": broker_ok, "account_id": exec_router.state.account_id},
    })
    if not broker_ok:
        blockers.append("Broker: Not connected")

    # Check 4: Account verification
    account_status = gates.get_account_status()
    account_ok = account_status.get("verified", False) and account_status.get("is_live", False)
    checks.append({
        "name": "Account verification",
        "passed": account_ok,
        "details": account_status,
    })
    if not account_ok:
        blockers.append("Account: Not verified or not a LIVE account")

    # Check 5: Account lock match
    lock_ok = (
        settings.has_live_account_lock
        and account_status.get("account_id") == settings.live_account_id
    )
    checks.append({
        "name": "Account lock",
        "passed": lock_ok,
        "details": {
            "configured_id": settings.live_account_id,
            "verified_id": account_status.get("account_id"),
        },
    })
    if not lock_ok:
        blockers.append("Account: ID does not match LIVE_ACCOUNT_ID")

    # Check 6: Safety guard status
    safety_ok = not exec_router.safety_guard.circuit_breaker_tripped
    checks.append({
        "name": "Safety guard",
        "passed": safety_ok,
        "details": {"circuit_breaker_ok": safety_ok},
    })
    if not safety_ok:
        blockers.append("Safety: Circuit breaker is tripped")

    # Check 7: Kill switch
    kill_ok = not exec_router.kill_switch.is_active
    checks.append({
        "name": "Kill switch",
        "passed": kill_ok,
        "details": {"kill_switch_inactive": kill_ok},
    })
    if not kill_ok:
        blockers.append("Safety: Kill switch is active")

    # Overall result
    passed = len(blockers) == 0

    # Record pass in gates if successful
    if passed:
        gates.record_prelive_pass()
        logger.info("Pre-live check PASSED - all %d checks OK", len(checks))
    else:
        logger.warning("Pre-live check FAILED - %d blockers: %s", len(blockers), blockers[:3])

    return PreliveCheckResult(
        passed=passed,
        checks=checks,
        blockers=blockers,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/reconcile/report", response_model=ReconciliationReportResponse)
async def get_reconciliation_report(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ReconciliationReportResponse:
    """
    Get reconciliation report.

    Shows position sync status between local state and broker:
    - Last reconciliation time
    - Position count
    - Sync status (in_sync, drifted, stale)
    - Any discrepancies found
    """
    if not exec_router.state.connected:
        return ReconciliationReportResponse(
            ok=False,
            sync_status="disconnected",
            warnings=["Not connected to broker"],
        )

    recon = exec_router.reconciliation

    # Get reconciliation status
    last_reconcile = recon.last_reconcile_time
    positions = exec_router.get_positions()

    # Determine sync status
    from datetime import UTC, datetime

    if last_reconcile is None:
        sync_status = "never_reconciled"
    else:
        age = (datetime.now(UTC) - last_reconcile).total_seconds()
        if age < 60:
            sync_status = "in_sync"
        elif age < 300:
            sync_status = "slightly_stale"
        else:
            sync_status = "stale"

    # Get any discrepancies
    discrepancies = recon.get_discrepancies() if hasattr(recon, "get_discrepancies") else []
    warnings = recon.get_warnings() if hasattr(recon, "get_warnings") else []

    return ReconciliationReportResponse(
        ok=True,
        last_reconcile_at=last_reconcile.isoformat() if last_reconcile else None,
        position_count=len(positions),
        sync_status=sync_status,
        discrepancies=discrepancies,
        warnings=warnings,
    )


# =============================================================================
# Events / Fills / Orders (ledger-backed)
# =============================================================================


def _read_ledger_entries(exec_router: ExecutionRouter) -> list[LedgerEntry]:
    """Read all ledger entries from the current run's ledger.jsonl."""
    ledger_path = exec_router.ledger._ledger_path
    if not ledger_path.exists():
        return []
    entries: list[LedgerEntry] = []
    with open(ledger_path) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                entries.append(LedgerEntry.model_validate_json(stripped))
    return entries


_ENTRY_TYPE_TO_EVENT_TYPE = {
    "intent": "INTENT",
    "submission": "SUBMIT",
    "ack": "FILL",
    "rejection": "REJECT",
}


@router.get("/events", response_model=EventsResponse)
async def get_events(
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    since: str | None = Query(default=None, description="ISO datetime lower bound"),
    limit: int = Query(default=100, ge=1, le=1000),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> EventsResponse:
    """
    Return execution events for chart markers.

    Reads from the current run's ledger.jsonl file.
    """
    entries = _read_ledger_entries(exec_router)

    # Parse since timestamp
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'since' datetime format")

    events: list[EventItem] = []
    for entry in entries:
        event_type = _ENTRY_TYPE_TO_EVENT_TYPE.get(entry.entry_type)
        if event_type is None:
            continue  # skip reconciliation, error, kill_switch etc.
        if symbol and entry.symbol != symbol:
            continue
        if since_dt and entry.timestamp < since_dt:
            continue

        meta = entry.metadata or {}
        events.append(EventItem(
            ts=entry.timestamp.isoformat(),
            type=event_type,
            side=entry.side.value if entry.side else None,
            price=meta.get("filled_price"),
            size=entry.size,
            reason=entry.error or (entry.reason_codes[0] if entry.reason_codes else None),
            order_id=str(entry.intent_id) if entry.intent_id else None,
            bot=meta.get("bot"),
        ))

    total = len(events)
    events = events[:limit]

    return EventsResponse(events=events, total=total)


@router.get("/fills", response_model=FillsResponse)
async def get_fills(
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    bot: str | None = Query(default=None, description="Filter by bot name"),
    side: str | None = Query(default=None, description="Filter by side (BUY/SELL)"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> FillsResponse:
    """
    Return fills for blotter display, sourced from ledger.jsonl ack entries.
    """
    entries = _read_ledger_entries(exec_router)

    fills: list[FillItem] = []
    for entry in entries:
        if entry.entry_type != "ack":
            continue
        # Only include filled entries
        if entry.status and entry.status.value != "FILLED":
            continue

        meta = entry.metadata or {}
        entry_side = entry.side.value if entry.side else None

        if symbol and entry.symbol != symbol:
            continue
        if bot and meta.get("bot") != bot:
            continue
        if side and entry_side != side.upper():
            continue

        fills.append(FillItem(
            ts=entry.timestamp.isoformat(),
            symbol=entry.symbol,
            side=entry_side,
            price=meta.get("filled_price"),
            size=meta.get("filled_size") or entry.size,
            pnl=meta.get("pnl"),
            bot=meta.get("bot"),
            order_id=str(entry.intent_id) if entry.intent_id else None,
            deal_id=entry.deal_id,
        ))

    total = len(fills)
    fills = fills[offset : offset + limit]

    return FillsResponse(fills=fills, total=total, limit=limit, offset=offset)


@router.get("/orders", response_model=OrdersResponse)
async def get_orders(
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> OrdersResponse:
    """
    Return orders for blotter display, sourced from ledger.jsonl.
    """
    entries = _read_ledger_entries(exec_router)

    orders: list[OrderItem] = []
    for entry in entries:
        if entry.entry_type not in ("intent", "submission", "ack"):
            continue
        if symbol and entry.symbol != symbol:
            continue
        if status and entry.status and entry.status.value != status.upper():
            continue
        if status and entry.status is None:
            continue

        meta = entry.metadata or {}
        orders.append(OrderItem(
            ts=entry.timestamp.isoformat(),
            symbol=entry.symbol,
            side=entry.side.value if entry.side else None,
            size=entry.size,
            status=entry.status.value if entry.status else entry.entry_type.upper(),
            order_type=meta.get("order_type"),
            bot=meta.get("bot"),
            intent_id=str(entry.intent_id) if entry.intent_id else None,
            deal_reference=entry.deal_reference,
        ))

    total = len(orders)
    orders = orders[offset : offset + limit]

    return OrdersResponse(orders=orders, total=total, limit=limit, offset=offset)


# =============================================================================
# Signals
# =============================================================================


@router.get("/signals", response_model=SignalsResponse)
async def get_signals(
    symbol: str | None = Query(default=None, description="Filter by symbol"),
    bot: str | None = Query(default=None, description="Filter by bot name"),
    timeframe: str | None = Query(default=None, description="Filter by timeframe"),
    direction: str | None = Query(default=None, description="Filter by direction (BUY/SELL)"),
    since: str | None = Query(default=None, description="ISO datetime lower bound"),
    limit: int = Query(default=100, ge=1, le=1000),
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> SignalsResponse:
    """
    Return strategy signals (intents) for the terminal signals panel.

    Reads from the current run's ledger.jsonl — intent entries
    represent strategy signals before order processing.
    """
    entries = _read_ledger_entries(exec_router)

    # Parse since timestamp
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'since' datetime format")

    signals: list[SignalItem] = []
    for entry in entries:
        if entry.entry_type != "intent":
            continue

        meta = entry.metadata or {}
        entry_side = entry.side.value if entry.side else None
        entry_bot = meta.get("bot")
        entry_tf = meta.get("timeframe")
        entry_source = meta.get("source")

        if symbol and entry.symbol != symbol:
            continue
        if bot and entry_bot != bot:
            continue
        if timeframe and entry_tf != timeframe:
            continue
        if direction and entry_side != direction.upper():
            continue
        if since_dt and entry.timestamp < since_dt:
            continue

        signals.append(SignalItem(
            ts=entry.timestamp.isoformat(),
            symbol=entry.symbol,
            bot=entry_bot,
            timeframe=entry_tf,
            side=entry_side,
            size=entry.size,
            confidence=meta.get("confidence"),
            stop_loss=meta.get("stop_loss"),
            take_profit=meta.get("take_profit"),
            reason_codes=entry.reason_codes,
            source=entry_source,
            intent_id=str(entry.intent_id) if entry.intent_id else None,
        ))

    total = len(signals)
    signals = signals[:limit]

    return SignalsResponse(signals=signals, total=total, limit=limit)


# =============================================================================
# Mode Flags
# =============================================================================


@router.get("/mode", response_model=ModeGetResponse)
async def get_mode(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ModeGetResponse:
    """Get current execution mode flags."""
    state = exec_router.state
    return ModeGetResponse(
        signals_enabled=state.signals_enabled,
        demo_arm_enabled=state.demo_arm_enabled,
        mode=state.mode.value,
    )


@router.post("/mode", response_model=ModeSetResponse)
async def set_mode(
    request: ModeSetRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> ModeSetResponse:
    """
    Set execution mode flags.

    - signals_enabled: toggle strategy signal generation
    - demo_arm_enabled: toggle DEMO order submission capability
    """
    if request.signals_enabled is not None:
        await exec_router.set_signals_enabled(request.signals_enabled)
    if request.demo_arm_enabled is not None:
        await exec_router.set_demo_arm_enabled(request.demo_arm_enabled)

    state = exec_router.state
    return ModeSetResponse(
        ok=True,
        signals_enabled=state.signals_enabled,
        demo_arm_enabled=state.demo_arm_enabled,
        mode=state.mode.value,
    )


# =============================================================================
# Symbol Allowlist
# =============================================================================


@router.post("/allowlist", response_model=AllowlistSetResponse)
async def set_allowlist(
    request: AllowlistSetRequest,
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> AllowlistSetResponse:
    """
    Set the symbol allowlist for this session.

    An empty list clears the allowlist (allows all symbols).
    """
    if request.symbols:
        exec_router._symbol_allowlist = set(s.upper() for s in request.symbols)
    else:
        exec_router._symbol_allowlist = None

    count = len(exec_router._symbol_allowlist) if exec_router._symbol_allowlist else 0
    return AllowlistSetResponse(ok=True, count=count)


@router.get("/allowlist", response_model=AllowlistGetResponse)
async def get_allowlist(
    exec_router: ExecutionRouter = Depends(get_execution_router),
) -> AllowlistGetResponse:
    """Get the current symbol allowlist."""
    if exec_router._symbol_allowlist is not None:
        return AllowlistGetResponse(
            symbols=sorted(exec_router._symbol_allowlist),
            active=True,
        )
    return AllowlistGetResponse(symbols=[], active=False)


# =============================================================================
# Reset for testing
# =============================================================================


def reset_execution_state() -> None:
    """Reset execution state (for testing)."""
    global _execution_router, _ig_client
    _execution_router = None
    _ig_client = None
