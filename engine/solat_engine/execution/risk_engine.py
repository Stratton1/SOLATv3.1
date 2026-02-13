"""
Risk Engine for execution gating.

Enforces hard limits on position size, exposure, loss, and trade frequency.
All intents must pass through RiskEngine before submission to broker.
"""

from datetime import UTC, datetime, timedelta

from solat_engine.execution.models import (
    ExecutionConfig,
    OrderIntent,
    PositionView,
    RiskCheckResult,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


class RiskEngine:
    """
    Hard gate for all order intents.

    Validates:
    - Position size limits
    - Concurrent position count
    - Daily loss limits
    - Trade frequency limits
    - Per-symbol exposure caps
    - Dealing rules (min size, step)
    """

    def __init__(self, config: ExecutionConfig):
        """
        Initialize risk engine with configuration.

        Args:
            config: Execution configuration with limits
        """
        self._config = config
        self._trades_timestamps: list[datetime] = []
        self._daily_pnl_start: float = 0.0
        self._daily_pnl_reset_date: datetime | None = None
        self._dealing_rules: dict[str, dict[str, float]] = {}
        self._symbol_metadata: dict[str, dict[str, float]] = {}

    def set_symbol_metadata(
        self,
        symbol: str,
        lot_size: float = 1.0,
        margin_factor: float = 100.0,
    ) -> None:
        """Set metadata for exposure calculation."""
        self._symbol_metadata[symbol] = {
            "lot_size": lot_size,
            "margin_factor": margin_factor,
        }

    def set_dealing_rules(
        self,
        symbol: str,
        min_size: float = 0.01,
        max_size: float = 1000.0,
        size_step: float = 0.01,
    ) -> None:
        """Set dealing rules for a symbol."""
        self._dealing_rules[symbol] = {
            "min_size": min_size,
            "max_size": max_size,
            "size_step": size_step,
        }

    def get_dealing_rules(self, symbol: str) -> dict[str, float]:
        """Get dealing rules for a symbol."""
        return self._dealing_rules.get(
            symbol,
            {"min_size": 0.01, "max_size": 1000.0, "size_step": 0.01},
        )

    def check_intent(
        self,
        intent: OrderIntent,
        current_positions: list[PositionView],
        account_balance: float,
        realized_pnl_today: float,
    ) -> RiskCheckResult:
        """
        Validate an order intent against all risk limits.

        Args:
            intent: The order intent to validate
            current_positions: Current open positions
            account_balance: Current account balance
            realized_pnl_today: Realized PnL since UTC midnight

        Returns:
            RiskCheckResult with allowed status and adjusted size
        """
        reason_codes: list[str] = []
        adjusted_size = intent.size

        # Get dealing rules
        rules = self.get_dealing_rules(intent.symbol)
        min_size = rules["min_size"]
        max_size = rules["max_size"]
        size_step = rules["size_step"]

        # 1. Check max position size
        if adjusted_size > self._config.max_position_size:
            adjusted_size = self._config.max_position_size
            reason_codes.append("size_capped_to_max")
            logger.debug(
                "Size capped: %.4f -> %.4f (max_position_size)",
                intent.size,
                adjusted_size,
            )

        # 2. Check dealing rules max size
        if adjusted_size > max_size:
            adjusted_size = max_size
            reason_codes.append("size_capped_to_dealing_max")

        # 3. Round to size step
        if size_step > 0:
            adjusted_size = round(adjusted_size / size_step) * size_step
            if adjusted_size != intent.size:
                reason_codes.append("size_rounded_to_step")

        # 4. Check min size
        if adjusted_size < min_size:
            return RiskCheckResult(
                allowed=False,
                reason_codes=["below_min_size"],
                adjusted_size=0.0,
                original_size=intent.size,
                rejection_reason=f"Size {adjusted_size:.4f} below minimum {min_size:.4f}",
            )

        # 5. Check concurrent positions
        if len(current_positions) >= self._config.max_concurrent_positions:
            return RiskCheckResult(
                allowed=False,
                reason_codes=["max_positions_reached"],
                adjusted_size=adjusted_size,
                original_size=intent.size,
                rejection_reason=f"Max concurrent positions ({self._config.max_concurrent_positions}) reached",
            )

        # 6. Check daily loss limit
        if account_balance > 0:
            loss_pct = abs(min(0, realized_pnl_today)) / account_balance * 100
            if loss_pct >= self._config.max_daily_loss_pct:
                return RiskCheckResult(
                    allowed=False,
                    reason_codes=["daily_loss_limit_reached"],
                    adjusted_size=adjusted_size,
                    original_size=intent.size,
                    rejection_reason=f"Daily loss {loss_pct:.2f}% exceeds limit {self._config.max_daily_loss_pct}%",
                )

        # 7. Check trade frequency
        self._cleanup_old_trades()
        if len(self._trades_timestamps) >= self._config.max_trades_per_hour:
            return RiskCheckResult(
                allowed=False,
                reason_codes=["trade_rate_limit_exceeded"],
                adjusted_size=adjusted_size,
                original_size=intent.size,
                rejection_reason=f"Max trades per hour ({self._config.max_trades_per_hour}) exceeded",
            )

        # 8. Check per-symbol exposure
        meta = self._symbol_metadata.get(intent.symbol, {"lot_size": 1.0})
        lot_size = meta["lot_size"]

        symbol_exposure = sum(
            pos.size * pos.open_level * lot_size
            for pos in current_positions
            if pos.symbol == intent.symbol or pos.epic == intent.epic
        )
        
        # Add proposed exposure (approximate with 1.0 price if no mid provided)
        # In a real run, the router would provide the current mid price.
        proposed_exposure = adjusted_size * 1.0 * lot_size
        if symbol_exposure + proposed_exposure > self._config.per_symbol_exposure_cap:
            return RiskCheckResult(
                allowed=False,
                reason_codes=["symbol_exposure_cap_exceeded"],
                adjusted_size=adjusted_size,
                original_size=intent.size,
                rejection_reason=f"Symbol exposure would exceed cap {self._config.per_symbol_exposure_cap}",
            )

        # 9. Check SL requirement
        if self._config.require_sl and intent.stop_loss is None:
            return RiskCheckResult(
                allowed=False,
                reason_codes=["sl_required"],
                adjusted_size=adjusted_size,
                original_size=intent.size,
                rejection_reason="Stop loss is required but not provided",
            )

        # All checks passed
        return RiskCheckResult(
            allowed=True,
            reason_codes=reason_codes,
            adjusted_size=adjusted_size,
            original_size=intent.size,
        )

    def record_trade(self) -> None:
        """Record a trade for rate limiting."""
        self._trades_timestamps.append(datetime.now(UTC))

    def _cleanup_old_trades(self) -> None:
        """Remove trades older than 1 hour from rate limit tracking."""
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        self._trades_timestamps = [
            ts for ts in self._trades_timestamps if ts > cutoff
        ]

    def get_trades_this_hour(self) -> int:
        """Get count of trades in the last hour."""
        self._cleanup_old_trades()
        return len(self._trades_timestamps)

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (called at UTC midnight)."""
        self._daily_pnl_start = 0.0
        self._daily_pnl_reset_date = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        logger.info("Daily risk stats reset")

    def update_config(self, config: ExecutionConfig) -> None:
        """Update risk configuration."""
        self._config = config
        logger.info("Risk engine config updated")
