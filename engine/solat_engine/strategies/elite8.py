"""
Elite 8 Strategy Suite.

Eight Ichimoku-based trading strategies, each with distinct entry/exit logic.
All strategies are deterministic and use only past/current bar data.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from solat_engine.backtest.models import SignalIntent
from solat_engine.strategies.indicators import (
    atr,
    crossover,
    crossunder,
    ema,
    ichimoku,
    is_price_above_cloud,
    is_price_below_cloud,
    macd,
    rsi,
)


@dataclass
class BarData:
    """Simple bar data structure for strategy calculations."""

    timestamp: Any
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class Elite8BaseStrategy(ABC):
    """Base class for Elite 8 strategies."""

    def __init__(self, warmup_bars: int = 100):
        self.warmup_bars = warmup_bars

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Strategy description."""
        pass

    @abstractmethod
    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,  # "long", "short", or None
    ) -> SignalIntent:
        """
        Generate trading signal from bar data.

        Args:
            bars: Historical bars up to current (inclusive)
            current_position: Current position side if any

        Returns:
            SignalIntent with direction, SL/TP, and reason codes
        """
        pass

    def _extract_ohlc(
        self, bars: Sequence[BarData]
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Extract OHLC arrays from bars."""
        opens = [b.open for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        return opens, highs, lows, closes

    def _calculate_sl_tp(
        self,
        entry_price: float,
        atr_value: float,
        is_long: bool,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.0,
    ) -> tuple[float, float]:
        """Calculate stop loss and take profit based on ATR."""
        if is_long:
            sl = entry_price - (atr_value * sl_atr_mult)
            tp = entry_price + (atr_value * tp_atr_mult)
        else:
            sl = entry_price + (atr_value * sl_atr_mult)
            tp = entry_price - (atr_value * tp_atr_mult)
        return sl, tp


# =============================================================================
# Elite 8 Strategy Implementations
# =============================================================================


class TKCrossSniper(Elite8BaseStrategy):
    """
    Bot 1: Tenkan-Kijun Cross Sniper

    Entry: Tenkan crosses Kijun with price above/below cloud for confirmation.
    Exit: Opposite cross or cloud entry.
    """

    @property
    def name(self) -> str:
        return "TKCrossSniper"

    @property
    def description(self) -> str:
        return "Tenkan-Kijun cross with cloud confirmation"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate Ichimoku
        ichi = ichimoku(highs, lows, closes)
        tenkan = ichi["tenkan"]
        kijun = ichi["kijun"]
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        # Calculate ATR for SL/TP
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Check for TK cross
        tk_cross_up = crossover(tenkan, kijun, idx)
        tk_cross_down = crossunder(tenkan, kijun, idx)

        above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])

        # Exit logic
        if current_position == "long" and (tk_cross_down or below_cloud):
            return SignalIntent(direction="SELL", reason_codes=["tk_cross_exit", "close_long"])

        if current_position == "short" and (tk_cross_up or above_cloud):
            return SignalIntent(direction="BUY", reason_codes=["tk_cross_exit", "close_short"])

        # Entry logic
        if current_position is None:
            if tk_cross_up and above_cloud:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["tk_cross_up", "above_cloud"],
                )

            if tk_cross_down and below_cloud:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["tk_cross_down", "below_cloud"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class KumoBreaker(Elite8BaseStrategy):
    """
    Bot 2: Kumo Breaker

    Entry: Price breaks out of the Kumo cloud with momentum confirmation.
    Exit: Price re-enters cloud or opposite breakout.
    """

    @property
    def name(self) -> str:
        return "KumoBreaker"

    @property
    def description(self) -> str:
        return "Cloud breakout with momentum confirmation"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]
        prev_price = closes[idx - 1] if idx > 0 else current_price

        # Calculate Ichimoku
        ichi = ichimoku(highs, lows, closes)
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        # ATR for SL/TP
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Cloud levels
        cloud_top = max(senkou_a[idx], senkou_b[idx])
        cloud_bottom = min(senkou_a[idx], senkou_b[idx])
        prev_cloud_top = max(senkou_a[idx - 1], senkou_b[idx - 1])
        prev_cloud_bottom = min(senkou_a[idx - 1], senkou_b[idx - 1])

        # Breakout detection
        broke_above = prev_price <= prev_cloud_top and current_price > cloud_top
        broke_below = prev_price >= prev_cloud_bottom and current_price < cloud_bottom

        # Re-entry detection
        in_cloud = cloud_bottom <= current_price <= cloud_top

        # Exit logic
        if current_position == "long" and (in_cloud or broke_below):
            return SignalIntent(direction="SELL", reason_codes=["kumo_reentry", "close_long"])

        if current_position == "short" and (in_cloud or broke_above):
            return SignalIntent(direction="BUY", reason_codes=["kumo_reentry", "close_short"])

        # Entry logic
        if current_position is None:
            if broke_above:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True, sl_atr_mult=2.0)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kumo_breakout_up"],
                )

            if broke_below:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False, sl_atr_mult=2.0)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kumo_breakout_down"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class ChikouConfirmer(Elite8BaseStrategy):
    """
    Bot 3: Chikou Confirmer

    Entry: Chikou Span confirms trend by crossing price from 26 bars ago.
    Exit: Chikou loses confirmation.
    """

    @property
    def name(self) -> str:
        return "ChikouConfirmer"

    @property
    def description(self) -> str:
        return "Chikou Span trend confirmation"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]
        displacement = 26

        if idx < displacement:
            return SignalIntent(direction="HOLD", reason_codes=["insufficient_data"])

        # Chikou is current close compared to price 26 bars ago
        chikou_current = current_price
        price_26_ago = closes[idx - displacement]
        chikou_prev = closes[idx - 1] if idx > 0 else current_price
        price_27_ago = closes[idx - displacement - 1] if idx > displacement else price_26_ago

        # ATR for SL/TP
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Chikou crosses above/below historical price
        chikou_cross_up = chikou_prev <= price_27_ago and chikou_current > price_26_ago
        chikou_cross_down = chikou_prev >= price_27_ago and chikou_current < price_26_ago

        # Exit logic
        if current_position == "long" and chikou_cross_down:
            return SignalIntent(direction="SELL", reason_codes=["chikou_lost_confirm", "close_long"])

        if current_position == "short" and chikou_cross_up:
            return SignalIntent(direction="BUY", reason_codes=["chikou_lost_confirm", "close_short"])

        # Entry logic
        if current_position is None:
            if chikou_cross_up:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["chikou_confirm_up"],
                )

            if chikou_cross_down:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["chikou_confirm_down"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class KijunBouncer(Elite8BaseStrategy):
    """
    Bot 4: Kijun Bouncer

    Entry: Price bounces off Kijun-sen in trending conditions.
    Exit: Price breaks Kijun decisively.
    """

    @property
    def name(self) -> str:
        return "KijunBouncer"

    @property
    def description(self) -> str:
        return "Kijun-sen bounce in trend"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate Ichimoku
        ichi = ichimoku(highs, lows, closes)
        kijun = ichi["kijun"]
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        # ATR
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Trend determination
        above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])

        # Bounce detection (price touches Kijun and bounces)
        kijun_val = kijun[idx]
        low = lows[idx]
        high = highs[idx]

        # Bullish bounce: low touched Kijun, close above it
        bullish_bounce = (
            above_cloud
            and low <= kijun_val * 1.001  # Allow small tolerance
            and current_price > kijun_val
            and current_price > closes[idx - 1] if idx > 0 else True
        )

        # Bearish bounce: high touched Kijun, close below it
        bearish_bounce = (
            below_cloud
            and high >= kijun_val * 0.999
            and current_price < kijun_val
            and current_price < closes[idx - 1] if idx > 0 else True
        )

        # Exit: price breaks Kijun decisively
        if current_position == "long" and current_price < kijun_val * 0.995:
            return SignalIntent(direction="SELL", reason_codes=["kijun_break", "close_long"])

        if current_position == "short" and current_price > kijun_val * 1.005:
            return SignalIntent(direction="BUY", reason_codes=["kijun_break", "close_short"])

        # Entry logic
        if current_position is None:
            if bullish_bounce:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kijun_bounce_up"],
                )

            if bearish_bounce:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["kijun_bounce_down"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class CloudTwist(Elite8BaseStrategy):
    """
    Bot 5: Cloud Twist

    Entry: Senkou A crosses Senkou B (future cloud twist) with current trend confirmation.
    Exit: Opposite twist or trend reversal.
    """

    @property
    def name(self) -> str:
        return "CloudTwist"

    @property
    def description(self) -> str:
        return "Kumo twist anticipation"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate Ichimoku
        ichi = ichimoku(highs, lows, closes)
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        # ATR
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Cloud twist detection
        twist_bullish = crossover(senkou_a, senkou_b, idx)
        twist_bearish = crossunder(senkou_a, senkou_b, idx)

        # Current trend
        above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])

        # Exit logic
        if current_position == "long" and twist_bearish:
            return SignalIntent(direction="SELL", reason_codes=["twist_bearish", "close_long"])

        if current_position == "short" and twist_bullish:
            return SignalIntent(direction="BUY", reason_codes=["twist_bullish", "close_short"])

        # Entry logic
        if current_position is None:
            if twist_bullish and above_cloud:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["cloud_twist_up", "above_cloud"],
                )

            if twist_bearish and below_cloud:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["cloud_twist_down", "below_cloud"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class MomentumRider(Elite8BaseStrategy):
    """
    Bot 6: Momentum Rider

    Entry: Strong momentum (RSI + MACD) with Ichimoku trend confirmation.
    Exit: Momentum exhaustion or trend reversal.
    """

    @property
    def name(self) -> str:
        return "MomentumRider"

    @property
    def description(self) -> str:
        return "RSI + MACD momentum with Ichimoku filter"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate indicators
        ichi = ichimoku(highs, lows, closes)
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        rsi_values = rsi(closes, period=14)
        macd_line, signal_line, histogram = macd(closes)

        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # Conditions
        rsi_val = rsi_values[idx]
        macd_val = macd_line[idx]
        signal_val = signal_line[idx]
        hist_val = histogram[idx]
        hist_prev = histogram[idx - 1] if idx > 0 else 0

        above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])

        # Strong bullish momentum
        bullish_momentum = (
            above_cloud
            and rsi_val > 50
            and rsi_val < 70  # Not overbought
            and macd_val > signal_val
            and hist_val > hist_prev  # Increasing momentum
        )

        # Strong bearish momentum
        bearish_momentum = (
            below_cloud
            and rsi_val < 50
            and rsi_val > 30  # Not oversold
            and macd_val < signal_val
            and hist_val < hist_prev  # Increasing momentum
        )

        # Exit: momentum exhaustion
        if current_position == "long" and (rsi_val > 70 or macd_val < signal_val):
            return SignalIntent(direction="SELL", reason_codes=["momentum_exhausted", "close_long"])

        if current_position == "short" and (rsi_val < 30 or macd_val > signal_val):
            return SignalIntent(direction="BUY", reason_codes=["momentum_exhausted", "close_short"])

        # Entry logic
        if current_position is None:
            if bullish_momentum:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=min(1.0, (rsi_val - 50) / 20),
                    reason_codes=["bullish_momentum"],
                )

            if bearish_momentum:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=min(1.0, (50 - rsi_val) / 20),
                    reason_codes=["bearish_momentum"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class TrendSurfer(Elite8BaseStrategy):
    """
    Bot 7: Trend Surfer

    Entry: EMA alignment with Ichimoku trend for sustained moves.
    Exit: EMA or Ichimoku trend reversal.
    """

    @property
    def name(self) -> str:
        return "TrendSurfer"

    @property
    def description(self) -> str:
        return "EMA alignment with Ichimoku trend"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate indicators
        ichi = ichimoku(highs, lows, closes)
        tenkan = ichi["tenkan"]
        kijun = ichi["kijun"]
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        ema_20 = ema(closes, 20)
        ema_50 = ema(closes, 50)

        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        # EMA alignment
        ema_bullish = ema_20[idx] > ema_50[idx] and current_price > ema_20[idx]
        ema_bearish = ema_20[idx] < ema_50[idx] and current_price < ema_20[idx]

        # Ichimoku trend
        above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
        below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])
        tk_bullish = tenkan[idx] > kijun[idx]
        tk_bearish = tenkan[idx] < kijun[idx]

        # Full alignment
        full_bullish = ema_bullish and above_cloud and tk_bullish
        full_bearish = ema_bearish and below_cloud and tk_bearish

        # Exit: alignment breaks
        if current_position == "long" and (not ema_bullish or not above_cloud):
            return SignalIntent(direction="SELL", reason_codes=["trend_break", "close_long"])

        if current_position == "short" and (not ema_bearish or not below_cloud):
            return SignalIntent(direction="BUY", reason_codes=["trend_break", "close_short"])

        # Entry logic (require fresh alignment via EMA cross)
        if current_position is None:
            ema_cross_up = crossover(ema_20, ema_50, idx)
            ema_cross_down = crossunder(ema_20, ema_50, idx)

            if full_bullish and ema_cross_up:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True, tp_atr_mult=3.0)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["trend_aligned_up"],
                )

            if full_bearish and ema_cross_down:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False, tp_atr_mult=3.0)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    reason_codes=["trend_aligned_down"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


class ReversalHunter(Elite8BaseStrategy):
    """
    Bot 8: Reversal Hunter

    Entry: Counter-trend signals at extremes with Ichimoku confirmation.
    Exit: Reversal completes or fails.
    """

    @property
    def name(self) -> str:
        return "ReversalHunter"

    @property
    def description(self) -> str:
        return "Counter-trend reversal at extremes"

    def generate_signal(
        self,
        bars: Sequence[BarData],
        current_position: str | None = None,
    ) -> SignalIntent:
        if len(bars) < self.warmup_bars:
            return SignalIntent(direction="HOLD", reason_codes=["warmup"])

        _, highs, lows, closes = self._extract_ohlc(bars)
        idx = len(bars) - 1
        current_price = closes[idx]

        # Calculate indicators
        ichi = ichimoku(highs, lows, closes)
        tenkan = ichi["tenkan"]
        kijun = ichi["kijun"]
        senkou_a = ichi["senkou_a"]
        senkou_b = ichi["senkou_b"]

        rsi_values = rsi(closes, period=14)
        atr_values = atr(highs, lows, closes, period=14)
        current_atr = atr_values[idx]

        rsi_val = rsi_values[idx]

        # Extreme conditions
        oversold = rsi_val < 30
        overbought = rsi_val > 70

        # RSI divergence (price makes new low but RSI doesn't)
        price_lower_low = closes[idx] < min(closes[max(0, idx - 5) : idx]) if idx > 5 else False
        rsi_higher_low = rsi_val > min(rsi_values[max(0, idx - 5) : idx]) if idx > 5 else False
        bullish_divergence = oversold and price_lower_low and rsi_higher_low

        price_higher_high = closes[idx] > max(closes[max(0, idx - 5) : idx]) if idx > 5 else False
        rsi_lower_high = rsi_val < max(rsi_values[max(0, idx - 5) : idx]) if idx > 5 else False
        bearish_divergence = overbought and price_higher_high and rsi_lower_high

        # TK cross as confirmation
        tk_cross_up = crossover(tenkan, kijun, idx)
        tk_cross_down = crossunder(tenkan, kijun, idx)

        # Exit: reversal completes (reaches cloud) or fails
        if current_position == "long":
            above_cloud = is_price_above_cloud(current_price, senkou_a[idx], senkou_b[idx])
            if above_cloud or rsi_val > 60:
                return SignalIntent(direction="SELL", reason_codes=["reversal_complete", "close_long"])

        if current_position == "short":
            below_cloud = is_price_below_cloud(current_price, senkou_a[idx], senkou_b[idx])
            if below_cloud or rsi_val < 40:
                return SignalIntent(direction="BUY", reason_codes=["reversal_complete", "close_short"])

        # Entry logic
        if current_position is None:
            if bullish_divergence and tk_cross_up:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=True, sl_atr_mult=2.0)
                return SignalIntent(
                    direction="BUY",
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=0.7,  # Lower confidence for reversals
                    reason_codes=["bullish_divergence", "reversal"],
                )

            if bearish_divergence and tk_cross_down:
                sl, tp = self._calculate_sl_tp(current_price, current_atr, is_long=False, sl_atr_mult=2.0)
                return SignalIntent(
                    direction="SELL",
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=0.7,
                    reason_codes=["bearish_divergence", "reversal"],
                )

        return SignalIntent(direction="HOLD", reason_codes=["no_signal"])


# =============================================================================
# Factory and Registry
# =============================================================================

ELITE_8_BOTS: dict[str, type[Elite8BaseStrategy]] = {
    "TKCrossSniper": TKCrossSniper,
    "KumoBreaker": KumoBreaker,
    "ChikouConfirmer": ChikouConfirmer,
    "KijunBouncer": KijunBouncer,
    "CloudTwist": CloudTwist,
    "MomentumRider": MomentumRider,
    "TrendSurfer": TrendSurfer,
    "ReversalHunter": ReversalHunter,
}


class Elite8StrategyFactory:
    """Factory for creating Elite 8 strategy instances."""

    @staticmethod
    def create(name: str, warmup_bars: int = 100) -> Elite8BaseStrategy:
        """
        Create a strategy instance by name.

        Args:
            name: Bot name (e.g., "TKCrossSniper")
            warmup_bars: Number of warmup bars

        Returns:
            Strategy instance

        Raises:
            ValueError: If bot name is unknown
        """
        if name not in ELITE_8_BOTS:
            available = ", ".join(ELITE_8_BOTS.keys())
            raise ValueError(f"Unknown bot '{name}'. Available: {available}")

        return ELITE_8_BOTS[name](warmup_bars=warmup_bars)

    @staticmethod
    def list_bots() -> list[str]:
        """Get list of available bot names."""
        return list(ELITE_8_BOTS.keys())

    @staticmethod
    def get_bot_info() -> list[dict[str, str]]:
        """Get info about all available bots."""
        info = []
        for name, cls in ELITE_8_BOTS.items():
            instance = cls()
            info.append({
                "name": name,
                "description": instance.description,
            })
        return info


def get_available_bots() -> list[str]:
    """Get list of available Elite 8 bot names."""
    return Elite8StrategyFactory.list_bots()
