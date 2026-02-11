"""Regime/churn hardening tests for Elite 8 strategies."""

import pytest

from solat_engine.backtest.models import SignalIntent
from solat_engine.strategies.elite8_hardened import (
    CloudTwist,
    KijunBouncer,
    KumoBreaker,
    StrategyContext,
    TKCrossSniper,
    TrendSurfer,
)
from tests.strategies.synthetic_data import (
    chop_range,
    clean_trend_with_turn,
    flat_market,
    persistent_breakout,
)


def _simulate_entries(strategy: object, bars: list, symbol: str = "EURUSD", timeframe: str = "1m") -> int:
    entries = 0
    position: str | None = None
    for i in range(len(bars)):
        signal: SignalIntent = strategy.generate_signal(
            bars[: i + 1],
            current_position=position,
            context=StrategyContext(symbol=symbol, timeframe=timeframe, bar_index=i, bot_name=strategy.name),
        )
        if position is None and signal.direction == "BUY":
            position = "long"
            entries += 1
        elif position is None and signal.direction == "SELL":
            position = "short"
            entries += 1
        elif position == "long" and signal.direction == "SELL":
            position = None
        elif position == "short" and signal.direction == "BUY":
            position = None
    return entries


@pytest.mark.parametrize(
    ("strategy_cls", "max_flat_entries", "max_chop_entries"),
    [
        (TKCrossSniper, 1, 2),
        (KumoBreaker, 1, 3),
        (TrendSurfer, 1, 3),
        (CloudTwist, 2, 4),
    ],
)
def test_trend_bots_suppress_signals_in_flat_and_chop(
    strategy_cls: type,
    max_flat_entries: int,
    max_chop_entries: int,
) -> None:
    strategy = strategy_cls(warmup_bars=80)
    flat_entries = _simulate_entries(strategy, flat_market(500))
    chop_entries = _simulate_entries(strategy_cls(warmup_bars=80), chop_range(500))

    assert flat_entries <= max_flat_entries
    assert chop_entries <= max_chop_entries


def test_trend_bots_trade_in_clean_trend_with_bounded_frequency() -> None:
    bots = [TKCrossSniper, KumoBreaker, TrendSurfer, CloudTwist]
    entries_by_bot: dict[str, int] = {}

    for strategy_cls in bots:
        strategy = strategy_cls(warmup_bars=40)
        entries = _simulate_entries(strategy, clean_trend_with_turn(600))
        entries_by_bot[strategy.name] = entries
        entries_per_1000 = (entries / 600) * 1000
        assert entries_per_1000 <= 40

    assert any(entries > 0 for entries in entries_by_bot.values())


def test_no_repeated_signals_on_persistent_breakout_condition() -> None:
    strategy = KumoBreaker(warmup_bars=80)
    bars = persistent_breakout(220)

    buy_entries = 0
    for i in range(len(bars)):
        signal = strategy.generate_signal(
            bars[: i + 1],
            current_position=None,
            context=StrategyContext(symbol="EURUSD", timeframe="1m", bar_index=i, bot_name=strategy.name),
        )
        if signal.direction == "BUY":
            buy_entries += 1

    assert buy_entries <= 1


def test_kijun_bouncer_needs_next_bar_confirmation() -> None:
    strategy = KijunBouncer(warmup_bars=80)
    entries = _simulate_entries(strategy, chop_range(450))
    assert entries <= 6
