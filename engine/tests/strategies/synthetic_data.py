"""Deterministic synthetic OHLCV generators for strategy tests."""

from datetime import UTC, datetime, timedelta

from solat_engine.strategies.elite8_hardened import BarData


def flat_market(n: int, base_price: float = 1.1000) -> list[BarData]:
    bars: list[BarData] = []
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    micro_cycle = [0.0, 0.00001, -0.00001, 0.00002, -0.00002]
    for i in range(n):
        close = base_price + micro_cycle[i % len(micro_cycle)]
        bars.append(
            BarData(
                timestamp=start + timedelta(minutes=i),
                open=close - 0.00002,
                high=close + 0.00008,
                low=close - 0.00008,
                close=close,
                volume=100.0,
            )
        )
    return bars


def clean_trend(n: int, start_price: float = 1.1000, step: float = 0.0002) -> list[BarData]:
    bars: list[BarData] = []
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    for i in range(n):
        # Small deterministic pullback every 17 bars.
        pullback = -step * 0.5 if i > 0 and i % 17 == 0 else 0.0
        close = start_price + (i * step) + pullback
        bars.append(
            BarData(
                timestamp=start + timedelta(minutes=i),
                open=close - 0.00006,
                high=close + 0.00018,
                low=close - 0.00012,
                close=close,
                volume=110.0 + (i % 7),
            )
        )
    return bars


def clean_trend_with_turn(n: int, start_price: float = 1.1000, step: float = 0.0002) -> list[BarData]:
    """Two-phase trend: mild decline then persistent climb."""
    bars: list[BarData] = []
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    pivot = max(30, n // 3)
    for i in range(n):
        if i < pivot:
            close = start_price - (i * step * 0.7)
        else:
            close = (start_price - (pivot * step * 0.7)) + ((i - pivot) * step * 1.2)
        bars.append(
            BarData(
                timestamp=start + timedelta(minutes=i),
                open=close - 0.00006,
                high=close + 0.0002,
                low=close - 0.00014,
                close=close,
                volume=110.0 + (i % 9),
            )
        )
    return bars


def chop_range(n: int, center: float = 1.1000, amplitude: float = 0.0006) -> list[BarData]:
    bars: list[BarData] = []
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    cycle = [0.0, 0.4, 1.0, 0.6, 0.0, -0.4, -1.0, -0.6]
    for i in range(n):
        phase = cycle[i % len(cycle)]
        close = center + (phase * amplitude)
        bars.append(
            BarData(
                timestamp=start + timedelta(minutes=i),
                open=close + (0.00005 if i % 2 == 0 else -0.00005),
                high=close + 0.00020,
                low=close - 0.00020,
                close=close,
                volume=95.0 + (i % 5),
            )
        )
    return bars


def persistent_breakout(n: int, base_price: float = 1.1000) -> list[BarData]:
    """Generate bars that break up and then stay elevated."""
    bars: list[BarData] = []
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    for i in range(n):
        if i < n // 4:
            close = base_price + (i * 0.00003)
        else:
            close = base_price + 0.008 + ((i - (n // 4)) * 0.00001)
        bars.append(
            BarData(
                timestamp=start + timedelta(minutes=i),
                open=close - 0.00004,
                high=close + 0.00022,
                low=close - 0.00012,
                close=close,
                volume=120.0,
            )
        )
    return bars
