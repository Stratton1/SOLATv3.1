"""
Hardened Elite 8 strategies with shared regime and gating helpers.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from solat_engine.backtest.models import SignalIntent
from solat_engine.strategies.indicators import (
    adx,
    atr,
    atr_pct,
    crossover,
    crossunder,
    ema,
    ichimoku,
    is_price_above_cloud,
    is_price_below_cloud,
    macd,
    rsi,
    volume_zscore,
)


@dataclass(frozen=True)
class BarData:
    timestamp: Any
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Regime(str, Enum):
    TRENDING = "TRENDING"
    CHOP = "CHOP"
    EXPLOSIVE = "EXPLOSIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeThresholds:
    adx_trend_min: float = 20.0
    adx_chop_max: float = 18.0
    atr_pct_min_active: float = 0.0008
    atr_pct_explosive: float = 0.0060
    vol_z_explosive: float = 1.5


@dataclass(frozen=True)
class StrategyContext:
    symbol: str = "unknown"
    timeframe: str = "unknown"
    bar_index: int = -1
    bot_name: str = "unknown"


@dataclass(frozen=True)
class BaseHardeningParams:
    cooldown_bars: int = 6
    breakout_atr_mult: float = 0.5
    regime_thresholds: RegimeThresholds = field(default_factory=RegimeThresholds)


@dataclass(frozen=True)
class TKCrossSniperParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=6))
    cloud_clear_atr_mult: float = 0.3


@dataclass(frozen=True)
class KumoBreakerParams:
    base: BaseHardeningParams = field(
        default_factory=lambda: BaseHardeningParams(cooldown_bars=6, breakout_atr_mult=0.5)
    )
    breakout_retest_enabled: bool = False
    retest_tolerance_atr_mult: float = 0.2


@dataclass(frozen=True)
class ChikouConfirmerParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=4))


@dataclass(frozen=True)
class KijunBouncerParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=8))
    impulse_atr_mult: float = 2.0
    kijun_touch_tolerance: float = 0.001


@dataclass(frozen=True)
class CloudTwistParams:
    base: BaseHardeningParams = field(
        default_factory=lambda: BaseHardeningParams(cooldown_bars=8, breakout_atr_mult=0.3)
    )


@dataclass(frozen=True)
class MomentumRiderParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=6))


@dataclass(frozen=True)
class TrendSurferParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=6))
    pullback_entry_enabled: bool = True


@dataclass(frozen=True)
class ReversalHunterParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=10))
    explosive_atr_pct_block: float = 0.0060


@dataclass(frozen=True)
class ChikouKaizenParams:
    base: BaseHardeningParams = field(default_factory=lambda: BaseHardeningParams(cooldown_bars=6))
    displacement: int = 26
    sl_atr_mult: float = 1.0
    tp_atr_mult: float = 2.0


class Elite8BaseStrategy(ABC):
    def __init__(self, warmup_bars: int = 100, *, cooldown_bars: int = 0):
        self.warmup_bars = warmup_bars
        self.cooldown_bars = cooldown_bars
        self._last_signal_bar_by_key: dict[tuple[str, str, str], int] = {}
        self._last_direction_by_key: dict[tuple[str, str, str], str] = {}

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
        context: StrategyContext | None = None,
    ) -> SignalIntent: ...

    def _extract_ohlc(
        self, bars: Sequence[BarData]
    ) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
        return (
            [b.open for b in bars],
            [b.high for b in bars],
            [b.low for b in bars],
            [b.close for b in bars],
            [b.volume for b in bars],
        )

    def _calculate_sl_tp(
        self,
        entry_price: float,
        atr_value: float,
        is_long: bool,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.0,
    ) -> tuple[float, float]:
        if is_long:
            return entry_price - (atr_value * sl_atr_mult), entry_price + (atr_value * tp_atr_mult)
        return entry_price + (atr_value * sl_atr_mult), entry_price - (atr_value * tp_atr_mult)

    def _hold(self, *reasons: str, metadata: dict[str, Any] | None = None) -> SignalIntent:
        return SignalIntent(
            direction="HOLD",
            reason_codes=list(reasons) if reasons else ["no_signal"],
            metadata=metadata or {},
        )

    def _context_key(self, context: StrategyContext | None) -> tuple[str, str, str]:
        if context is None:
            return (self.name, "global", "global")
        return (context.bot_name or self.name, context.symbol or "unknown", context.timeframe or "unknown")

    def _bar_index(self, bars: Sequence[BarData], context: StrategyContext | None) -> int:
        if context is not None and context.bar_index >= 0:
            return context.bar_index
        return len(bars) - 1

    def _entry_gate(
        self,
        key: tuple[str, str, str],
        bar_index: int,
        direction: str,
        cooldown_bars: int,
    ) -> SignalIntent | None:
        last = self._last_signal_bar_by_key.get(key)
        if cooldown_bars > 0 and last is not None and (bar_index - last) < cooldown_bars:
            return self._hold("cooldown_active")
        if self._last_direction_by_key.get(key) == direction:
            return self._hold("not_fresh_signal")
        return None

    def _register_signal(self, key: tuple[str, str, str], bar_index: int, direction: str) -> None:
        self._last_signal_bar_by_key[key] = bar_index
        self._last_direction_by_key[key] = direction

    def _compute_regime(
        self,
        highs: Sequence[float],
        lows: Sequence[float],
        closes: Sequence[float],
        volumes: Sequence[float],
        idx: int,
        thresholds: RegimeThresholds,
    ) -> tuple[Regime, float, float]:
        adx_values = adx(highs, lows, closes, period=14)
        atr_values = atr(highs, lows, closes, period=14)
        atr_pct_values = atr_pct(atr_values, closes)

        volume_available = any(v > 0 for v in volumes[max(0, idx - 40) : idx + 1])
        vol_z = None
        if volume_available:
            vol_z = volume_zscore(volumes, period=20)[idx]

        adx_14 = adx_values[idx]
        atr_pct_14 = atr_pct_values[idx]
        if adx_14 >= thresholds.adx_trend_min and atr_pct_14 >= thresholds.atr_pct_min_active:
            regime = Regime.TRENDING
        elif adx_14 <= thresholds.adx_chop_max:
            regime = Regime.CHOP
        elif atr_pct_14 >= thresholds.atr_pct_explosive and (
            (not volume_available) or (vol_z is not None and vol_z >= thresholds.vol_z_explosive)
        ):
            regime = Regime.EXPLOSIVE
        else:
            regime = Regime.UNKNOWN
        return regime, atr_values[idx], atr_pct_14

    def _breakout_confirm(
        self, close: float, level: float, atr_value: float, atr_mult: float, is_long: bool
    ) -> bool:
        d = atr_value * atr_mult
        return close > (level + d) if is_long else close < (level - d)


class TKCrossSniper(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: TKCrossSniperParams | None = None):
        self.params = params or TKCrossSniperParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "TKCrossSniper"

    @property
    def description(self) -> str:
        return "Tenkan-Kijun cross with cloud confirmation"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]

        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        ichi = ichimoku(highs, lows, closes)
        tenkan, kijun = ichi["tenkan"], ichi["kijun"]
        senkou_a, senkou_b = ichi["senkou_a"], ichi["senkou_b"]
        cloud_top = max(senkou_a[idx], senkou_b[idx])
        cloud_bottom = min(senkou_a[idx], senkou_b[idx])
        cross_up = crossover(tenkan, kijun, idx)
        cross_down = crossunder(tenkan, kijun, idx)
        above_cloud = price > (cloud_top + current_atr * self.params.cloud_clear_atr_mult)
        below_cloud = price < (cloud_bottom - current_atr * self.params.cloud_clear_atr_mult)

        if current_position == "long" and (cross_down or price < cloud_bottom):
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["tk_cross_exit", "close_long"])
        if current_position == "short" and (cross_up or price > cloud_top):
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["tk_cross_exit", "close_short"])
        if current_position is None:
            if regime != Regime.TRENDING:
                return self._hold("regime_blocked")
            if cross_up and above_cloud:
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["tk_cross_up", "cloud_clearance"],
                    metadata={"regime": regime.value},
                )
            if cross_down and below_cloud:
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["tk_cross_down", "cloud_clearance"],
                    metadata={"regime": regime.value},
                )
        return self._hold("no_signal")


class KumoBreaker(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: KumoBreakerParams | None = None):
        self.params = params or KumoBreakerParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)
        self._one_side_latch: dict[tuple[str, str, str], str] = {}
        self._pending_retest: dict[tuple[str, str, str], dict[str, float | int | str]] = {}

    @property
    def name(self) -> str:
        return "KumoBreaker"

    @property
    def description(self) -> str:
        return "Cloud breakout with momentum confirmation"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        prev_price = closes[idx - 1] if idx > 0 else price
        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        ichi = ichimoku(highs, lows, closes)
        senkou_a, senkou_b = ichi["senkou_a"], ichi["senkou_b"]
        cloud_top = max(senkou_a[idx], senkou_b[idx])
        cloud_bottom = min(senkou_a[idx], senkou_b[idx])
        prev_cloud_top = max(senkou_a[idx - 1], senkou_b[idx - 1])
        prev_cloud_bottom = min(senkou_a[idx - 1], senkou_b[idx - 1])
        broke_above = prev_price <= prev_cloud_top and self._breakout_confirm(
            price, cloud_top, current_atr, self.params.base.breakout_atr_mult, True
        )
        broke_below = prev_price >= prev_cloud_bottom and self._breakout_confirm(
            price, cloud_bottom, current_atr, self.params.base.breakout_atr_mult, False
        )
        in_cloud = cloud_bottom <= price <= cloud_top
        if in_cloud:
            self._one_side_latch.pop(key, None)
        if current_position == "long" and (in_cloud or broke_below):
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["kumo_reentry", "close_long"])
        if current_position == "short" and (in_cloud or broke_above):
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["kumo_reentry", "close_short"])
        if current_position is None:
            if regime not in (Regime.TRENDING, Regime.EXPLOSIVE):
                return self._hold("regime_blocked")
            if broke_above and self._one_side_latch.get(key) != "BUY":
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                self._one_side_latch[key] = "BUY"
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True, sl_atr_mult=2.0)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kumo_breakout_up", "close_confirmed"],
                    metadata={"regime": regime.value},
                )
            if broke_below and self._one_side_latch.get(key) != "SELL":
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                self._one_side_latch[key] = "SELL"
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False, sl_atr_mult=2.0)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kumo_breakout_down", "close_confirmed"],
                    metadata={"regime": regime.value},
                )
            if self.params.breakout_retest_enabled:
                pending = self._pending_retest.get(key)
                if broke_above:
                    self._pending_retest[key] = {"side": "BUY", "level": cloud_top, "bar_index": bar_index}
                if broke_below:
                    self._pending_retest[key] = {"side": "SELL", "level": cloud_bottom, "bar_index": bar_index}
                if pending is not None:
                    side = str(pending["side"])
                    level = float(pending["level"])
                    tol = current_atr * self.params.retest_tolerance_atr_mult
                    touched = abs(price - level) <= tol
                    bounced = price > level + tol if side == "BUY" else price < level - tol
                    if touched and bounced:
                        gate = self._entry_gate(key, bar_index, side, self.cooldown_bars)
                        if gate is not None:
                            return gate
                        is_long = side == "BUY"
                        sl, tp = self._calculate_sl_tp(price, current_atr, is_long=is_long, sl_atr_mult=2.0)
                        self._register_signal(key, bar_index, side)
                        self._one_side_latch[key] = side
                        self._pending_retest.pop(key, None)
                        return SignalIntent(
                            direction=side,
                            stop_loss=sl,
                            take_profit=tp,
                            reason_codes=["kumo_retest_confirmed"],
                            metadata={"regime": regime.value},
                        )
        return self._hold("no_signal")


class ChikouConfirmer(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: ChikouConfirmerParams | None = None):
        self.params = params or ChikouConfirmerParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "ChikouConfirmer"

    @property
    def description(self) -> str:
        return "Chikou Span trend confirmation (filter-only)"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        displacement = 26
        if idx < displacement:
            return self._hold("insufficient_data")
        regime, _, _ = self._compute_regime(highs, lows, closes, volumes, idx, self.params.base.regime_thresholds)
        chikou_current = closes[idx]
        price_26_ago = closes[idx - displacement]
        chikou_prev = closes[idx - 1]
        price_27_ago = closes[idx - displacement - 1] if idx > displacement else price_26_ago
        return self._hold(
            "filter_only",
            metadata={
                "regime": regime.value,
                "chikou_confirm_long": chikou_prev <= price_27_ago and chikou_current > price_26_ago,
                "chikou_confirm_short": chikou_prev >= price_27_ago and chikou_current < price_26_ago,
                "current_position": current_position,
            },
        )


class KijunBouncer(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: KijunBouncerParams | None = None):
        self.params = params or KijunBouncerParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)
        self._pending_touch: dict[tuple[str, str, str], dict[str, float | int | str]] = {}

    @property
    def name(self) -> str:
        return "KijunBouncer"

    @property
    def description(self) -> str:
        return "Kijun-sen bounce in trend with next-bar confirmation"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        opens, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        if regime == Regime.CHOP:
            self._pending_touch.pop(key, None)
            return self._hold("regime_blocked")
        ichi = ichimoku(highs, lows, closes)
        kijun = ichi["kijun"]
        senkou_a, senkou_b = ichi["senkou_a"], ichi["senkou_b"]
        above_cloud = is_price_above_cloud(price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(price, senkou_a[idx], senkou_b[idx])
        kijun_val = kijun[idx]
        if current_position == "long" and price < kijun_val * 0.995:
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["kijun_break", "close_long"])
        if current_position == "short" and price > kijun_val * 1.005:
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["kijun_break", "close_short"])
        pending = self._pending_touch.get(key)
        if current_position is None and pending is not None and int(pending["bar_index"]) == bar_index - 1:
            side = str(pending["side"])
            touched_level = float(pending["kijun"])
            confirmed = (
                price > opens[idx] and price > touched_level and (idx == 0 or price > closes[idx - 1])
                if side == "BUY"
                else price < opens[idx] and price < touched_level and (idx == 0 or price < closes[idx - 1])
            )
            if confirmed:
                gate = self._entry_gate(key, bar_index, side, self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=(side == "BUY"))
                self._register_signal(key, bar_index, side)
                self._pending_touch.pop(key, None)
                return SignalIntent(
                    direction=side,
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kijun_touch_confirmed", "next_bar_confirmation"],
                    metadata={"regime": regime.value},
                )
        impulse = abs(price - opens[idx]) > (self.params.impulse_atr_mult * current_atr)
        bullish_touch = (
            above_cloud
            and lows[idx] <= kijun_val * (1 + self.params.kijun_touch_tolerance)
            and price >= kijun_val
            and not impulse
        )
        bearish_touch = (
            below_cloud
            and highs[idx] >= kijun_val * (1 - self.params.kijun_touch_tolerance)
            and price <= kijun_val
            and not impulse
        )
        if current_position is None:
            if bullish_touch:
                self._pending_touch[key] = {"bar_index": bar_index, "side": "BUY", "kijun": kijun_val}
                return self._hold("await_next_bar_confirmation")
            if bearish_touch:
                self._pending_touch[key] = {"bar_index": bar_index, "side": "SELL", "kijun": kijun_val}
                return self._hold("await_next_bar_confirmation")
        return self._hold("no_signal")


class CloudTwist(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: CloudTwistParams | None = None):
        self.params = params or CloudTwistParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "CloudTwist"

    @property
    def description(self) -> str:
        return "Kumo twist anticipation with confirmation"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        ichi = ichimoku(highs, lows, closes)
        sa, sb = ichi["senkou_a"], ichi["senkou_b"]
        twist_up = crossover(sa, sb, idx)
        twist_down = crossunder(sa, sb, idx)
        cloud_top, cloud_bottom = max(sa[idx], sb[idx]), min(sa[idx], sb[idx])
        bullish_confirm = self._breakout_confirm(price, cloud_top, current_atr, self.params.base.breakout_atr_mult, True)
        bearish_confirm = self._breakout_confirm(price, cloud_bottom, current_atr, self.params.base.breakout_atr_mult, False)
        if current_position == "long" and twist_down:
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["twist_bearish", "close_long"])
        if current_position == "short" and twist_up:
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["twist_bullish", "close_short"])
        if current_position is None:
            if regime == Regime.CHOP:
                return self._hold("regime_blocked")
            if twist_up and bullish_confirm:
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(direction="BUY", stop_loss=sl, take_profit=tp, reason_codes=["cloud_twist_up", "close_confirmed"], metadata={"regime": regime.value})
            if twist_down and bearish_confirm:
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(direction="SELL", stop_loss=sl, take_profit=tp, reason_codes=["cloud_twist_down", "close_confirmed"], metadata={"regime": regime.value})
        return self._hold("no_signal")


class MomentumRider(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: MomentumRiderParams | None = None):
        self.params = params or MomentumRiderParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "MomentumRider"

    @property
    def description(self) -> str:
        return "RSI + MACD momentum with Ichimoku filter"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        ichi = ichimoku(highs, lows, closes)
        sa, sb = ichi["senkou_a"], ichi["senkou_b"]
        above_cloud = is_price_above_cloud(price, sa[idx], sb[idx])
        below_cloud = is_price_below_cloud(price, sa[idx], sb[idx])
        rsi_values = rsi(closes, period=14)
        macd_line, signal_line, histogram = macd(closes)
        rsi_val = rsi_values[idx]
        hist_val = histogram[idx]
        hist_prev = histogram[idx - 1] if idx > 0 else hist_val
        bullish_event = crossover(macd_line, signal_line, idx) or (hist_prev <= 0 and hist_val > 0)
        bearish_event = crossunder(macd_line, signal_line, idx) or (hist_prev >= 0 and hist_val < 0)
        bullish = above_cloud and rsi_val > 50 and macd_line[idx] > signal_line[idx] and bullish_event
        bearish = below_cloud and rsi_val < 50 and macd_line[idx] < signal_line[idx] and bearish_event
        if current_position == "long" and (rsi_val > 75 or macd_line[idx] < signal_line[idx]):
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["momentum_exhausted", "close_long"])
        if current_position == "short" and (rsi_val < 25 or macd_line[idx] > signal_line[idx]):
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["momentum_exhausted", "close_short"])
        if current_position is None:
            if regime == Regime.CHOP:
                return self._hold("regime_blocked")
            if bullish:
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(direction="BUY", stop_loss=sl, take_profit=tp, confidence=min(1.0, (rsi_val - 50) / 20), reason_codes=["bullish_momentum", "fresh_macd_event"], metadata={"regime": regime.value})
            if bearish:
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(direction="SELL", stop_loss=sl, take_profit=tp, confidence=min(1.0, (50 - rsi_val) / 20), reason_codes=["bearish_momentum", "fresh_macd_event"], metadata={"regime": regime.value})
        return self._hold("no_signal")


class TrendSurfer(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: TrendSurferParams | None = None):
        self.params = params or TrendSurferParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "TrendSurfer"

    @property
    def description(self) -> str:
        return "EMA alignment with Ichimoku trend"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        regime, current_atr, _ = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        if regime != Regime.TRENDING:
            return self._hold("regime_blocked")
        ichi = ichimoku(highs, lows, closes)
        tenkan, kijun = ichi["tenkan"], ichi["kijun"]
        sa, sb = ichi["senkou_a"], ichi["senkou_b"]
        ema_20 = ema(closes, 20)
        ema_50 = ema(closes, 50)
        ema_bull = ema_20[idx] > ema_50[idx] and price > ema_20[idx]
        ema_bear = ema_20[idx] < ema_50[idx] and price < ema_20[idx]
        above_cloud = is_price_above_cloud(price, sa[idx], sb[idx])
        below_cloud = is_price_below_cloud(price, sa[idx], sb[idx])
        tk_bull = tenkan[idx] > kijun[idx]
        tk_bear = tenkan[idx] < kijun[idx]
        full_bull = ema_bull and above_cloud and tk_bull
        full_bear = ema_bear and below_cloud and tk_bear
        if current_position == "long" and (not ema_bull or not above_cloud):
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["trend_break", "close_long"])
        if current_position == "short" and (not ema_bear or not below_cloud):
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["trend_break", "close_short"])
        if current_position is None:
            ema_cross_up = crossover(ema_20, ema_50, idx)
            ema_cross_down = crossunder(ema_20, ema_50, idx)
            pullback_bull = (
                self.params.pullback_entry_enabled
                and full_bull
                and lows[idx] <= ema_20[idx]
                and price > ema_20[idx]
                and (idx == 0 or price > closes[idx - 1])
            )
            pullback_bear = (
                self.params.pullback_entry_enabled
                and full_bear
                and highs[idx] >= ema_20[idx]
                and price < ema_20[idx]
                and (idx == 0 or price < closes[idx - 1])
            )
            if full_bull and (ema_cross_up or pullback_bull):
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True, tp_atr_mult=3.0)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(direction="BUY", stop_loss=sl, take_profit=tp, reason_codes=["trend_aligned_up", "fresh_entry"])
            if full_bear and (ema_cross_down or pullback_bear):
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False, tp_atr_mult=3.0)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(direction="SELL", stop_loss=sl, take_profit=tp, reason_codes=["trend_aligned_down", "fresh_entry"])
        return self._hold("no_signal")


class ReversalHunter(Elite8BaseStrategy):
    def __init__(self, warmup_bars: int = 100, params: ReversalHunterParams | None = None):
        self.params = params or ReversalHunterParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "ReversalHunter"

    @property
    def description(self) -> str:
        return "Counter-trend reversal at extremes"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return self._hold("warmup")
        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, volumes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        price = closes[idx]
        regime, current_atr, atr_percent_value = self._compute_regime(
            highs, lows, closes, volumes, idx, self.params.base.regime_thresholds
        )
        if regime not in (Regime.CHOP, Regime.UNKNOWN):
            return self._hold("regime_blocked")
        if atr_percent_value >= self.params.explosive_atr_pct_block:
            return self._hold("volatility_blocked")
        ichi = ichimoku(highs, lows, closes)
        tenkan, kijun = ichi["tenkan"], ichi["kijun"]
        sa, sb = ichi["senkou_a"], ichi["senkou_b"]
        rsi_values = rsi(closes, period=14)
        rsi_val = rsi_values[idx]
        oversold, overbought = rsi_val < 30, rsi_val > 70
        price_lower_low = closes[idx] < min(closes[max(0, idx - 5) : idx]) if idx > 5 else False
        rsi_higher_low = rsi_val > min(rsi_values[max(0, idx - 5) : idx]) if idx > 5 else False
        price_higher_high = closes[idx] > max(closes[max(0, idx - 5) : idx]) if idx > 5 else False
        rsi_lower_high = rsi_val < max(rsi_values[max(0, idx - 5) : idx]) if idx > 5 else False
        bull_div = oversold and price_lower_low and rsi_higher_low
        bear_div = overbought and price_higher_high and rsi_lower_high
        tk_up = crossover(tenkan, kijun, idx)
        tk_down = crossunder(tenkan, kijun, idx)
        confirm_up = idx == 0 or closes[idx] > closes[idx - 1]
        confirm_down = idx == 0 or closes[idx] < closes[idx - 1]
        if current_position == "long":
            if is_price_above_cloud(price, sa[idx], sb[idx]) or rsi_val > 60:
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(direction="SELL", reason_codes=["reversal_complete", "close_long"])
        if current_position == "short":
            if is_price_below_cloud(price, sa[idx], sb[idx]) or rsi_val < 40:
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(direction="BUY", reason_codes=["reversal_complete", "close_short"])
        if current_position is None:
            if bull_div and tk_up and confirm_up:
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=True, sl_atr_mult=2.0)
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(direction="BUY", stop_loss=sl, take_profit=tp, confidence=0.7, reason_codes=["bullish_divergence", "reversal_confirmed"], metadata={"regime": regime.value})
            if bear_div and tk_down and confirm_down:
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(price, current_atr, is_long=False, sl_atr_mult=2.0)
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(direction="SELL", stop_loss=sl, take_profit=tp, confidence=0.7, reason_codes=["bearish_divergence", "reversal_confirmed"], metadata={"regime": regime.value})
        return self._hold("no_signal")


class ChikouKaizen(Elite8BaseStrategy):
    """
    Bot 9: Chikou Kaizen (AI Optimized)

    Logic: Chikou breakout entries with Chikou-touch exits.
    """

    def __init__(self, warmup_bars: int = 100, params: ChikouKaizenParams | None = None):
        self.params = params or ChikouKaizenParams()
        super().__init__(warmup_bars=warmup_bars, cooldown_bars=self.params.base.cooldown_bars)

    @property
    def name(self) -> str:
        return "ChikouKaizen"

    @property
    def description(self) -> str:
        return "Chikou breakout with touch exit and variable-risk metadata"

    def generate_signal(
        self, bars: Sequence[BarData], current_position: str | None = None, context: StrategyContext | None = None
    ) -> SignalIntent:
        displacement = self.params.displacement
        min_bars = max(self.warmup_bars, displacement + 2)
        if len(bars) < min_bars:
            return self._hold("warmup")

        key = self._context_key(context)
        bar_index = self._bar_index(bars, context)
        _, highs, lows, closes, _ = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]
        past_price = closes[idx - displacement]
        prev_price = closes[idx - 1]
        past_prev_price = closes[idx - displacement - 1]

        current_atr = atr(highs, lows, closes, period=14)[idx]
        chikou_break_up = prev_price <= past_prev_price and current_price > past_price
        chikou_break_down = prev_price >= past_prev_price and current_price < past_price
        chikou_touch_exit_long = current_price <= past_price
        chikou_touch_exit_short = current_price >= past_price

        if current_position == "long" and chikou_touch_exit_long:
            self._register_signal(key, bar_index, "SELL")
            return SignalIntent(direction="SELL", reason_codes=["chikou_touch_exit", "close_long"])
        if current_position == "short" and chikou_touch_exit_short:
            self._register_signal(key, bar_index, "BUY")
            return SignalIntent(direction="BUY", reason_codes=["chikou_touch_exit", "close_short"])

        if current_position is None:
            if chikou_break_up:
                gate = self._entry_gate(key, bar_index, "BUY", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(
                    current_price,
                    current_atr,
                    is_long=True,
                    sl_atr_mult=self.params.sl_atr_mult,
                    tp_atr_mult=self.params.tp_atr_mult,
                )
                self._register_signal(key, bar_index, "BUY")
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["chikou_breakout_up"],
                    metadata={"risk_after_win_pct": 3.0, "risk_after_loss_pct": 2.0},
                )
            if chikou_break_down:
                gate = self._entry_gate(key, bar_index, "SELL", self.cooldown_bars)
                if gate is not None:
                    return gate
                sl, tp = self._calculate_sl_tp(
                    current_price,
                    current_atr,
                    is_long=False,
                    sl_atr_mult=self.params.sl_atr_mult,
                    tp_atr_mult=self.params.tp_atr_mult,
                )
                self._register_signal(key, bar_index, "SELL")
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["chikou_breakout_down"],
                    metadata={"risk_after_win_pct": 3.0, "risk_after_loss_pct": 2.0},
                )

        return self._hold("no_signal")


ELITE_8_BOTS: dict[str, type[Elite8BaseStrategy]] = {
    "TKCrossSniper": TKCrossSniper,
    "KumoBreaker": KumoBreaker,
    "ChikouConfirmer": ChikouConfirmer,
    "KijunBouncer": KijunBouncer,
    "CloudTwist": CloudTwist,
    "MomentumRider": MomentumRider,
    "TrendSurfer": TrendSurfer,
    "ReversalHunter": ReversalHunter,
    "ChikouKaizen": ChikouKaizen,
}


class Elite8StrategyFactory:
    @staticmethod
    def create(name: str, warmup_bars: int = 100, params: Any | None = None) -> Elite8BaseStrategy:
        if name not in ELITE_8_BOTS:
            available = ", ".join(ELITE_8_BOTS.keys())
            raise ValueError(f"Unknown bot '{name}'. Available: {available}")
        if params is None:
            return ELITE_8_BOTS[name](warmup_bars=warmup_bars)
        return ELITE_8_BOTS[name](warmup_bars=warmup_bars, params=params)

    @staticmethod
    def list_bots() -> list[str]:
        return list(ELITE_8_BOTS.keys())

    @staticmethod
    def get_bot_info() -> list[dict[str, str]]:
        return [{"name": name, "description": cls().description} for name, cls in ELITE_8_BOTS.items()]


def get_available_bots() -> list[str]:
    return Elite8StrategyFactory.list_bots()
