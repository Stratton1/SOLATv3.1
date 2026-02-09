"""
SOLAT Trading Engine - FastAPI Application

Main entry point for the Python sidecar process.
Provides REST API and WebSocket endpoints for the desktop terminal.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from solat_engine import __version__
from solat_engine.api.backtest_routes import router as backtest_router
from solat_engine.api.catalog_routes import router as catalog_router
from solat_engine.api.chart_routes import router as chart_router
from solat_engine.api.data_routes import router as data_router
from solat_engine.api.diagnostics_routes import router as diagnostics_router
from solat_engine.api.diagnostics_routes import set_ws_clients_ref
from solat_engine.api.execution_routes import router as execution_router
from solat_engine.api.ig_routes import router as ig_router
from solat_engine.api.market_data_routes import router as market_data_router
from solat_engine.api.optimization_routes import router as optimization_router
from solat_engine.config import Settings, get_settings, get_settings_dep
from solat_engine.logging import get_logger, setup_logging
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus
from solat_engine.runtime.ws_throttle import ExecutionEventCompressor

# Setup logging
setup_logging(level=get_settings().log_level)
logger = get_logger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    time: str
    uptime_seconds: float


class LiveHealthResponse(BaseModel):
    """Comprehensive health check for LIVE monitoring."""

    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    time: str
    uptime_seconds: float
    checks: dict[str, Any] = {}


class ConfigResponse(BaseModel):
    """Configuration response (redacted)."""

    mode: str
    env: str
    data_dir: str
    app_env: str
    ig_configured: bool


class HeartbeatMessage(BaseModel):
    """WebSocket heartbeat message."""

    type: str = "heartbeat"
    count: int
    timestamp: str


# =============================================================================
# Application State
# =============================================================================


class AppState:
    """Application state container."""

    def __init__(self) -> None:
        self.start_time: datetime = datetime.now(UTC)
        self.heartbeat_count: int = 0
        self.websocket_clients: list[WebSocket] = []
        self.heartbeat_task: asyncio.Task | None = None
        # Execution event compressor to reduce WS noise
        self.execution_compressor = ExecutionEventCompressor(dedup_window_s=2.0)


state = AppState()


# =============================================================================
# Lifecycle
# =============================================================================


async def heartbeat_loop() -> None:
    """Background task that sends heartbeats to all connected WebSocket clients."""
    while True:
        await asyncio.sleep(1)
        state.heartbeat_count += 1

        # Prepare heartbeat message
        message = HeartbeatMessage(
            count=state.heartbeat_count,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Send to all connected clients
        disconnected: list[WebSocket] = []
        for ws in state.websocket_clients:
            try:
                await ws.send_json(message.model_dump())
            except Exception:
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            state.websocket_clients.remove(ws)

        # Publish event to internal bus
        event_bus = get_event_bus()
        await event_bus.publish(
            Event(
                type=EventType.HEARTBEAT,
                data={"count": state.heartbeat_count},
            )
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    # Startup
    logger.info(
        "Starting SOLAT Engine v%s in %s mode",
        __version__,
        settings.mode.value,
    )
    logger.info("Data directory: %s", settings.data_dir)
    logger.info("Server: http://%s:%d", settings.host, settings.port)

    # Start heartbeat task
    state.heartbeat_task = asyncio.create_task(heartbeat_loop())

    # Set WS clients reference for diagnostics
    set_ws_clients_ref(state.websocket_clients)

    # Publish startup event
    event_bus = get_event_bus()
    await event_bus.publish(Event(type=EventType.ENGINE_STARTED))

    # Subscribe to sync progress events for WS forwarding
    async def forward_sync_events(event: Event) -> None:
        """Forward sync events to WebSocket clients."""
        if event.type in (
            EventType.SYNC_STARTED,
            EventType.SYNC_PROGRESS,
            EventType.SYNC_COMPLETED,
            EventType.SYNC_FAILED,
        ):
            message = {
                "type": event.type.value,
                "run_id": event.run_id,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            }
            disconnected: list[WebSocket] = []
            for ws in state.websocket_clients:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                if ws in state.websocket_clients:
                    state.websocket_clients.remove(ws)

    await event_bus.subscribe(EventType.SYNC_STARTED, forward_sync_events)
    await event_bus.subscribe(EventType.SYNC_PROGRESS, forward_sync_events)
    await event_bus.subscribe(EventType.SYNC_COMPLETED, forward_sync_events)
    await event_bus.subscribe(EventType.SYNC_FAILED, forward_sync_events)

    # Subscribe to backtest events for WS forwarding
    async def forward_backtest_events(event: Event) -> None:
        """Forward backtest events to WebSocket clients."""
        if event.type in (
            EventType.BACKTEST_STARTED,
            EventType.BACKTEST_PROGRESS,
            EventType.BACKTEST_COMPLETED,
        ):
            message = {
                "type": event.type.value,
                "run_id": event.run_id,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            }
            disconnected: list[WebSocket] = []
            for ws in state.websocket_clients:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                if ws in state.websocket_clients:
                    state.websocket_clients.remove(ws)

    await event_bus.subscribe(EventType.BACKTEST_STARTED, forward_backtest_events)
    await event_bus.subscribe(EventType.BACKTEST_PROGRESS, forward_backtest_events)
    await event_bus.subscribe(EventType.BACKTEST_COMPLETED, forward_backtest_events)

    # Subscribe to execution events for WS forwarding (with compression)
    async def forward_execution_events(event: Event) -> None:
        """Forward execution events to WebSocket clients with compression."""
        if event.type in (
            EventType.EXECUTION_STATUS,
            EventType.EXECUTION_INTENT_CREATED,
            EventType.EXECUTION_ORDER_SUBMITTED,
            EventType.EXECUTION_ORDER_REJECTED,
            EventType.EXECUTION_ORDER_ACKNOWLEDGED,
            EventType.EXECUTION_POSITIONS_UPDATED,
            EventType.EXECUTION_RECONCILIATION_WARNING,
            EventType.EXECUTION_KILL_SWITCH_ACTIVATED,
            EventType.EXECUTION_KILL_SWITCH_RESET,
        ):
            # Apply execution event compression to reduce WS noise
            if not state.execution_compressor.should_deliver(event):
                return  # Skip compressed/deduplicated events

            message = {
                "type": event.type.value,
                "run_id": event.run_id,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            }
            disconnected: list[WebSocket] = []
            for ws in state.websocket_clients:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                if ws in state.websocket_clients:
                    state.websocket_clients.remove(ws)

    await event_bus.subscribe(EventType.EXECUTION_STATUS, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_INTENT_CREATED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_ORDER_SUBMITTED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_ORDER_REJECTED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_ORDER_ACKNOWLEDGED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_POSITIONS_UPDATED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_RECONCILIATION_WARNING, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_KILL_SWITCH_ACTIVATED, forward_execution_events)
    await event_bus.subscribe(EventType.EXECUTION_KILL_SWITCH_RESET, forward_execution_events)

    # Subscribe to market data events for WS forwarding
    async def forward_market_data_events(event: Event) -> None:
        """Forward market data events to WebSocket clients."""
        if event.type in (
            EventType.QUOTE_RECEIVED,
            EventType.BAR_RECEIVED,
            EventType.BROKER_CONNECTED,
            EventType.BROKER_DISCONNECTED,
        ):
            message = {
                "type": event.type.value,
                "timestamp": event.timestamp.isoformat(),
                **event.data,
            }
            disconnected: list[WebSocket] = []
            for ws in state.websocket_clients:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                if ws in state.websocket_clients:
                    state.websocket_clients.remove(ws)

    await event_bus.subscribe(EventType.QUOTE_RECEIVED, forward_market_data_events)
    await event_bus.subscribe(EventType.BAR_RECEIVED, forward_market_data_events)
    await event_bus.subscribe(EventType.BROKER_CONNECTED, forward_market_data_events)
    await event_bus.subscribe(EventType.BROKER_DISCONNECTED, forward_market_data_events)

    yield

    # Shutdown
    logger.info("Shutting down SOLAT Engine")

    # Cancel heartbeat task
    if state.heartbeat_task:
        state.heartbeat_task.cancel()
        try:
            await state.heartbeat_task
        except asyncio.CancelledError:
            pass

    # Close all WebSocket connections
    for ws in state.websocket_clients:
        try:
            await ws.close()
        except Exception:
            pass

    # Publish shutdown event
    await event_bus.publish(Event(type=EventType.ENGINE_STOPPED))


# =============================================================================
# FastAPI Application
# =============================================================================


app = FastAPI(
    title="SOLAT Trading Engine",
    description="Algorithmic trading engine with IG broker integration",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware - only allow localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",  # Tauri dev server
        "http://127.0.0.1:1420",
        "tauri://localhost",  # Tauri production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(ig_router)
app.include_router(catalog_router)
app.include_router(data_router)
app.include_router(backtest_router)
app.include_router(execution_router)
app.include_router(market_data_router)
app.include_router(chart_router)
app.include_router(diagnostics_router)
app.include_router(optimization_router)


# =============================================================================
# REST Endpoints
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Health check endpoint.

    Returns current status, version, and uptime.
    """
    now = datetime.now(UTC)
    uptime = (now - state.start_time).total_seconds()

    return HealthResponse(
        status="healthy",
        version=__version__,
        time=now.isoformat(),
        uptime_seconds=round(uptime, 2),
    )


