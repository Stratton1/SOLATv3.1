"""Quick before/after-style trade count comparison for hardened Elite 8 bots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile

from solat_engine.backtest.engine import BacktestEngineV1
from solat_engine.backtest.models import BacktestRequest
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.strategies.elite8_hardened import (
    BaseHardeningParams,
    KijunBouncer,
    KijunBouncerParams,
    KumoBreaker,
    KumoBreakerParams,
    TKCrossSniper,
    TKCrossSniperParams,
)


def build_demo_bars(n: int = 500) -> list[HistoricalBar]:
    start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    bars: list[HistoricalBar] = []
    base = 1.1000
    for i in range(n):
        ts = start + timedelta(minutes=i)
        # Deterministic mixed regime sequence.
        if i < n // 3:
            close = base + ((i % 10) - 5) * 0.00008
        elif i < 2 * n // 3:
            close = base + 0.002 + ((i - n // 3) * 0.00012)
        else:
            close = base + 0.01 + ((i % 12) - 6) * 0.0001
        bars.append(
            HistoricalBar(
                timestamp_utc=ts,
                instrument_symbol="EURUSD",
                timeframe=SupportedTimeframe.M1,
                open=close - 0.00005,
                high=close + 0.0002,
                low=close - 0.0002,
                close=close,
                volume=100.0 + (i % 11),
            )
        )
    return bars


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base_path = Path(tmp)
        store = ParquetStore(base_path)
        bars = build_demo_bars()
        store.write_bars(bars)

        engine = BacktestEngineV1(parquet_store=store, artefacts_dir=base_path)
        request = BacktestRequest(
            symbols=["EURUSD"],
            timeframe="1m",
            start=bars[0].timestamp_utc,
            end=bars[-1].timestamp_utc,
            bots=["TKCrossSniper", "KumoBreaker", "KijunBouncer"],
            initial_cash=100000.0,
            warmup_bars=80,
        )
        hardened = engine.run(request)

        # Legacy-like permissive settings for rough comparison.
        permissive_base = BaseHardeningParams(cooldown_bars=0, breakout_atr_mult=0.0)
        legacy_like = {
            "TKCrossSniper": TKCrossSniper(params=TKCrossSniperParams(base=permissive_base)),
            "KumoBreaker": KumoBreaker(params=KumoBreakerParams(base=permissive_base)),
            "KijunBouncer": KijunBouncer(
                params=KijunBouncerParams(
                    base=permissive_base,
                    impulse_atr_mult=100.0,
                    kijun_touch_tolerance=0.002,
                )
            ),
        }

        print("hardened_results")
        for bot_result in hardened.per_bot_results:
            trades = bot_result.metrics.total_trades
            trades_per_1000 = (trades / len(bars)) * 1000
            print(
                f"{bot_result.bot}: trades={trades} trades_per_1000={trades_per_1000:.2f} "
                f"sharpe={bot_result.metrics.sharpe_ratio:.3f}"
            )

        print("legacy_like_signal_counts")
        for name, strategy in legacy_like.items():
            position = None
            entries = 0
            for i in range(len(bars)):
                from solat_engine.strategies.elite8_hardened import BarData, StrategyContext

                signal = strategy.generate_signal(
                    [
                        BarData(
                            timestamp=b.timestamp_utc,
                            open=b.open,
                            high=b.high,
                            low=b.low,
                            close=b.close,
                            volume=b.volume,
                        )
                        for b in bars[: i + 1]
                    ],
                    current_position=position,
                    context=StrategyContext(symbol="EURUSD", timeframe="1m", bar_index=i, bot_name=name),
                )
                if position is None and signal.direction in ("BUY", "SELL"):
                    position = "long" if signal.direction == "BUY" else "short"
                    entries += 1
                elif position == "long" and signal.direction == "SELL":
                    position = None
                elif position == "short" and signal.direction == "BUY":
                    position = None
            entries_per_1000 = (entries / len(bars)) * 1000
            print(f"{name}: entries={entries} entries_per_1000={entries_per_1000:.2f}")


if __name__ == "__main__":
    main()
