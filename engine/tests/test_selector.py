"""
Tests for optimization/selector.py — ComboSelector.
"""

import pytest

from solat_engine.optimization.models import WalkForwardConfig, WalkForwardResult
from solat_engine.optimization.selector import (
    ComboSelector,
    SelectionConstraints,
    SelectorResult,
)
from datetime import UTC, datetime


def _make_wfo_result(combos: list[dict]) -> WalkForwardResult:
    """Helper: create a completed WalkForwardResult with given recommended_combos."""
    config = WalkForwardConfig(
        symbols=["EURUSD"],
        bots=["TKCrossSniper"],
        start_date=datetime(2023, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 12, 31, tzinfo=UTC),
    )
    return WalkForwardResult(
        run_id="wf-test",
        config=config,
        status="completed",
        recommended_combos=combos,
    )


def _combo(
    symbol: str = "EURUSD",
    bot: str = "TKCrossSniper",
    timeframe: str = "1h",
    avg_sharpe: float = 1.0,
    total_trades: int = 50,
    folds_profitable_pct: float = 0.8,
    sharpe_cv: float = 0.5,
    consistency_score: float = 2.0,
    windows_count: int = 5,
) -> dict:
    return {
        "combo_id": f"{symbol}:{bot}:{timeframe}",
        "symbol": symbol,
        "bot": bot,
        "timeframe": timeframe,
        "avg_sharpe": avg_sharpe,
        "avg_win_rate": 0.55,
        "avg_return_pct": 5.0,
        "total_trades": total_trades,
        "avg_drawdown_pct": 8.0,
        "sharpe_std": avg_sharpe * sharpe_cv,
        "sharpe_cv": sharpe_cv,
        "folds_profitable_pct": folds_profitable_pct,
        "windows_count": windows_count,
        "consistency_score": consistency_score,
    }


class TestSelectorFiltering:
    """Tests that the selector correctly filters combos."""

    def test_filters_low_sharpe(self):
        selector = ComboSelector()
        combos = [
            _combo(avg_sharpe=0.1),  # below 0.3 default threshold
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(min_oos_sharpe=0.3),
        )
        assert len(result.selected) == 0
        assert len(result.rejected) == 1
        assert "sharpe" in result.rejected[0]["rejection_reasons"][0]

    def test_filters_low_trades(self):
        selector = ComboSelector()
        combos = [
            _combo(total_trades=5),  # below 20 default threshold
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(min_oos_trades=20),
        )
        assert len(result.selected) == 0
        assert len(result.rejected) == 1
        assert "trades" in result.rejected[0]["rejection_reasons"][0]

    def test_filters_low_folds_profitable(self):
        selector = ComboSelector()
        combos = [
            _combo(folds_profitable_pct=0.2),  # below 0.5 default threshold
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(min_folds_profitable_pct=0.5),
        )
        assert len(result.selected) == 0
        assert len(result.rejected) == 1
        assert "folds_profitable" in result.rejected[0]["rejection_reasons"][0]

    def test_filters_high_sharpe_cv(self):
        selector = ComboSelector()
        combos = [
            _combo(sharpe_cv=3.0),  # above 2.0 default threshold
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(max_sharpe_cv=2.0),
        )
        assert len(result.selected) == 0
        assert len(result.rejected) == 1
        assert "sharpe_cv" in result.rejected[0]["rejection_reasons"][0]

    def test_passes_good_combo(self):
        selector = ComboSelector()
        combos = [
            _combo(avg_sharpe=1.5, total_trades=100, folds_profitable_pct=0.9, sharpe_cv=0.5),
        ]
        result = selector.select(_make_wfo_result(combos))
        assert len(result.selected) == 1
        assert result.selected[0].symbol == "EURUSD"


class TestSelectorDiversity:
    """Tests diversification enforcement."""

    def test_max_per_symbol(self):
        selector = ComboSelector()
        # 5 combos for same symbol, different bots
        combos = [
            _combo(symbol="EURUSD", bot=f"Bot{i}", consistency_score=5 - i)
            for i in range(5)
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(max_per_symbol=2, max_per_bot=10),
        )
        assert len(result.selected) == 2
        assert all(s.symbol == "EURUSD" for s in result.selected)

    def test_max_per_bot(self):
        selector = ComboSelector()
        # 5 combos for same bot, different symbols
        combos = [
            _combo(symbol=f"SYM{i}", bot="TKCross", consistency_score=5 - i)
            for i in range(5)
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(max_per_symbol=10, max_per_bot=3),
        )
        assert len(result.selected) == 3
        assert all(s.bot == "TKCross" for s in result.selected)

    def test_max_combos(self):
        selector = ComboSelector()
        combos = [
            _combo(symbol=f"SYM{i}", bot=f"Bot{i}", consistency_score=10 - i)
            for i in range(10)
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(max_combos=3, max_per_symbol=10, max_per_bot=10),
        )
        assert len(result.selected) == 3


class TestSelectorRationale:
    """Tests that rationale strings contain key metrics."""

    def test_rationale_contains_metrics(self):
        selector = ComboSelector()
        combos = [
            _combo(avg_sharpe=2.5, folds_profitable_pct=0.8, sharpe_cv=0.3),
        ]
        result = selector.select(_make_wfo_result(combos))
        assert len(result.selected) == 1
        rationale = result.selected[0].rationale
        assert "Sharpe=2.50" in rationale
        assert "80%" in rationale
        assert "CV=0.30" in rationale


class TestSelectorEdgeCases:
    """Tests edge cases."""

    def test_empty_combos(self):
        selector = ComboSelector()
        result = selector.select(_make_wfo_result([]))
        assert len(result.selected) == 0
        assert len(result.rejected) == 0

    def test_incomplete_wfo(self):
        """WFO result with combos missing some fields should not crash."""
        selector = ComboSelector()
        combos = [
            {
                "combo_id": "X:Y:Z",
                "symbol": "X",
                "bot": "Y",
                "timeframe": "Z",
                "avg_sharpe": 1.0,
                "total_trades": 50,
                # Missing folds_profitable_pct and sharpe_cv
            },
        ]
        result = selector.select(
            _make_wfo_result(combos),
            SelectionConstraints(
                min_folds_profitable_pct=0.0,
                max_sharpe_cv=float("inf"),
            ),
        )
        # Should still pass (defaults fill in 0 / inf)
        assert len(result.selected) == 1

    def test_to_allowlist_entries(self):
        selector = ComboSelector()
        combos = [_combo()]
        result = selector.select(_make_wfo_result(combos))
        entries = selector.to_allowlist_entries(result.selected, "wf-test")
        assert len(entries) == 1
        assert entries[0].symbol == "EURUSD"
        assert entries[0].source_run_id == "wf-test"
