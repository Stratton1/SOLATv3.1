"""
Regression tests for sweep output: ensure core sweep_utils functions
produce non-empty output given valid fixture data.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from solat_engine.backtest.sweep_utils import (
    detect_broken_bots,
    generate_curated_allowlist,
    generate_ranked_csv,
)


def _make_fixture_results() -> pd.DataFrame:
    """Create a realistic sweep results DataFrame with multiple bots/symbols/timeframes."""
    rows = []
    bots = ["TKCrossSniper", "KumoBreaker", "CloudTwist", "MomentumRider"]
    symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    timeframes = ["1h", "4h"]

    for i, bot in enumerate(bots):
        for j, symbol in enumerate(symbols):
            for k, tf in enumerate(timeframes):
                sharpe = 2.5 - i * 0.3 + j * 0.1 - k * 0.05
                rows.append({
                    "bot": bot,
                    "symbol": symbol,
                    "timeframe": tf,
                    "success": True,
                    "skipped": False,
                    "total_trades": 60 + i * 10 + j * 5,
                    "sharpe": round(sharpe, 3),
                    "win_rate": 0.52 + i * 0.01,
                    "max_drawdown": -0.05 - i * 0.01,
                    "pnl": 1000 - i * 200 + j * 50,
                    "sortino": sharpe * 1.2,
                    "profit_factor": 1.5 + sharpe * 0.1,
                    "avg_trade_pnl": (1000 - i * 200) / (60 + i * 10),
                })

    return pd.DataFrame(rows)


class TestGenerateRankedCsvNonEmpty:
    """Regression: ranked CSV should be non-empty for valid fixture data."""

    def test_non_empty_output(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        assert len(ranked) > 0, "ranked output should not be empty for valid data"
        assert (tmp_path / "ranked.csv").exists()

    def test_rank_column_present(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        assert "rank" in ranked.columns
        assert ranked.iloc[0]["rank"] == 1

    def test_sorted_by_sharpe_desc(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        sharpes = ranked["sharpe"].tolist()
        assert sharpes == sorted(sharpes, reverse=True)


class TestDetectBrokenBotsNonEmpty:
    """Regression: healthy data should produce 0 broken bots."""

    def test_no_broken_bots(self) -> None:
        df = _make_fixture_results()
        result = detect_broken_bots(df, zero_trade_threshold=0.5)
        assert result["broken_bots_count"] == 0
        assert result["total_bots"] == 4

    def test_detects_broken_bot(self) -> None:
        df = _make_fixture_results()
        # Make one bot have all zero trades
        df.loc[df["bot"] == "MomentumRider", "total_trades"] = 0
        result = detect_broken_bots(df, zero_trade_threshold=0.5)
        assert result["broken_bots_count"] == 1
        assert result["broken_bots"][0]["bot"] == "MomentumRider"


class TestGenerateCuratedAllowlistNonEmpty:
    """Regression: curated allowlist should be non-empty for valid ranked data."""

    def test_non_empty_output(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            max_per_symbol=3, max_per_bot=5,
        )
        assert len(allowlist["symbols"]) > 0, "allowlist should not be empty"
        assert (tmp_path / "allowlist.json").exists()

    def test_excludes_broken_bots(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            broken_bots=["TKCrossSniper"],
        )
        # Verify excluded bot not in any picks
        for symbol_data in allowlist["symbols"].values():
            for tf_bots in symbol_data.values():
                for entry in tf_bots:
                    assert entry["bot"] != "TKCrossSniper"

    def test_max_per_bot_limit(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            max_per_bot=2,
        )
        # Count per bot across all symbols/timeframes
        bot_counts: dict[str, int] = {}
        for symbol_data in allowlist["symbols"].values():
            for tf_bots in symbol_data.values():
                for entry in tf_bots:
                    bot_counts[entry["bot"]] = bot_counts.get(entry["bot"], 0) + 1
        for bot, count in bot_counts.items():
            assert count <= 2, f"{bot} has {count} entries, expected <= 2"

    def test_max_per_timeframe_limit(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            max_per_timeframe=3,
        )
        # Count per timeframe across all symbols
        tf_counts: dict[str, int] = {}
        for symbol_data in allowlist["symbols"].values():
            for tf, tf_bots in symbol_data.items():
                tf_counts[tf] = tf_counts.get(tf, 0) + len(tf_bots)
        for tf, count in tf_counts.items():
            assert count <= 3, f"timeframe {tf} has {count} entries, expected <= 3"

    def test_max_per_timeframe_none_is_unlimited(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            max_per_timeframe=None,
        )
        assert len(allowlist["symbols"]) > 0

    def test_filters_in_output(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        allowlist = generate_curated_allowlist(
            ranked, tmp_path / "allowlist.json",
            max_per_timeframe=5,
        )
        assert allowlist["filters"]["max_per_timeframe"] == 5

    def test_json_readable(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        generate_curated_allowlist(ranked, tmp_path / "allowlist.json")
        with open(tmp_path / "allowlist.json") as f:
            data = json.load(f)
        assert "generated_at" in data
        assert "symbols" in data
