"""
Tests for domain models.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from solat_engine.domain import (
    Bar,
    Fill,
    FillType,
    Instrument,
    InstrumentType,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SignalDirection,
    Timeframe,
)


class TestInstrument:
    """Tests for Instrument model."""

    def test_create_instrument(self) -> None:
        """Should create instrument with required fields."""
        inst = Instrument(
            symbol="EURUSD",
            epic="CS.D.EURUSD.CFD.IP",
            name="EUR/USD",
            instrument_type=InstrumentType.FOREX,
        )
        assert inst.symbol == "EURUSD"
        assert inst.epic == "CS.D.EURUSD.CFD.IP"
        assert inst.instrument_type == InstrumentType.FOREX

    def test_instrument_is_immutable(self) -> None:
        """Instrument should be immutable (frozen)."""
        from pydantic import ValidationError

        inst = Instrument(
            symbol="EURUSD",
            epic="CS.D.EURUSD.CFD.IP",
            name="EUR/USD",
            instrument_type=InstrumentType.FOREX,
        )
        with pytest.raises(ValidationError):
            inst.symbol = "GBPUSD"  # type: ignore

    def test_instrument_hash(self) -> None:
        """Instruments with same symbol/epic should have same hash."""
        inst1 = Instrument(
            symbol="EURUSD",
            epic="CS.D.EURUSD.CFD.IP",
            name="EUR/USD",
            instrument_type=InstrumentType.FOREX,
        )
        inst2 = Instrument(
            symbol="EURUSD",
            epic="CS.D.EURUSD.CFD.IP",
            name="Euro vs Dollar",  # Different name
            instrument_type=InstrumentType.FOREX,
        )
        assert hash(inst1) == hash(inst2)


class TestBar:
    """Tests for Bar model."""

    def test_create_bar(self) -> None:
        """Should create bar with valid OHLCV data."""
        bar = Bar(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime.now(UTC),
            open=Decimal("1.1000"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            close=Decimal("1.1020"),
        )
        assert bar.symbol == "EURUSD"
        assert bar.timeframe == Timeframe.H1

    def test_bar_validation_high_gte_low(self) -> None:
        """High must be >= low."""
        with pytest.raises(ValueError):
            Bar(
                symbol="EURUSD",
                timeframe=Timeframe.H1,
                timestamp=datetime.now(UTC),
                open=Decimal("1.1000"),
                high=Decimal("1.0900"),  # Invalid: less than low
                low=Decimal("1.0950"),
                close=Decimal("1.1020"),
            )

    def test_bar_is_bullish(self) -> None:
        """Bar should correctly identify bullish pattern."""
        bar = Bar(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime.now(UTC),
            open=Decimal("1.1000"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            close=Decimal("1.1030"),  # Close > Open
        )
        assert bar.is_bullish
        assert not bar.is_bearish

    def test_bar_is_bearish(self) -> None:
        """Bar should correctly identify bearish pattern."""
        bar = Bar(
            symbol="EURUSD",
            timeframe=Timeframe.H1,
            timestamp=datetime.now(UTC),
            open=Decimal("1.1030"),
            high=Decimal("1.1050"),
            low=Decimal("1.0950"),
            close=Decimal("1.1000"),  # Close < Open
        )
        assert bar.is_bearish
        assert not bar.is_bullish

    def test_timeframe_minutes(self) -> None:
        """Timeframe should return correct minutes."""
        assert Timeframe.M1.minutes == 1
        assert Timeframe.M5.minutes == 5
        assert Timeframe.H1.minutes == 60
        assert Timeframe.H4.minutes == 240
        assert Timeframe.D1.minutes == 1440


class TestSignal:
    """Tests for Signal model."""

    def test_create_signal(self) -> None:
        """Should create signal with required fields."""
        signal = Signal(
            strategy_id="test_strategy",
            symbol="EURUSD",
            timestamp=datetime.now(UTC),
            direction=SignalDirection.LONG,
        )
        assert signal.strategy_id == "test_strategy"
        assert signal.direction == SignalDirection.LONG
        assert signal.is_entry
        assert signal.is_long
        assert not signal.is_short

    def test_signal_exit(self) -> None:
        """FLAT signal should be identified as exit."""
        signal = Signal(
            strategy_id="test_strategy",
            symbol="EURUSD",
            timestamp=datetime.now(UTC),
            direction=SignalDirection.FLAT,
        )
        assert signal.is_exit
        assert not signal.is_entry


class TestOrder:
    """Tests for Order model."""

    def test_create_market_order(self) -> None:
        """Should create market order."""
        order = Order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1.0"),
        )
        assert order.symbol == "EURUSD"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.PENDING
        assert order.is_open

    def test_order_remaining_quantity(self) -> None:
        """Should calculate remaining quantity correctly."""
        order = Order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("10.0"),
            filled_quantity=Decimal("3.0"),
        )
        assert order.remaining_quantity == Decimal("7.0")


class TestFill:
    """Tests for Fill model."""

    def test_create_fill(self) -> None:
        """Should create fill with required fields."""
        from uuid import uuid4

        order_id = uuid4()
        fill = Fill(
            order_id=order_id,
            symbol="EURUSD",
            quantity=Decimal("1.0"),
            price=Decimal("1.1000"),
            fill_type=FillType.FULL,
            timestamp=datetime.now(UTC),
        )
        assert fill.order_id == order_id
        assert fill.quantity == Decimal("1.0")
        assert fill.notional_value == Decimal("1.1000")


class TestPosition:
    """Tests for Position model."""

    def test_create_position(self) -> None:
        """Should create position with required fields."""
        position = Position(
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),
            entry_price=Decimal("1.1000"),
            opened_at=datetime.now(UTC),
        )
        assert position.symbol == "EURUSD"
        assert position.is_long
        assert not position.is_short

    def test_position_unrealized_pnl_long(self) -> None:
        """Should calculate unrealized P&L for long position."""
        position = Position(
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            entry_price=Decimal("1.1000"),
            opened_at=datetime.now(UTC),
        )
        # Price went up - profit
        pnl = position.calculate_unrealized_pnl(Decimal("1.1100"))
        assert pnl == Decimal("1.0")  # 0.01 * 100

    def test_position_unrealized_pnl_short(self) -> None:
        """Should calculate unrealized P&L for short position."""
        position = Position(
            symbol="EURUSD",
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            entry_price=Decimal("1.1000"),
            opened_at=datetime.now(UTC),
        )
        # Price went down - profit for short
        pnl = position.calculate_unrealized_pnl(Decimal("1.0900"))
        assert pnl == Decimal("1.0")  # 0.01 * 100