@app.get("/health/live", response_model=LiveHealthResponse)
async def health_live() -> LiveHealthResponse:
    """
    Comprehensive health check for LIVE monitoring.

    Checks all subsystems critical for LIVE trading:
    - Execution: connected, armed, kill switch, mode
    - Reconciliation: last reconcile age, drift status
    - Market data: feed staleness
    - Safety: circuit breaker state
    """
    now = datetime.now(UTC)
    uptime = (now - state.start_time).total_seconds()
    checks: dict[str, Any] = {}
    issues: list[str] = []

    # Execution router state
    from solat_engine.api.execution_routes import _execution_router

    if _execution_router is not None:
        es = _execution_router.state
        checks["execution"] = {
            "connected": es.connected,
            "armed": es.armed,
            "kill_switch_active": es.kill_switch_active,
            "mode": es.mode.value,
            "account_id": es.account_id,
        }
        if es.kill_switch_active:
            issues.append("kill_switch_active")
        if not es.connected:
            issues.append("broker_disconnected")

        # Reconciliation freshness
        recon = _execution_router.reconciliation
        last_recon = recon.last_reconcile_time
        if last_recon is not None:
            recon_age = (now - last_recon).total_seconds()
            checks["reconciliation"] = {
                "last_reconcile_age_s": round(recon_age, 1),
                "healthy": recon_age < 30,
            }
            if recon_age > 30:
                issues.append(f"reconciliation_stale_{recon_age:.0f}s")
        else:
            checks["reconciliation"] = {"last_reconcile_age_s": None, "healthy": False}

        # Safety guard
        sg = _execution_router.safety_guard
        checks["safety"] = {
            "circuit_breaker_ok": not sg.circuit_breaker_tripped,
        }
        if sg.circuit_breaker_tripped:
            issues.append("circuit_breaker_tripped")
    else:
        checks["execution"] = {"connected": False, "armed": False}

    # Market data feed health
    from solat_engine.api.market_data_routes import _market_service

    if _market_service is not None and hasattr(_market_service, "get_status"):
        md_status = _market_service.get_status()
        checks["market_data"] = {
            "mode": md_status.get("mode", "unknown"),
            "subscriptions": md_status.get("subscription_count", 0),
            "stale": md_status.get("is_stale", False),
        }
        if md_status.get("is_stale"):
            issues.append("market_data_stale")
    else:
        checks["market_data"] = {"mode": "inactive", "subscriptions": 0}

    # Overall status
    if len(issues) == 0:
        status = "healthy"
    elif any(i in ("circuit_breaker_tripped", "kill_switch_active") for i in issues):
        status = "unhealthy"
    else:
        status = "degraded"

    if issues:
        checks["issues"] = issues

    return LiveHealthResponse(
        status=status,
        version=__version__,
        time=now.isoformat(),
        uptime_seconds=round(uptime, 2),
        checks=checks,
    )


