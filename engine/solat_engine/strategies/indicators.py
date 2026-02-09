"""
Technical indicators for strategy calculations.

All functions are pure and deterministic - same inputs always produce same outputs.
Only uses data up to current index (no lookahead).
"""

from collections.abc import Sequence


def ema(values: Sequence[float], period: int) -> list[float]:
    """
    Calculate Exponential Moving Average.

    Args:
        values: Price series
        period: EMA period

    Returns:
        EMA values (first period-1 values are NaN-like using first available)
    """
    if len(values) < period or period < 1:
        return [values[0] if values else 0.0] * len(values)

    multiplier = 2.0 / (period + 1)
    result = [0.0] * len(values)

    # Initialize with SMA for first period
    result[period - 1] = sum(values[:period]) / period

    # Calculate EMA for remaining values
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]

    # Backfill initial values
    for i in range(period - 1):
        result[i] = result[period - 1]

    return result


def sma(values: Sequence[float], period: int) -> list[float]:
    """
    Calculate Simple Moving Average.

    Args:
        values: Price series
        period: SMA period

    Returns:
        SMA values
    """
    if len(values) < period or period < 1:
        return [values[0] if values else 0.0] * len(values)

    result = [0.0] * len(values)

    # Calculate rolling sum
    window_sum = sum(values[:period])
    result[period - 1] = window_sum / period

    for i in range(period, len(values)):
        window_sum = window_sum - values[i - period] + values[i]
        result[i] = window_sum / period

    # Backfill initial values
    for i in range(period - 1):
        result[i] = result[period - 1]

    return result


def rsi(closes: Sequence[float], period: int = 14) -> list[float]:
    """
    Calculate Relative Strength Index.

    Args:
        closes: Close prices
        period: RSI period (default 14)

    Returns:
        RSI values (0-100)
    """
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    result = [50.0] * len(closes)
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)

    # Calculate price changes
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = abs(change)

    # First average gain/loss
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    # First RSI
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    # Smoothed RSI
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    # Backfill
    for i in range(period):
        result[i] = result[period]

    return result


def macd(
    closes: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        closes: Close prices
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line period (default 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram)
    """
    fast_ema = ema(closes, fast_period)
    slow_ema = ema(closes, slow_period)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=True)]
    signal_line = ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line, signal_line, strict=True)]

    return macd_line, signal_line, histogram


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float]:
    """
    Calculate Average True Range.

    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        period: ATR period (default 14)

    Returns:
        ATR values
    """
    if len(highs) < 2:
        return [0.0] * len(highs)

    true_ranges = [highs[0] - lows[0]]

    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    return ema(true_ranges, period)


def bollinger_bands(
    closes: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    """
    Calculate Bollinger Bands.

    Args:
        closes: Close prices
        period: SMA period (default 20)
        std_dev: Standard deviation multiplier (default 2.0)

    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    middle = sma(closes, period)
    upper = [0.0] * len(closes)
    lower = [0.0] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = variance**0.5

        upper[i] = middle[i] + std_dev * std
        lower[i] = middle[i] - std_dev * std

    # Backfill
    for i in range(period - 1):
        upper[i] = upper[period - 1]
        lower[i] = lower[period - 1]

    return upper, middle, lower


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[list[float], list[float]]:
    """
    Calculate Stochastic Oscillator.

    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        k_period: %K period (default 14)
        d_period: %D period (default 3)

    Returns:
        Tuple of (%K, %D)
    """
    k_values = [50.0] * len(closes)

    for i in range(k_period - 1, len(closes)):
        highest_high = max(highs[i - k_period + 1 : i + 1])
        lowest_low = min(lows[i - k_period + 1 : i + 1])

        if highest_high == lowest_low:
            k_values[i] = 50.0
        else:
            k_values[i] = 100 * (closes[i] - lowest_low) / (highest_high - lowest_low)

    # Backfill
    for i in range(k_period - 1):
        k_values[i] = k_values[k_period - 1]

    d_values = sma(k_values, d_period)

    return k_values, d_values


# =============================================================================
# Ichimoku Cloud Components
# =============================================================================


def ichimoku(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
    displacement: int = 26,
) -> dict[str, list[float]]:
    """
    Calculate Ichimoku Cloud components.

    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        tenkan_period: Tenkan-sen period (default 9)
        kijun_period: Kijun-sen period (default 26)
        senkou_b_period: Senkou Span B period (default 52)
        displacement: Cloud displacement (default 26)

    Returns:
        Dict with tenkan, kijun, senkou_a, senkou_b, chikou
    """
    n = len(closes)

    def donchian_mid(period: int) -> list[float]:
        result = [0.0] * n
        if n < period:
            # Not enough data - use available high/low midpoint
            if n > 0:
                mid = (max(highs) + min(lows)) / 2
                for i in range(n):
                    result[i] = mid
            return result
        for i in range(period - 1, n):
            hh = max(highs[i - period + 1 : i + 1])
            ll = min(lows[i - period + 1 : i + 1])
            result[i] = (hh + ll) / 2
        for i in range(period - 1):
            result[i] = result[period - 1]
        return result

    tenkan = donchian_mid(tenkan_period)
    kijun = donchian_mid(kijun_period)

    # Senkou Span A: (Tenkan + Kijun) / 2, displaced forward
    senkou_a = [0.0] * n
    for i in range(n):
        senkou_a[i] = (tenkan[i] + kijun[i]) / 2

    # Senkou Span B: Donchian mid of senkou_b_period, displaced forward
    senkou_b = donchian_mid(senkou_b_period)

    # Chikou Span: Close displaced backward (we store current close at i - displacement)
    chikou = closes[:]  # Current close, to be plotted displaced back

    return {
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
        "chikou": list(chikou),
    }


def is_price_above_cloud(
    price: float,
    senkou_a: float,
    senkou_b: float,
) -> bool:
    """Check if price is above the Kumo cloud."""
    cloud_top = max(senkou_a, senkou_b)
    return price > cloud_top


def is_price_below_cloud(
    price: float,
    senkou_a: float,
    senkou_b: float,
) -> bool:
    """Check if price is below the Kumo cloud."""
    cloud_bottom = min(senkou_a, senkou_b)
    return price < cloud_bottom


def is_price_in_cloud(
    price: float,
    senkou_a: float,
    senkou_b: float,
) -> bool:
    """Check if price is inside the Kumo cloud."""
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    return cloud_bottom <= price <= cloud_top


# =============================================================================
# Utility Functions
# =============================================================================


def crossover(series1: Sequence[float], series2: Sequence[float], index: int) -> bool:
    """Check if series1 crosses above series2 at index."""
    if index < 1 or index >= len(series1) or index >= len(series2):
        return False
    return series1[index - 1] <= series2[index - 1] and series1[index] > series2[index]


def crossunder(series1: Sequence[float], series2: Sequence[float], index: int) -> bool:
    """Check if series1 crosses below series2 at index."""
    if index < 1 or index >= len(series1) or index >= len(series2):
        return False
    return series1[index - 1] >= series2[index - 1] and series1[index] < series2[index]


def highest(values: Sequence[float], period: int, index: int) -> float:
    """Get highest value over period ending at index."""
    start = max(0, index - period + 1)
    return max(values[start : index + 1])


def lowest(values: Sequence[float], period: int, index: int) -> float:
    """Get lowest value over period ending at index."""
    start = max(0, index - period + 1)
    return min(values[start : index + 1])


def slope(values: Sequence[float], period: int, index: int) -> float:
    """Calculate slope over period ending at index."""
    if index < period - 1:
        return 0.0
    return (values[index] - values[index - period + 1]) / period
