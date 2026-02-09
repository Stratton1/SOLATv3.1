"""
Position sizing for backtesting.

Supports fixed size and risk-per-trade methods.
"""

from dataclasses import dataclass

from solat_engine.backtest.models import RiskConfig, SignalIntent, SizingMethod
from solat_engine.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SizeResult:
    """Result of position sizing calculation."""

    size: float
    method_used: SizingMethod
    risk_amount: float = 0.0
    stop_distance: float = 0.0
    rejection_reason: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.rejection_reason is None and self.size > 0


def calculate_position_size(
    signal: SignalIntent,
    equity: float,
    current_price: float,
    risk_config: RiskConfig,
    pip_size: float = 0.0001,
    min_size: float = 0.01,
    size_step: float = 0.01,
) -> SizeResult:
    """
    Calculate position size based on risk configuration.

    For RISK_PER_TRADE:
    - Uses stop loss distance to determine size
    - size = (equity * risk_pct) / (stop_distance_in_price)

    For FIXED_SIZE:
    - Returns configured fixed size

    Returns SizeResult with size and metadata.
    """
    if risk_config.sizing_method == SizingMethod.FIXED_SIZE:
        size = risk_config.fixed_size
        size = _round_to_step(size, size_step)
        size = max(min_size, size)

        return SizeResult(
            size=size,
            method_used=SizingMethod.FIXED_SIZE,
        )

    # RISK_PER_TRADE method
    if signal.stop_loss is None:
        # No stop loss provided - fall back to fixed size
        logger.debug(
            "No stop loss in signal, falling back to fixed size for risk-per-trade"
        )
        size = risk_config.fixed_size
        size = _round_to_step(size, size_step)
        size = max(min_size, size)

        return SizeResult(
            size=size,
            method_used=SizingMethod.FIXED_SIZE,
            rejection_reason=None,
        )

    # Calculate stop distance
    stop_distance = abs(current_price - signal.stop_loss)

    if stop_distance <= 0:
        return SizeResult(
            size=0.0,
            method_used=SizingMethod.RISK_PER_TRADE,
            rejection_reason="Stop loss distance is zero or negative",
        )

    # Risk amount in account currency
    risk_pct = risk_config.risk_per_trade_pct / 100.0
    risk_amount = equity * risk_pct

    # Calculate size
    # For forex: size (lots) = risk_amount / (stop_distance_in_pips * pip_value)
    # Simplified: size = risk_amount / stop_distance (assuming 1:1 pip value per lot)
    size = risk_amount / stop_distance

    # Round to step
    size = _round_to_step(size, size_step)
    size = max(min_size, size)

    return SizeResult(
        size=size,
        method_used=SizingMethod.RISK_PER_TRADE,
        risk_amount=risk_amount,
        stop_distance=stop_distance,
    )


def _round_to_step(value: float, step: float) -> float:
    """Round value to nearest step."""
    if step <= 0:
        return value
    return round(value / step) * step


def check_risk_limits(
    symbol: str,
    proposed_size: float,
    current_price: float,
    equity: float,
    current_position_count: int,
    current_symbol_exposure: float,
    current_total_exposure: float,
    risk_config: RiskConfig,
) -> tuple[bool, str | None]:
    """
    Check if proposed position passes risk limits.

    Returns (is_allowed, rejection_reason).
    """
    # Check max positions
    if current_position_count >= risk_config.max_open_positions:
        return False, f"Max positions ({risk_config.max_open_positions}) reached"

    # Calculate proposed exposure for limit checks
    proposed_notional = proposed_size * current_price

    # Check symbol exposure
    new_symbol_exposure = current_symbol_exposure + proposed_notional
    if new_symbol_exposure > risk_config.max_exposure_per_symbol:
        return False, (
            f"Symbol exposure {new_symbol_exposure:.2f} exceeds max "
            f"{risk_config.max_exposure_per_symbol:.2f}"
        )

    # Check total exposure
    new_total_exposure = current_total_exposure + proposed_notional
    if new_total_exposure > risk_config.max_total_exposure:
        return False, (
            f"Total exposure {new_total_exposure:.2f} exceeds max "
            f"{risk_config.max_total_exposure:.2f}"
        )

    return True, None


def adjust_size_for_exposure(
    proposed_size: float,
    current_price: float,
    current_symbol_exposure: float,
    current_total_exposure: float,
    risk_config: RiskConfig,
    min_size: float = 0.01,
    size_step: float = 0.01,
) -> float:
    """
    Adjust size down if it would exceed exposure limits.

    Returns adjusted size (may be 0 if impossible).
    """
    # Check symbol limit
    max_symbol_add = risk_config.max_exposure_per_symbol - current_symbol_exposure
    max_size_symbol = max_symbol_add / current_price if current_price > 0 else 0

    # Check total limit
    max_total_add = risk_config.max_total_exposure - current_total_exposure
    max_size_total = max_total_add / current_price if current_price > 0 else 0

    # Take minimum
    max_size = min(proposed_size, max_size_symbol, max_size_total)

    if max_size < min_size:
        return 0.0

    # Round down to step
    adjusted = (max_size // size_step) * size_step

    return max(0.0, adjusted)
