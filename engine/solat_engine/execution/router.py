"""
Execution Router.

Converts strategy signals to order intents, validates through risk engine,
and submits to broker when armed.

LIVE Trading Safety:
- All LIVE orders must pass TradingGates evaluation
- UI confirmation required for LIVE mode with TTL
- Account must be verified and locked
- Pre-live check must pass before arming
"""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from solat_engine.config import Settings, TradingMode, get_settings
from solat_engine.catalog.store import CatalogueStore
from solat_engine.execution.gates import GateMode, get_trading_gates
from solat_engine.execution.kill_switch import KillSwitch
from solat_engine.execution.ledger import ExecutionLedger
from solat_engine.execution.models import (
    ExecutionConfig,
    ExecutionMode,
    ExecutionState,
    OrderAck,
    OrderIntent,
    OrderSide,
    OrderStatus,
    PositionView,
)
from solat_engine.execution.reconciliation import PositionStore, ReconciliationService
from solat_engine.execution.risk_engine import RiskEngine
from solat_engine.execution.safety import ExecutionSafetyGuard, SafetyConfig
from solat_engine.logging import get_logger
from solat_engine.runtime.event_bus import Event, EventType, get_event_bus

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class ExecutionRouter:
    """
    Central execution router for live trading.

    Responsibilities:
    - Convert strategy signals to order intents
    - Validate intents through risk engine
    - Submit orders to broker (when armed)
    - Track execution state
    - Emit WS events for all execution lifecycle events
    """

    def __init__(
        self,
        config: ExecutionConfig,
        data_dir: Any,
    ):
        """
        Initialize execution router.

        Args:
            config: Execution configuration
            data_dir: Base directory for execution data
        """
        self._config = config
        self._data_dir = data_dir

        # Initialize components
        self._risk_engine = RiskEngine(config)
        self._kill_switch = KillSwitch(config)
        self._catalogue_store = CatalogueStore()

        # Restore kill switch state from disk (if exists)
        kill_switch_state_file = data_dir / "execution" / "kill_switch_state.json"
        self._kill_switch.restore_state(kill_switch_state_file)

        self._position_store = PositionStore()

        # Safety guard (idempotency, circuit breaker, size caps)
        is_demo = config.mode == ExecutionMode.DEMO
        self._safety_guard = ExecutionSafetyGuard(
            config=SafetyConfig(),
            is_demo=is_demo,
        )

        # Initialize ledger
        self._ledger = ExecutionLedger(data_dir, config)
        self._reconciliation = ReconciliationService(
            config,
            self._position_store,
            self._ledger,
        )
        self._reconciliation.set_event_callback(self._emit_event)

        # State
        self._state = ExecutionState(mode=config.mode)
        self._broker_adapter: Any = None
        self._pending_orders: dict[str, OrderIntent] = {}  # deal_ref -> intent

        # Symbol allowlist (None = all symbols allowed)
        self._symbol_allowlist: set[str] | None = None

        # Daily stats
        self._realized_pnl_today: float = 0.0
        self._account_balance: float = 0.0
        self._balance_last_updated: datetime | None = None
        self._fills_since_balance_refresh: int = 0

    @property
    def state(self) -> ExecutionState:
        """Get current execution state."""
        return self._state

    @property
    def position_store(self) -> PositionStore:
        """Get position store."""
        return self._position_store

    @property
    def risk_engine(self) -> RiskEngine:
        """Get risk engine."""
        return self._risk_engine

    @property
    def kill_switch(self) -> KillSwitch:
        """Get kill switch."""
        return self._kill_switch

    @property
    def ledger(self) -> ExecutionLedger:
        """Get execution ledger."""
        return self._ledger

    @property
    def reconciliation(self) -> ReconciliationService:
        """Get reconciliation service."""
        return self._reconciliation

    @property
    def safety_guard(self) -> ExecutionSafetyGuard:
        """Get execution safety guard."""
        return self._safety_guard

    async def connect(
        self,
        broker_adapter: Any,
        settings: Settings | None = None,
    ) -> dict[str, Any]:
        """
        Connect to broker.

        Args:
            broker_adapter: Broker adapter instance
            settings: Optional settings override (for testing)

        Returns:
            Connection result with account info
        """
        if self._state.connected:
            return {"ok": False, "error": "Already connected"}

        try:
            self._broker_adapter = broker_adapter

            # Get account info
            accounts = await broker_adapter.list_accounts()
            if not accounts:
                return {"ok": False, "error": "No accounts found"}

            account = accounts[0]
            self._state.account_id = account.get("accountId", account.get("account_id"))
            
            # Sync catalogue metadata to risk engine
            for item in self._catalogue_store.load():
                self._risk_engine.set_symbol_metadata(
                    item.symbol,
                    lot_size=float(item.lot_size) if item.lot_size else 1.0,
                    margin_factor=float(item.margin_factor) if item.margin_factor else 100.0
                )
                if item.dealing_rules:
                    self._risk_engine.set_dealing_rules(
                        item.symbol,
                        min_size=float(item.dealing_rules.min_deal_size) if item.dealing_rules.min_deal_size else 0.01,
                        max_size=float(item.dealing_rules.max_deal_size) if item.dealing_rules.max_deal_size else 1000.0,
                        size_step=float(item.dealing_rules.min_size_increment) if item.dealing_rules.min_size_increment else 0.01
                    )

            self._state.account_balance = float(account.get("balance", {}).get("balance", 0))
            self._account_balance = self._state.account_balance
            self._balance_last_updated = datetime.now(UTC)

            # Update state
            self._state.connected = True
            self._state.session_start = datetime.now(UTC)
            self._state.last_error = None

            # Verify account for LIVE mode if configured
            settings = settings or get_settings()

            if settings.mode == TradingMode.LIVE or settings.live_trading_enabled:
                gates = get_trading_gates()

                # Get detailed account info for verification
                try:
                    if hasattr(broker_adapter, "verify_account_for_live"):
                        account_info = await broker_adapter.verify_account_for_live(
                            settings.live_account_id
                        )
                        if account_info.get("verified"):
                            gates.set_account_verification(
                                account_id=account_info.get("account_id", self._state.account_id),
                                account_type=account_info.get("account_type", "CFD"),
                                currency=account_info.get("currency", "USD"),
                                balance=account_info.get("balance", self._account_balance),
                                available=account_info.get("available", self._account_balance),
                                is_live=account_info.get("is_live", False),
                            )
                            logger.info(
                                "Account verified for LIVE: %s (is_live=%s)",
                                self._state.account_id,
                                account_info.get("is_live"),
                            )
                except Exception as e:
                    logger.warning("Account verification failed (non-fatal): %s", e)

            # Start reconciliation
            await self._reconciliation.start(broker_adapter)

            # Emit event
            await self._emit_event({
                "type": "execution_status",
                "connected": True,
                "account_id": self._state.account_id,
                "mode": self._config.mode.value,
            })

            logger.info(
                "Connected to broker: account=%s, balance=%s",
                self._state.account_id,
                self._state.account_balance,
            )

            return {
                "ok": True,
                "account_id": self._state.account_id,
                "balance": self._state.account_balance,
                "mode": self._config.mode.value,
            }

        except Exception as e:
            self._state.last_error = str(e)
            self._state.last_error_ts = datetime.now(UTC)
            logger.error("Connection failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def disconnect(self) -> dict[str, Any]:
        """Disconnect from broker."""
        if not self._state.connected:
            return {"ok": True, "message": "Not connected"}

        # Stop reconciliation
        await self._reconciliation.stop()

        # Disarm if armed
        if self._state.armed:
            await self.disarm()

        # Finalize ledger
        self._ledger.finalize()

        # Clear state
        self._state.connected = False
        self._state.account_id = None
        self._state.session_start = None
        self._broker_adapter = None

        await self._emit_event({
            "type": "execution_status",
            "connected": False,
        })

        logger.info("Disconnected from broker")
        return {"ok": True}

    async def _refresh_account_balance(self) -> None:
        """
        Refresh account balance from broker.

        Called periodically to keep balance up-to-date:
        - After every N fills
        - Before risk checks if balance is stale (> 5 minutes)
        """
        if self._broker_adapter is None:
            logger.warning("Cannot refresh balance: not connected to broker")
            return

        try:
            accounts = await self._broker_adapter.list_accounts()
            if accounts:
                balance = float(accounts[0].get("balance", {}).get("balance", 0))
                old_balance = self._account_balance

                self._account_balance = balance
                self._state.account_balance = balance
                self._balance_last_updated = datetime.now(UTC)
                self._fills_since_balance_refresh = 0

                if abs(balance - old_balance) > 0.01:  # Log only if changed
                    logger.info(
                        "Account balance refreshed: %.2f -> %.2f (delta: %.2f)",
                        old_balance,
                        balance,
                        balance - old_balance,
                    )
                else:
                    logger.debug("Account balance refreshed: %.2f (no change)", balance)

        except Exception as e:
            logger.warning("Failed to refresh account balance: %s", e)

    async def arm(self, confirm: bool = False, live_mode: bool = False) -> dict[str, Any]:
        """
        Arm execution (enable order submission).

        Args:
            confirm: Must be True to arm
            live_mode: If True, attempt to arm in LIVE mode (requires all gates)

        Returns:
            Arm result
        """
        if not self._state.connected:
            return {"ok": False, "error": "Not connected"}

        if self._config.require_arm_confirmation and not confirm:
            return {"ok": False, "error": "Confirmation required (confirm=true)"}

        if self._kill_switch.is_active:
            return {"ok": False, "error": "Kill switch is active"}

        # Determine requested mode
        requested_mode = GateMode.LIVE if live_mode else GateMode.DEMO

        # Check trading gates only for LIVE mode
        if live_mode:
            gates = get_trading_gates()
            gate_status = gates.evaluate(requested_mode)

            if not gate_status.allowed:
                logger.warning(
                    "LIVE arm rejected: %d blockers: %s",
                    len(gate_status.blockers),
                    ", ".join(gate_status.blockers[:3]),
                )
                return {
                    "ok": False,
                    "error": "LIVE trading gates not satisfied",
                    "blockers": gate_status.blockers,
                    "warnings": gate_status.warnings,
                }

        # For LIVE mode, verify we're configured for LIVE
        if live_mode:
            if self._config.mode != ExecutionMode.LIVE:
                return {"ok": False, "error": "Config mode is not LIVE"}

            # Update state to reflect LIVE
            self._state.mode = ExecutionMode.LIVE
            logger.warning("ARMING IN LIVE MODE - REAL MONEY AT RISK")
        else:
            # DEMO mode is always allowed
            self._state.mode = ExecutionMode.DEMO

        self._state.armed = True

        await self._emit_event({
            "type": "execution_status",
            "armed": True,
            "mode": self._state.mode.value,
            "live": live_mode,
        })

        logger.warning("Execution ARMED (mode=%s)", self._state.mode.value)
        return {
            "ok": True,
            "armed": True,
            "mode": self._state.mode.value,
            "live": live_mode,
        }

    async def disarm(self) -> dict[str, Any]:
        """
        Disarm execution (disable order submission).

        Also revokes LIVE confirmation for safety.
        """
        was_live = self._state.mode == ExecutionMode.LIVE
        self._state.armed = False

        # Revoke LIVE confirmation for safety
        if was_live:
            gates = get_trading_gates()
            gates.revoke_ui_confirmation()
            self._state.mode = ExecutionMode.DEMO
            logger.warning("LIVE mode disarmed - confirmation revoked")

        await self._emit_event({
            "type": "execution_status",
            "armed": False,
            "mode": self._state.mode.value,
        })

        logger.info("Execution DISARMED")
        return {"ok": True, "armed": False, "mode": self._state.mode.value}

    async def activate_kill_switch(
        self,
        reason: str = "manual",
    ) -> dict[str, Any]:
        """Activate kill switch."""
        result = self._kill_switch.activate(reason=reason, activated_by="user")

        if result.get("ok"):
            self._state.kill_switch_active = True
            self._state.armed = False

            # Record in ledger
            self._ledger.record_kill_switch(activated=True, reason=reason, by="user")

            # Persist kill switch state to disk
            kill_switch_state_file = self._data_dir / "execution" / "kill_switch_state.json"
            self._kill_switch.save_state(kill_switch_state_file)

            await self._emit_event({
                "type": "kill_switch_activated",
                "reason": reason,
            })

            # Close positions if configured
            if self._config.close_on_kill_switch and self._broker_adapter:
                positions = self._kill_switch.get_positions_to_close(
                    self._position_store.positions
                )
                
                logger.debug("KILL SWITCH: Found %d positions to close", len(positions))
                
                if positions:
                    logger.warning("KILL SWITCH: Commencing parallel liquidation of %d positions", len(positions))
                    
                    # Define a helper for retrying a single close
                    async def close_with_retry(pos: PositionView):
                        for attempt in range(3):
                            try:
                                await self.close_position(pos.deal_id)
                                return None  # Success
                            except Exception as e:
                                logger.error("Failed to close %s (attempt %d/3): %s", pos.deal_id, attempt+1, e)
                                if attempt < 2:
                                    await asyncio.sleep(0.5)
                        return pos.deal_id  # Failed after all retries

                    # Run all closures in parallel
                    results = await asyncio.gather(*[close_with_retry(p) for p in positions])
                    
                    failed_closes = [r for r in results if r is not None]

                    if failed_closes:
                        logger.critical(
                            "KILL SWITCH: %d/%d positions failed to close: %s",
                            len(failed_closes), len(positions), failed_closes,
                        )
                        await self._emit_event({
                            "type": "kill_switch_close_failed",
                            "failed_deal_ids": failed_closes,
                            "total_positions": len(positions),
                        })
                    else:
                        logger.info("KILL SWITCH: All positions liquidated successfully")

        return result

    async def reset_kill_switch(self) -> dict[str, Any]:
        """Reset kill switch."""
        result = self._kill_switch.reset(reset_by="user")

        if result.get("ok") and not self._kill_switch.is_active:
            self._state.kill_switch_active = False

            self._ledger.record_kill_switch(activated=False, reason="reset", by="user")

            # Persist kill switch state to disk (inactive)
            kill_switch_state_file = self._data_dir / "execution" / "kill_switch_state.json"
            self._kill_switch.save_state(kill_switch_state_file)

            await self._emit_event({
                "type": "kill_switch_reset",
            })

        return result

    async def route_intent(self, intent: OrderIntent) -> OrderAck:
        """
        Route an order intent through validation and submission.

        Args:
            intent: Order intent to route

        Returns:
            OrderAck with result
        """
        # Check trading gates for LIVE mode
        if self._state.mode == ExecutionMode.LIVE:
            gates = get_trading_gates()
            gate_status = gates.evaluate(GateMode.LIVE)

            if not gate_status.allowed:
                logger.warning(
                    "LIVE order blocked by gates: %s",
                    ", ".join(gate_status.blockers[:2]),
                )
                await self._emit_event({
                    "type": "execution_blocked",
                    "intent_id": str(intent.intent_id),
                    "reason": "LIVE gates not satisfied",
                    "blockers": gate_status.blockers,
                })
                return OrderAck(
                    intent_id=intent.intent_id,
                    status=OrderStatus.REJECTED,
                    rejection_reason=f"LIVE blocked: {gate_status.blockers[0] if gate_status.blockers else 'unknown'}",
                )

        # Safety checks (idempotency, circuit breaker, size caps)
        safety_ok, safety_error = self._safety_guard.pre_order_check(
            intent.intent_id,
            intent.size,
        )
        if not safety_ok:
            logger.warning("Safety check failed for %s: %s", intent.intent_id, safety_error)
            await self._emit_event({
                "type": "execution_order_rejected",
                "intent_id": str(intent.intent_id),
                "reason": safety_error,
            })
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.REJECTED,
                rejection_reason=safety_error,
            )

        # Cap size in DEMO mode
        intent.size = self._safety_guard.cap_size(intent.size)

        # Check symbol allowlist
        if self._symbol_allowlist is not None and intent.symbol not in self._symbol_allowlist:
            self._ledger.record_rejection(
                intent,
                "SYMBOL_NOT_ALLOWLISTED",
                ["symbol_not_allowlisted"],
            )
            await self._emit_event({
                "type": "execution_order_rejected",
                "intent_id": str(intent.intent_id),
                "reason": "SYMBOL_NOT_ALLOWLISTED",
            })
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.REJECTED,
                rejection_reason="SYMBOL_NOT_ALLOWLISTED",
            )

        # Record intent in ledger
        self._ledger.record_intent(intent)

        await self._emit_event({
            "type": "execution_intent_created",
            "intent_id": str(intent.intent_id),
            "symbol": intent.symbol,
            "side": intent.side.value,
            "size": intent.size,
            "bot": intent.bot,
        })

        # Check kill switch
        can_trade, kill_reason = self._kill_switch.check_can_trade()
        if not can_trade:
            self._ledger.record_rejection(
                intent,
                kill_reason or "Kill switch active",
                ["kill_switch_active"],
            )
            await self._emit_event({
                "type": "execution_order_rejected",
                "intent_id": str(intent.intent_id),
                "reason": "kill_switch_active",
            })
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.REJECTED,
                rejection_reason=kill_reason,
            )

        # Check if balance is stale (> 5 minutes) and refresh if needed
        if self._balance_last_updated is not None:
            balance_age_seconds = (datetime.now(UTC) - self._balance_last_updated).total_seconds()
            if balance_age_seconds > 300:  # 5 minutes
                logger.warning(
                    "Account balance is stale (%.0f seconds old), refreshing before risk check",
                    balance_age_seconds,
                )
                await self._refresh_account_balance()

        # Validate through risk engine
        risk_result = self._risk_engine.check_intent(
            intent,
            self._position_store.positions,
            self._account_balance,
            self._realized_pnl_today,
        )

        if not risk_result.allowed:
            self._ledger.record_rejection(
                intent,
                risk_result.rejection_reason or "Risk check failed",
                risk_result.reason_codes,
            )
            await self._emit_event({
                "type": "execution_order_rejected",
                "intent_id": str(intent.intent_id),
                "reason": risk_result.rejection_reason,
                "reason_codes": risk_result.reason_codes,
            })
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.REJECTED,
                rejection_reason=risk_result.rejection_reason,
            )

        # Update size if adjusted
        if risk_result.adjusted_size != intent.size:
            intent.size = risk_result.adjusted_size
            logger.debug(
                "Size adjusted: %s -> %s",
                risk_result.original_size,
                risk_result.adjusted_size,
            )

        # DEMO mode: require demo_arm_enabled for order submission
        if self._state.mode == ExecutionMode.DEMO and not self._state.demo_arm_enabled:
            logger.debug("DEMO arm not enabled, intent recorded but not submitted")
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.PENDING,
                rejection_reason="DEMO arm not enabled - intent recorded only",
            )

        # Check if armed and connected
        if not self._state.armed:
            logger.debug("Not armed, intent recorded but not submitted")
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.PENDING,
                rejection_reason="Not armed - intent recorded only",
            )

        if not self._state.connected or not self._broker_adapter:
            return OrderAck(
                intent_id=intent.intent_id,
                status=OrderStatus.REJECTED,
                rejection_reason="Not connected to broker",
            )

        # Submit to broker
        return await self._submit_to_broker(intent)

    async def _submit_to_broker(self, intent: OrderIntent) -> OrderAck:
        """Submit order to broker."""
        # Generate deal reference for idempotency
        deal_reference = f"SOLAT_{intent.intent_id.hex[:8]}_{datetime.now(UTC).strftime('%H%M%S')}"

        # Record submission
        self._ledger.record_submission(intent, deal_reference)
        self._pending_orders[deal_reference] = intent

        await self._emit_event({
            "type": "execution_order_submitted",
            "intent_id": str(intent.intent_id),
            "deal_reference": deal_reference,
        })

        try:
            # Convert side to IG direction
            direction = "BUY" if intent.side == OrderSide.BUY else "SELL"

            # Place order
            result = await self._broker_adapter.place_market_order(
                epic=intent.epic or self._resolve_epic(intent.symbol),
                direction=direction,
                size=intent.size,
                stop_level=intent.stop_loss,
                limit_level=intent.take_profit,
                deal_reference=deal_reference,
            )

            # Extract deal ID
            deal_id = result.get("dealId") or result.get("deal_id")
            status_str = result.get("dealStatus", "ACCEPTED")

            if status_str == "ACCEPTED":
                status = OrderStatus.FILLED
            elif status_str == "REJECTED":
                status = OrderStatus.REJECTED
            else:
                status = OrderStatus.ACKNOWLEDGED

            # Record trade for rate limiting
            if status == OrderStatus.FILLED:
                self._risk_engine.record_trade()
                self._state.trades_this_hour = self._risk_engine.get_trades_this_hour()
                # Record success with safety guard
                self._safety_guard.record_order_success(intent.intent_id, result)

                # Update fill counter and refresh balance if threshold reached
                self._fills_since_balance_refresh += 1
                if self._fills_since_balance_refresh >= 10:
                    # Refresh balance from broker every 10 fills
                    await self._refresh_account_balance()

            ack = OrderAck(
                intent_id=intent.intent_id,
                deal_reference=deal_reference,
                deal_id=deal_id,
                status=status,
                filled_size=intent.size if status == OrderStatus.FILLED else None,
                raw_response=self._redact_response(result),
            )

            self._ledger.record_ack(ack)

            await self._emit_event({
                "type": "execution_order_acknowledged",
                "intent_id": str(intent.intent_id),
                "deal_reference": deal_reference,
                "deal_id": deal_id,
                "status": status.value,
            })

            return ack

        except Exception as e:
            logger.error("Order submission failed: %s", e)
            self._ledger.record_error(
                str(e),
                intent_id=intent.intent_id,
                deal_reference=deal_reference,
            )

            # Record error with circuit breaker
            tripped = self._safety_guard.record_order_error(str(e))
            if tripped:
                logger.error("Circuit breaker tripped after order error")
                await self._emit_event({
                    "type": "circuit_breaker_tripped",
                    "reason": str(e),
                })

            await self._emit_event({
                "type": "execution_order_rejected",
                "intent_id": str(intent.intent_id),
                "reason": str(e),
            })

            return OrderAck(
                intent_id=intent.intent_id,
                deal_reference=deal_reference,
                status=OrderStatus.REJECTED,
                rejection_reason=str(e),
            )

        finally:
            # Remove from pending
            self._pending_orders.pop(deal_reference, None)

    async def close_position(
        self,
        deal_id: str,
        size: float | None = None,
    ) -> dict[str, Any]:
        """
        Close a position.

        Args:
            deal_id: Position deal ID
            size: Optional size to close (full position if None)

        Returns:
            Close result
        """
        if not self._state.connected or not self._broker_adapter:
            return {"ok": False, "error": "Not connected"}

        # Get position
        position = self._position_store.get_position(deal_id)
        if not position:
            return {"ok": False, "error": f"Position {deal_id} not found"}

        # Determine close direction (opposite of position)
        close_direction = "SELL" if position.direction == OrderSide.BUY else "BUY"

        try:
            result = await self._broker_adapter.close_position(
                deal_id=deal_id,
                direction=close_direction,
                size=size or position.size,
            )

            logger.info("Position closed: %s", deal_id)
            return {"ok": True, "result": result}

        except Exception as e:
            logger.error("Failed to close position %s: %s", deal_id, e)
            return {"ok": False, "error": str(e)}

    def _resolve_epic(self, symbol: str) -> str:
        """Resolve symbol to IG epic using catalogue."""
        item = self._catalogue_store.get(symbol)
        if item and item.epic:
            return item.epic

        # Fallback to pattern-based resolution if not in catalogue
        suffix = "TODAY.IP" if self._state.mode == ExecutionMode.LIVE else "MINI.IP"
        return f"CS.D.{symbol}.{suffix}"

    def _redact_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive data from broker response."""
        redacted = {}
        safe_keys = {"dealId", "dealReference", "dealStatus", "reason", "status", "affectedDeals"}
        for key, value in response.items():
            if key in safe_keys:
                redacted[key] = value
        return redacted

    async def _emit_event(self, data: dict[str, Any]) -> None:
        """Emit WS event."""
        try:
            bus = get_event_bus()
            event = Event(
                type=EventType.EXECUTION_STATUS,
                data={
                    "ts": datetime.now(UTC).isoformat(),
                    **data,
                },
            )
            await bus.publish(event)
        except Exception as e:
            logger.debug("Failed to emit event: %s", e)

    def get_positions(self) -> list[PositionView]:
        """Get current positions."""
        return self._position_store.positions

    async def set_signals_enabled(self, enabled: bool) -> None:
        """Toggle signal generation on/off."""
        self._state.signals_enabled = enabled
        await self._emit_event({
            "type": "execution_mode_changed",
            "signals_enabled": enabled,
        })
        logger.info("Signals %s", "enabled" if enabled else "disabled")

    async def set_demo_arm_enabled(self, enabled: bool) -> None:
        """Toggle DEMO arm on/off."""
        self._state.demo_arm_enabled = enabled
        await self._emit_event({
            "type": "execution_mode_changed",
            "demo_arm_enabled": enabled,
        })
        logger.info("DEMO arm %s", "enabled" if enabled else "disabled")

    def update_config(self, config: ExecutionConfig) -> None:
        """Update configuration."""
        self._config = config
        self._risk_engine.update_config(config)
        self._kill_switch.update_config(config)
        self._reconciliation.update_config(config)