@app.get("/config", response_model=ConfigResponse)
async def config(
    settings: Settings = Depends(get_settings_dep)
) -> ConfigResponse:
    """
    Get current configuration (redacted).

    Sensitive values are not exposed.
    """
    return ConfigResponse(
        mode=settings.mode.value,
        env=settings.env.value,
        data_dir=str(settings.data_dir),
        app_env=settings.env.value,
        ig_configured=settings.has_ig_credentials,
    )


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint with API info."""
    return {
        "name": "SOLAT Trading Engine",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# =============================================================================
# WebSocket Endpoint
# =============================================================================


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """
    WebSocket endpoint for real-time updates.

    Streams:
    - Heartbeat events (every 1s)
    - Market data (when subscribed)
    - Order updates (when trading)
    """
    await websocket.accept()
    state.websocket_clients.append(websocket)
    logger.info("WebSocket client connected. Total clients: %d", len(state.websocket_clients))

    try:
        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "version": __version__,
                "mode": settings.mode.value,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                # Handle client messages (subscription requests, etc.)
                await handle_ws_message(websocket, data)
            except WebSocketDisconnect:
                break

    finally:
        if websocket in state.websocket_clients:
            state.websocket_clients.remove(websocket)
        logger.info(
            "WebSocket client disconnected. Total clients: %d",
            len(state.websocket_clients),
        )


async def handle_ws_message(websocket: WebSocket, data: dict[str, Any]) -> None:
    """
    Handle incoming WebSocket messages.

    Args:
        websocket: WebSocket connection
        data: Message data
    """
    msg_type = data.get("type")

    if msg_type == "ping":
        await websocket.send_json(
            {
                "type": "pong",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    elif msg_type == "subscribe":
        # Future: Handle market data subscriptions
        channel = data.get("channel")
        logger.info("Subscription request for channel: %s", channel)
        await websocket.send_json(
            {
                "type": "subscribed",
                "channel": channel,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    else:
        logger.warning("Unknown WebSocket message type: %s", msg_type)


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Run the server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "solat_engine.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env.value == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
