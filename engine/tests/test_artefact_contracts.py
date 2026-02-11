"""
Artefact contract tests.

Verifies that sweep/backtest JSON artefacts include schema_version
and required fields per the artefact contract specification.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from solat_engine.backtest.sweep_utils import (
    detect_broken_bots,
    generate_curated_allowlist,
    generate_ranked_csv,
    generate_top_picks_json,
)

SCHEMA_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")


def _make_fixture_results() -> pd.DataFrame:
    """Fixture data with multiple bots/symbols/timeframes."""
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


class TestTopPicksContract:
    """top_picks.json artefact contract."""

    def test_has_schema_version(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_top_picks_json(ranked, tmp_path / "top_picks.json")
        assert "schema_version" in result

    def test_schema_version_format(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_top_picks_json(ranked, tmp_path / "top_picks.json")
        assert SCHEMA_VERSION_PATTERN.match(result["schema_version"])

    def test_picks_is_list(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_top_picks_json(ranked, tmp_path / "top_picks.json")
        assert isinstance(result["picks"], list)
        assert len(result["picks"]) > 0

    def test_pick_has_required_fields(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_top_picks_json(ranked, tmp_path / "top_picks.json")
        first = result["picks"][0]
        for key in ("bot", "symbol", "timeframe", "score"):
            assert key in first, f"pick missing '{key}'"


class TestCuratedAllowlistContract:
    """curated_allowlist.json artefact contract."""

    def test_has_schema_version(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_curated_allowlist(ranked, tmp_path / "allowlist.json")
        assert "schema_version" in result

    def test_schema_version_format(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_curated_allowlist(ranked, tmp_path / "allowlist.json")
        assert SCHEMA_VERSION_PATTERN.match(result["schema_version"])

    def test_symbols_is_dict(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        result = generate_curated_allowlist(ranked, tmp_path / "allowlist.json")
        assert isinstance(result["symbols"], dict)

    def test_empty_result_has_schema_version(self, tmp_path: Path) -> None:
        empty_df = pd.DataFrame(columns=["bot", "symbol", "timeframe", "sharpe"])
        result = generate_curated_allowlist(empty_df, tmp_path / "allowlist.json")
        assert "schema_version" in result
        assert SCHEMA_VERSION_PATTERN.match(result["schema_version"])


class TestDetectBrokenBotsContract:
    """disabled_bots.json artefact contract."""

    def test_has_schema_version(self) -> None:
        df = _make_fixture_results()
        result = detect_broken_bots(df)
        assert "schema_version" in result

    def test_schema_version_format(self) -> None:
        df = _make_fixture_results()
        result = detect_broken_bots(df)
        assert SCHEMA_VERSION_PATTERN.match(result["schema_version"])

    def test_broken_bots_is_list(self) -> None:
        df = _make_fixture_results()
        result = detect_broken_bots(df)
        assert isinstance(result["broken_bots"], list)


class TestRankedCsvContract:
    """ranked.csv artefact contract."""

    def test_has_required_columns(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        required = {"rank", "bot", "symbol", "timeframe", "sharpe"}
        assert required.issubset(set(ranked.columns))

    def test_rank_starts_at_one(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        assert ranked.iloc[0]["rank"] == 1

    def test_sorted_by_sharpe_desc(self, tmp_path: Path) -> None:
        df = _make_fixture_results()
        ranked = generate_ranked_csv(df, tmp_path / "ranked.csv", min_trades=30)
        sharpes = ranked["sharpe"].tolist()
        assert sharpes == sorted(sharpes, reverse=True)
