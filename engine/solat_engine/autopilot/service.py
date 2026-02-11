"""
Autopilot Service — event-driven strategy execution loop.

Subscribes to BAR_RECEIVED events, matches bars to allowlist entries,
runs strategies, and routes signals through the execution router.

Safety:
- DEMO-only (LIVE fail-closed)
- All intents flow through ExecutionRouter (risk engine + kill switch)
- Rate limiting and per-combo cooldowns
- Bounded bar buffers
"""

import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from solat_engine.backtest.models import SignalIntent
from solat_engine.config import TradingMode, get_settings
from solat_engine.execution.models import OrderIntent, OrderSide
from solat_engine.execution.router import ExecutionRouter
from solat_engine.logging import get_logger
from solat_engine.optimization.allowlist import AllowlistManager
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus
from solat_engine.strategies.elite8_hardened import (
    BarData,
    Elite8StrategyFactory,
    StrategyContext,
)

logger = get_logger(__name__)


class AutopilotConfig(BaseModel):
    """Configuration for the autopilot service."""

    max_signals_per_minute: int = 10
    per_combo_cooldown_bars: int = 3
    default_size: float = 0.1
    warmup_bars: int = 100


class AutopilotState(BaseModel):
    """Current state of the autopilot service."""

    enabled: bool = False
    enabled_at: str | None = None
    combo_count: int = 0
    cycle_count: int = 0
    signals_generated: int = 0
    intents_routed: int = 0
    last_cycle_at: str | None = None
    blocked_reasons: list[str] = Field(default_factory=list)


