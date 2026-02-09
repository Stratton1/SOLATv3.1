"""
Tests for execution risk engine.

Tests caps, rounding, and rejection reasons.
"""

import pytest

from solat_engine.execution.models import (
    ExecutionConfig,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionView,
)
from solat_engine.execution.risk_engine import RiskEngine

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def default_config() -> ExecutionConfig:
    """Create default execution config."""
    return ExecutionConfig(
        max_position_size=1.0,
        max_concurrent_positions=3,
        max_daily_loss_pct=5.0,
        max_trades_per_hour=10,
        per_symbol_exposure_cap=10000.0,
        require_sl=False,
    )


@pytest.fixture
def risk_engine(default_config: ExecutionConfig) -> RiskEngine:
    """Create risk engine with default config."""
    return RiskEngine(default_config)


@pytest.fixture
def sample_intent() -> OrderIntent:
    """Create sample order intent."""
    return OrderIntent(
        symbol="EURUSD",
        epic="CS.D.EURUSD.MINI.IP",
        side=OrderSide.BUY,
        size=0.5,
        order_type=OrderType.MARKET,
        bot="TestBot",
        reason_codes=["test"],
    )


# =============================================================================
# Size Capping Tests
# =============================================================================


class TestSizeCapping:
    """Tests for position size capping."""

    def test_size_capped_to_max(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Size exceeding max should be capped."""
        sample_intent.size = 5.0  # Exceeds max of 1.0

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert result.allowed
        assert result.adjusted_size == 1.0
        assert "size_capped_to_max" in result.reason_codes

    def test_size_rounded_to_step(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Size should be rounded to step."""
        risk_engine.set_dealing_rules("EURUSD", min_size=0.01, size_step=0.01)
        sample_intent.size = 0.555  # Will round to 0.56

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert result.allowed
        assert result.adjusted_size == 0.56

    def test_size_below_min_rejected(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Size below minimum should be rejected."""
        risk_engine.set_dealing_rules("EURUSD", min_size=0.1)
        sample_intent.size = 0.05

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert not result.allowed
        assert "below_min_size" in result.reason_codes


# =============================================================================
# Position Limit Tests
# =============================================================================


class TestPositionLimits:
    """Tests for concurrent position limits."""

    def test_max_positions_reached(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should reject when max positions reached."""
        # Create 3 existing positions (max)
        positions = [
            PositionView(
                deal_id=f"deal_{i}",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.1,
                open_level=1.1,
            )
            for i in range(3)
        ]

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=positions,
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert not result.allowed
        assert "max_positions_reached" in result.reason_codes

    def test_allows_when_below_max(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should allow when below max positions."""
        positions = [
            PositionView(
                deal_id="deal_1",
                epic="CS.D.EURUSD.MINI.IP",
                direction=OrderSide.BUY,
                size=0.1,
                open_level=1.1,
            )
        ]

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=positions,
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert result.allowed


# =============================================================================
# Daily Loss Limit Tests
# =============================================================================


class TestDailyLossLimit:
    """Tests for daily loss limit."""

    def test_daily_loss_limit_reached(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should reject when daily loss limit reached."""
        # 6% loss on 10000 = -600 (exceeds 5%)
        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=-600,
        )

        assert not result.allowed
        assert "daily_loss_limit_reached" in result.reason_codes

    def test_allows_within_loss_limit(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should allow when within daily loss limit."""
        # 4% loss on 10000 = -400 (within 5%)
        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=-400,
        )

        assert result.allowed


# =============================================================================
# Trade Rate Limit Tests
# =============================================================================


class TestTradeRateLimit:
    """Tests for trade rate limiting."""

    def test_trade_rate_limit_exceeded(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should reject when trade rate limit exceeded."""
        # Record 10 trades (max)
        for _ in range(10):
            risk_engine.record_trade()

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert not result.allowed
        assert "trade_rate_limit_exceeded" in result.reason_codes

    def test_allows_within_rate_limit(
        self,
        risk_engine: RiskEngine,
        sample_intent: OrderIntent,
    ) -> None:
        """Should allow when within rate limit."""
        # Record 5 trades (half of max)
        for _ in range(5):
            risk_engine.record_trade()

        result = risk_engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert result.allowed


# =============================================================================
# Stop Loss Requirement Tests
# =============================================================================


class TestStopLossRequirement:
    """Tests for stop loss requirement."""

    def test_sl_required_but_missing(
        self,
        sample_intent: OrderIntent,
    ) -> None:
        """Should reject when SL required but not provided."""
        config = ExecutionConfig(require_sl=True)
        engine = RiskEngine(config)
        sample_intent.stop_loss = None

        result = engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert not result.allowed
        assert "sl_required" in result.reason_codes

    def test_sl_provided_when_required(
        self,
        sample_intent: OrderIntent,
    ) -> None:
        """Should allow when SL is provided."""
        config = ExecutionConfig(require_sl=True)
        engine = RiskEngine(config)
        sample_intent.stop_loss = 1.0800

        result = engine.check_intent(
            intent=sample_intent,
            current_positions=[],
            account_balance=10000,
            realized_pnl_today=0,
        )

        assert result.allowed


# =============================================================================
# Dealing Rules Tests
# =============================================================================


class TestDealingRules:
    """Tests for dealing rules."""

    def test_dealing_rules_applied(self, risk_engine: RiskEngine) -> None:
        """Dealing rules should be stored and retrieved."""
        risk_engine.set_dealing_rules(
            "EURUSD",
            min_size=0.1,
            max_size=10.0,
            size_step=0.1,
        )

        rules = risk_engine.get_dealing_rules("EURUSD")

        assert rules["min_size"] == 0.1
        assert rules["max_size"] == 10.0
        assert rules["size_step"] == 0.1

    def test_default_dealing_rules(self, risk_engine: RiskEngine) -> None:
        """Should return defaults for unknown symbol."""
        rules = risk_engine.get_dealing_rules("UNKNOWN")

        assert rules["min_size"] == 0.01
        assert rules["max_size"] == 1000.0
        assert rules["size_step"] == 0.01