class AutopilotService:
    """
    Event-driven autopilot that runs strategies on incoming bars.

    Subscribes to BAR_RECEIVED events from the event bus, matches each
    bar to allowlist entries, runs the corresponding strategy, and
    routes entry signals through the execution router.
    """

    def __init__(
        self,
        execution_router: ExecutionRouter | None = None,
        allowlist_mgr: AllowlistManager | None = None,
        config: AutopilotConfig | None = None,
        settings: Any = None,
    ):
        self._execution_router = execution_router
        self._allowlist_mgr = allowlist_mgr
        self._config = config or AutopilotConfig()
        self._settings = settings
        self._enabled = False
        self._enabled_at: datetime | None = None

        # Per-combo state: key = "symbol:bot:timeframe"
        self._bar_buffers: dict[str, deque[BarData]] = {}
        self._strategies: dict[str, Any] = {}
        self._cooldowns: dict[str, int] = {}  # combo_key -> bars_since_last_signal

        # Metrics
        self._cycle_count = 0
        self._signals_generated = 0
        self._intents_routed = 0
        self._last_cycle_at: datetime | None = None

        # Rate limiting: track signal timestamps
        self._signal_timestamps: list[float] = []
        self._max_errors = 50
        self._errors: list[str] = []

    async def enable(self) -> AutopilotState:
        """Enable autopilot (DEMO only)."""
        reasons = self._check_blockers()
        if reasons:
            state = self.get_state()
            state.blocked_reasons = reasons
            return state

        self._enabled = True
        self._enabled_at = datetime.now(UTC)

        # Subscribe to bar events
        event_bus = get_event_bus()
        await event_bus.subscribe(EventType.BAR_RECEIVED, self._on_bar_received)

        # Load combos from allowlist
        self._load_combos()

        # Emit event
        await event_bus.publish(Event(
            type=EventType.AUTOPILOT_ENABLED,
            data={"combo_count": len(self._bar_buffers)},
        ))

        logger.info(
            "Autopilot enabled: %d combos from allowlist",
            len(self._bar_buffers),
        )
        return self.get_state()

    async def disable(self) -> AutopilotState:
        """Disable autopilot."""
        self._enabled = False

        # Unsubscribe from bar events
        event_bus = get_event_bus()
        await event_bus.unsubscribe(EventType.BAR_RECEIVED, self._on_bar_received)

        await event_bus.publish(Event(
            type=EventType.AUTOPILOT_DISABLED,
            data={
                "cycles": self._cycle_count,
                "signals": self._signals_generated,
                "intents": self._intents_routed,
            },
        ))

        logger.info("Autopilot disabled")
        return self.get_state()

    def get_state(self) -> AutopilotState:
        """Get current autopilot state."""
        return AutopilotState(
            enabled=self._enabled,
            enabled_at=self._enabled_at.isoformat() if self._enabled_at else None,
            combo_count=len(self._bar_buffers),
            cycle_count=self._cycle_count,
            signals_generated=self._signals_generated,
            intents_routed=self._intents_routed,
            last_cycle_at=self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            blocked_reasons=self._check_blockers() if not self._enabled else [],
        )

    def get_combos(self) -> list[dict[str, Any]]:
        """Get active combos with buffer sizes."""
        combos = []
        for key, buf in self._bar_buffers.items():
            parts = key.split(":")
            if len(parts) == 3:
                combos.append({
                    "symbol": parts[0],
                    "bot": parts[1],
                    "timeframe": parts[2],
                    "buffer_size": len(buf),
                    "cooldown_remaining": max(
                        0,
                        self._config.per_combo_cooldown_bars
                        - self._cooldowns.get(key, self._config.per_combo_cooldown_bars),
                    ),
                })
        return combos

    def _check_blockers(self) -> list[str]:
        """Check reasons autopilot cannot be enabled."""
        reasons: list[str] = []
        settings = self._settings if self._settings is not None else get_settings()

        if settings.mode == TradingMode.LIVE:
            reasons.append("LIVE mode — autopilot is DEMO-only")

        if self._execution_router is None:
            reasons.append("No execution router configured")

        if self._allowlist_mgr is None:
            reasons.append("No allowlist manager configured")
        elif not self._allowlist_mgr.get_enabled():
            reasons.append("Allowlist is empty — no combos to run")

        if self._execution_router is not None:
            if not self._execution_router.state.armed:
                reasons.append("Execution engine is not armed")
            if self._execution_router.kill_switch.is_active:
                reasons.append("Kill switch is active")

        return reasons

    def _load_combos(self) -> None:
        """Load enabled allowlist entries into bar buffers and strategies."""
        if self._allowlist_mgr is None:
            return

        maxlen = self._config.warmup_bars + 50
        entries = self._allowlist_mgr.get_enabled()

        for entry in entries:
            key = f"{entry.symbol}:{entry.bot}:{entry.timeframe}"
            if key not in self._bar_buffers:
                self._bar_buffers[key] = deque(maxlen=maxlen)
                self._cooldowns[key] = self._config.per_combo_cooldown_bars
                try:
                    self._strategies[key] = Elite8StrategyFactory.create(
                        entry.bot,
                        warmup_bars=self._config.warmup_bars,
                    )
                except ValueError:
                    logger.warning("Unknown bot '%s', skipping combo %s", entry.bot, key)
                    del self._bar_buffers[key]
                    del self._cooldowns[key]

    async def _on_bar_received(self, event: Event) -> None:
        """Handle BAR_RECEIVED event — core autopilot loop."""
        if not self._enabled:
            return

        self._cycle_count += 1
        self._last_cycle_at = datetime.now(UTC)

        # Guard: kill switch check
        if self._execution_router is not None and self._execution_router.kill_switch.is_active:
            return

        # Guard: signals_enabled check
        if self._execution_router is not None and not self._execution_router.state.signals_enabled:
            return

        symbol = event.data.get("symbol", "")
        timeframe = event.data.get("timeframe", "")

        if not symbol or not timeframe:
            return

        # Build BarData from event
        try:
            bar = BarData(
                timestamp=event.data.get("timestamp", event.timestamp.isoformat()),
                open=float(event.data.get("open", 0)),
                high=float(event.data.get("high", 0)),
                low=float(event.data.get("low", 0)),
                close=float(event.data.get("close", 0)),
                volume=float(event.data.get("volume", 0)),
            )
        except (KeyError, TypeError, ValueError) as e:
            self._record_error(f"Bad bar data: {e}")
            return

        # Match to all combos for this symbol+timeframe
        for key, buf in self._bar_buffers.items():
            parts = key.split(":")
            if len(parts) != 3:
                continue
            combo_symbol, combo_bot, combo_tf = parts

            if combo_symbol != symbol or combo_tf != timeframe:
                continue

            # Append bar to buffer
            buf.append(bar)

            # Increment cooldown counter
            self._cooldowns[key] = self._cooldowns.get(key, 0) + 1

            # Check cooldown
            if self._cooldowns[key] < self._config.per_combo_cooldown_bars:
                continue

            # Check rate limit
            if not self._check_rate_limit():
                continue

            # Run strategy
            strategy = self._strategies.get(key)
            if strategy is None:
                continue

            try:
                context = StrategyContext(
                    symbol=combo_symbol,
                    timeframe=combo_tf,
                    bot_name=combo_bot,
                )
                signal: SignalIntent = strategy.generate_signal(
                    list(buf),
                    current_position=None,
                    context=context,
                )
            except Exception as e:
                self._record_error(f"Strategy error {key}: {e}")
                continue

            if not signal.is_entry:
                continue

            self._signals_generated += 1
            self._cooldowns[key] = 0  # Reset cooldown

            # Convert to OrderIntent and route
            try:
                side = OrderSide.BUY if signal.is_buy else OrderSide.SELL
                intent = OrderIntent(
                    symbol=combo_symbol,
                    side=side,
                    size=self._config.default_size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    bot=combo_bot,
                    reason_codes=signal.reason_codes,
                    confidence=signal.confidence,
                    metadata={"source": "autopilot", "timeframe": combo_tf},
                )

                if self._execution_router is not None:
                    await self._execution_router.route_intent(intent)
                    self._intents_routed += 1

                # Emit signal event
                event_bus = get_event_bus()
                await event_bus.publish(Event(
                    type=EventType.AUTOPILOT_SIGNAL,
                    data={
                        "symbol": combo_symbol,
                        "bot": combo_bot,
                        "timeframe": combo_tf,
                        "direction": signal.direction,
                    },
                ))

            except Exception as e:
                self._record_error(f"Route error {key}: {e}")

    def _check_rate_limit(self) -> bool:
        """Check if within signals-per-minute rate limit."""
        now = time.monotonic()
        cutoff = now - 60
        self._signal_timestamps = [t for t in self._signal_timestamps if t > cutoff]
        if len(self._signal_timestamps) >= self._config.max_signals_per_minute:
            return False
        self._signal_timestamps.append(now)
        return True

    def _record_error(self, msg: str) -> None:
        """Record error with bounded list."""
        if len(self._errors) >= self._max_errors:
            self._errors.pop(0)
        self._errors.append(msg)
        logger.warning("Autopilot: %s", msg)


# Module-level singleton
_autopilot_service: AutopilotService | None = None


def get_autopilot_service() -> AutopilotService | None:
    """Get the global autopilot service."""
    return _autopilot_service


def set_autopilot_service(svc: AutopilotService | None) -> None:
    """Set the global autopilot service (called from main.py lifespan)."""
    global _autopilot_service
    _autopilot_service = svc
