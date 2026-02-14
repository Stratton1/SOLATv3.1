"""
Tests for the tuning pipeline: OHLCV validation, scoring, portfolio builder,
params passthrough, search spaces, and integration smoke.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
import pytest

from solat_engine.backtest.models import BacktestRequest, MetricsSummary
from solat_engine.data.ohlcv_validator import (
    OHLCVValidationResult,
    validate_bars_list,
    validate_ohlcv_frame,
)
from solat_engine.optimization.models import AllowlistEntry
from solat_engine.optimization.portfolio_builder import (
    FX_CURRENCY_EXPOSURE,
    PortfolioBuilder,
    PortfolioConstraints,
)
from solat_engine.optimization.scoring import (
    ComboScore,
    HardGates,
    ScoringWeights,
    apply_hard_gates,
    compute_weighted_score,
    score_combo,
)
from solat_engine.optimization.search_space import (
    BOT_SEARCH_SPACES,
    dict_to_params,
    get_default_params_dict,
    params_to_dict,
)
from solat_engine.strategies.elite8_hardened import Elite8StrategyFactory


# =============================================================================
# OHLCV Validation Tests
# =============================================================================


class TestOHLCVValidation:
    """Tests for OHLCV frame validator."""

    def test_valid_frame(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="h"),
            "open": [1.1] * 100,
            "high": [1.2] * 100,
            "low": [1.0] * 100,
            "close": [1.15] * 100,
            "volume": [1000.0] * 100,
        })
        result = validate_ohlcv_frame(df)
        assert result.ok is True
        assert result.total_bars == 100
        assert result.nan_count == 0
        assert result.inf_count == 0
        assert result.ohlc_violations == 0

    def test_nan_detection(self):
        df = pd.DataFrame({
            "open": [1.1, float("nan"), 1.1],
            "high": [1.2, 1.2, 1.2],
            "low": [1.0, 1.0, 1.0],
            "close": [1.15, 1.15, float("nan")],
        })
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert result.nan_count == 2

    def test_inf_detection(self):
        df = pd.DataFrame({
            "open": [1.1, float("inf"), 1.1],
            "high": [1.2, 1.2, 1.2],
            "low": [1.0, 1.0, 1.0],
            "close": [1.15, 1.15, 1.15],
        })
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert result.inf_count == 1

    def test_ohlc_violation_high_less_than_low(self):
        df = pd.DataFrame({
            "open": [1.1, 1.1],
            "high": [1.2, 0.9],  # second bar: high < low
            "low": [1.0, 1.0],
            "close": [1.15, 1.15],
        })
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert result.ohlc_violations == 1

    def test_non_monotonic_timestamps(self):
        df = pd.DataFrame({
            "timestamp": [
                datetime(2024, 1, 1, 10, 0),
                datetime(2024, 1, 1, 9, 0),  # Goes backward
                datetime(2024, 1, 1, 11, 0),
            ],
            "open": [1.1] * 3,
            "high": [1.2] * 3,
            "low": [1.0] * 3,
            "close": [1.15] * 3,
        })
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert result.non_monotonic_timestamps == 1

    def test_duplicate_timestamps(self):
        df = pd.DataFrame({
            "timestamp": [
                datetime(2024, 1, 1, 10, 0),
                datetime(2024, 1, 1, 10, 0),  # Duplicate
                datetime(2024, 1, 1, 11, 0),
            ],
            "open": [1.1] * 3,
            "high": [1.2] * 3,
            "low": [1.0] * 3,
            "close": [1.15] * 3,
        })
        result = validate_ohlcv_frame(df)
        assert result.duplicate_timestamps == 1

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert "Empty" in result.errors[0]

    def test_missing_columns(self):
        df = pd.DataFrame({"open": [1.1], "high": [1.2]})
        result = validate_ohlcv_frame(df)
        assert result.ok is False
        assert any("Missing" in e for e in result.errors)

    def test_bars_list_empty(self):
        result = validate_bars_list([])
        assert result.ok is False

    def test_bars_list_insufficient(self):
        @dataclass
        class FakeBar:
            timestamp: datetime = datetime(2024, 1, 1, tzinfo=UTC)
            open: float = 1.1
            high: float = 1.2
            low: float = 1.0
            close: float = 1.15
            volume: float = 100.0

        bars = [FakeBar() for _ in range(10)]
        result = validate_bars_list(bars, min_bars=50)
        assert result.ok is False
        assert "Insufficient" in result.errors[0]


# =============================================================================
# Scoring Tests - Hard Gates
# =============================================================================


class TestScoringGates:
    """Tests for hard gate rejection logic."""

    def test_max_dd_reject(self):
        passed, reasons = apply_hard_gates(
            {"max_drawdown_pct": 25.0, "total_trades": 50, "oos_trades": 20}
        )
        assert passed is False
        assert any("DD" in r for r in reasons)

    def test_min_trades_reject(self):
        passed, reasons = apply_hard_gates(
            {"max_drawdown_pct": 10.0, "total_trades": 5, "oos_trades": 20}
        )
        assert passed is False
        assert any("Trades" in r for r in reasons)

    def test_exposure_reject(self):
        passed, reasons = apply_hard_gates(
            {"max_drawdown_pct": 10.0, "total_trades": 50, "exposure_time_pct": 95.0}
        )
        assert passed is False
        assert any("Exposure" in r for r in reasons)

    def test_nan_reject(self):
        passed, reasons = apply_hard_gates(
            {"oos_sharpe": float("nan"), "total_trades": 50, "max_drawdown_pct": 5.0}
        )
        assert passed is False
        assert any("NaN" in r for r in reasons)

    def test_all_pass(self):
        passed, reasons = apply_hard_gates({
            "max_drawdown_pct": 10.0,
            "total_trades": 50,
            "oos_trades": 20,
            "exposure_time_pct": 30.0,
            "folds_profitable_pct": 0.8,
            "oos_sharpe": 2.0,
            "oos_return_pct": 0.15,
        })
        assert passed is True
        assert reasons == []


# =============================================================================
# Scoring Tests - Weighted Score
# =============================================================================


class TestScoringWeights:
    """Tests for weighted scoring formula."""

    def test_perfect_score_near_100(self):
        score, breakdown = compute_weighted_score(
            oos_sharpe=6.0,
            oos_return_pct=1.0,  # 100%
            max_drawdown_pct=0.0,
            trades_per_day=3.0,
            folds_profitable_pct=1.0,
            sharpe_cv=0.0,
        )
        assert score >= 95.0
        assert score <= 100.0

    def test_sharpe_clamped_at_6(self):
        score1, _ = compute_weighted_score(6.0, 0.5, 10.0, 1.0, 0.8, 0.3)
        score2, _ = compute_weighted_score(10.0, 0.5, 10.0, 1.0, 0.8, 0.3)
        # Should be equal since Sharpe is clamped at 6
        assert abs(score1 - score2) < 0.1

    def test_dd_bonus_under_10(self):
        score_low_dd, bd_low = compute_weighted_score(3.0, 0.3, 8.0, 1.0, 0.8, 0.3)
        score_high_dd, bd_high = compute_weighted_score(3.0, 0.3, 15.0, 1.0, 0.8, 0.3)
        assert score_low_dd > score_high_dd

    def test_cv_penalty(self):
        score_low_cv, _ = compute_weighted_score(3.0, 0.3, 10.0, 1.0, 0.8, 0.5)
        score_high_cv, _ = compute_weighted_score(3.0, 0.3, 10.0, 1.0, 0.8, 1.5)
        assert score_low_cv > score_high_cv

    def test_folds_penalty(self):
        score_good_folds, _ = compute_weighted_score(3.0, 0.3, 10.0, 1.0, 0.8, 0.3)
        score_bad_folds, _ = compute_weighted_score(3.0, 0.3, 10.0, 1.0, 0.3, 0.3)
        assert score_good_folds > score_bad_folds

    def test_score_range_0_100(self):
        # Test various inputs stay in range
        test_cases = [
            (0.0, 0.0, 20.0, 0.0, 0.0, 2.0),
            (6.0, 1.0, 0.0, 3.0, 1.0, 0.0),
            (2.0, 0.2, 10.0, 0.5, 0.6, 0.5),
            (-1.0, -0.1, 25.0, 0.0, 0.0, 3.0),
        ]
        for args in test_cases:
            score, _ = compute_weighted_score(*args)
            assert 0.0 <= score <= 100.0, f"Score {score} out of range for args {args}"

    def test_score_combo_rejected(self):
        cs = score_combo({
            "bot": "TestBot", "symbol": "EURUSD", "timeframe": "1h",
            "max_drawdown_pct": 30.0,  # Over 20% gate
            "total_trades": 50,
        })
        assert cs.rejected is True
        assert cs.score_total == 0.0

    def test_score_combo_scored(self):
        cs = score_combo({
            "bot": "TestBot", "symbol": "EURUSD", "timeframe": "1h",
            "oos_sharpe": 3.0, "oos_return_pct": 0.2,
            "max_drawdown_pct": 10.0, "total_trades": 100,
            "trades_per_day": 1.0, "folds_profitable_pct": 0.8,
            "sharpe_cv": 0.5, "exposure_time_pct": 30.0,
        })
        assert cs.rejected is False
        assert cs.score_total > 0


# =============================================================================
# Portfolio Builder Tests
# =============================================================================


class TestPortfolioBuilder:
    """Tests for portfolio builder with constraints."""

    def _make_combo(self, bot: str, symbol: str, tf: str, score: float,
                    variant: str = "baseline", **kwargs) -> ComboScore:
        return ComboScore(
            bot=bot, symbol=symbol, timeframe=tf,
            variant_id=variant, score_total=score,
            oos_sharpe=kwargs.get("sharpe", 2.0),
            max_drawdown_pct=kwargs.get("dd", 10.0),
            win_rate=kwargs.get("wr", 0.6),
            total_trades=kwargs.get("trades", 50),
        )

    def test_sort_by_score(self):
        combos = [
            self._make_combo("A", "EURUSD", "1h", 50.0),
            self._make_combo("B", "GBPUSD", "1h", 80.0),
            self._make_combo("C", "USDJPY", "1h", 65.0),
        ]
        builder = PortfolioBuilder()
        result = builder.build(combos)
        assert result.slots[0].bot == "B"
        assert result.slots[0].score_total == 80.0

    def test_max_per_symbol(self):
        combos = [
            self._make_combo("A", "EURUSD", "1h", 90.0),
            self._make_combo("B", "EURUSD", "4h", 85.0),
            self._make_combo("C", "EURUSD", "1h", 80.0, variant="tunedA"),
        ]
        constraints = PortfolioConstraints(max_per_symbol=2)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        eurusd_count = sum(1 for s in result.slots if s.symbol == "EURUSD")
        assert eurusd_count == 2

    def test_max_per_bot_family(self):
        combos = [
            self._make_combo("CloudTwist", f"PAIR{i}", "1h", 90.0 - i)
            for i in range(10)
        ]
        constraints = PortfolioConstraints(max_per_bot_family=6, max_per_symbol=5)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        ct_count = sum(1 for s in result.slots if s.bot == "CloudTwist")
        assert ct_count == 6

    def test_max_per_timeframe(self):
        combos = [
            self._make_combo(f"Bot{i}", f"PAIR{i}", "1h", 90.0 - i)
            for i in range(15)
        ]
        constraints = PortfolioConstraints(max_per_timeframe=10, max_per_symbol=5, max_per_bot_family=15)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        tf_1h = sum(1 for s in result.slots if s.timeframe == "1h")
        assert tf_1h <= 10

    def test_currency_buckets(self):
        # All USD pairs — should hit currency cap
        usd_pairs = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD",
                      "USDJPY", "USDCHF", "EURUSD", "GBPUSD", "AUDUSD"]
        combos = [
            self._make_combo(f"Bot{i}", pair, "1h", 90.0 - i)
            for i, pair in enumerate(usd_pairs[:8])
        ]
        constraints = PortfolioConstraints(max_per_currency=4, max_per_symbol=5, max_per_bot_family=10)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        # USD shouldn't exceed 4
        usd_count = result.currency_distribution.get("USD", 0)
        assert usd_count <= 4

    def test_min_score_filter(self):
        combos = [
            self._make_combo("A", "EURUSD", "1h", 80.0),
            self._make_combo("B", "GBPUSD", "1h", 30.0),  # Below min_score
        ]
        constraints = PortfolioConstraints(min_score=40.0)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        assert result.total_slots == 1

    def test_variants_count_toward_family(self):
        combos = [
            self._make_combo("CloudTwist", "EURUSD", "1h", 90.0, "baseline"),
            self._make_combo("CloudTwist", "GBPUSD", "1h", 88.0, "tunedA"),
            self._make_combo("CloudTwist", "USDJPY", "1h", 86.0, "tunedB"),
            self._make_combo("CloudTwist", "AUDUSD", "1h", 84.0, "baseline"),
            self._make_combo("CloudTwist", "NZDUSD", "1h", 82.0, "tunedA"),
            self._make_combo("CloudTwist", "USDCAD", "1h", 80.0, "tunedB"),
            self._make_combo("CloudTwist", "EURGBP", "1h", 78.0, "baseline"),  # Should be rejected
        ]
        constraints = PortfolioConstraints(max_per_bot_family=6, max_per_symbol=3)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        ct_count = sum(1 for s in result.slots if s.bot == "CloudTwist")
        assert ct_count == 6

    def test_max_slots(self):
        combos = [
            self._make_combo(f"Bot{i}", f"PAIR{i}", "1h", 90.0 - i)
            for i in range(30)
        ]
        constraints = PortfolioConstraints(max_slots=20, max_per_symbol=5, max_per_bot_family=30)
        builder = PortfolioBuilder()
        result = builder.build(combos, constraints)
        assert result.total_slots <= 20

    def test_to_allowlist(self):
        combos = [self._make_combo("CloudTwist", "EURUSD", "1h", 80.0, "tunedA")]
        builder = PortfolioBuilder()
        result = builder.build(combos)
        allowlist = builder.to_allowlist(result)
        assert len(allowlist) == 1
        assert allowlist[0].variant_id == "tunedA"
        assert allowlist[0].score_total == 80.0

    def test_to_markdown_report(self):
        combos = [self._make_combo("CloudTwist", "EURUSD", "1h", 80.0)]
        builder = PortfolioBuilder()
        result = builder.build(combos)
        report = builder.to_markdown_report(result)
        assert "Portfolio Report" in report
        assert "CloudTwist" in report
        assert "EURUSD" in report

    def test_rejected_combo_excluded(self):
        combos = [
            ComboScore(
                bot="A", symbol="EURUSD", timeframe="1h",
                rejected=True, score_total=90.0,
            ),
            self._make_combo("B", "GBPUSD", "1h", 50.0),
        ]
        builder = PortfolioBuilder()
        result = builder.build(combos)
        assert result.total_slots == 1
        assert result.slots[0].bot == "B"


# =============================================================================
# Params Passthrough Tests
# =============================================================================


class TestParamsPassthrough:
    """Tests for params_override in BacktestRequest and factory."""

    def test_backtest_request_with_params(self):
        req = BacktestRequest(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
            params_override={"CloudTwist": {"cooldown_bars": 10}},
        )
        assert req.params_override is not None
        assert "CloudTwist" in req.params_override

    def test_backtest_request_without_params(self):
        req = BacktestRequest(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            timeframe="1h",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert req.params_override is None

    def test_factory_creates_with_custom_params(self):
        from solat_engine.strategies.elite8_hardened import CloudTwistParams, BaseHardeningParams
        custom = CloudTwistParams(base=BaseHardeningParams(cooldown_bars=12))
        strategy = Elite8StrategyFactory.create("CloudTwist", params=custom)
        assert strategy.name == "CloudTwist"

    def test_factory_creates_without_params(self):
        strategy = Elite8StrategyFactory.create("CloudTwist")
        assert strategy.name == "CloudTwist"

    def test_extended_metrics_fields_exist(self):
        m = MetricsSummary()
        assert hasattr(m, "trades_per_day")
        assert hasattr(m, "equity_peak")
        assert hasattr(m, "best_5_trades_pnl")
        assert hasattr(m, "worst_5_trades_pnl")
        assert hasattr(m, "missing_bar_pct")
        assert m.trades_per_day == 0.0
        assert m.equity_peak == 0.0
        assert m.best_5_trades_pnl == []


# =============================================================================
# Search Space Tests
# =============================================================================


class TestSearchSpace:
    """Tests for per-bot search spaces and param conversion."""

    @pytest.mark.parametrize("bot_name", list(BOT_SEARCH_SPACES.keys()))
    def test_dict_to_params_roundtrip(self, bot_name: str):
        default_dict = get_default_params_dict(bot_name)
        assert isinstance(default_dict, dict)
        assert "cooldown_bars" in default_dict

        # Convert to dataclass and back
        params_obj = dict_to_params(bot_name, default_dict)
        back_to_dict = params_to_dict(bot_name, params_obj)

        for key in default_dict:
            assert key in back_to_dict, f"Missing key {key} in roundtrip for {bot_name}"
            assert back_to_dict[key] == default_dict[key], (
                f"{bot_name}.{key}: {back_to_dict[key]} != {default_dict[key]}"
            )

    @pytest.mark.parametrize("bot_name", list(BOT_SEARCH_SPACES.keys()))
    def test_default_params_valid(self, bot_name: str):
        default_dict = get_default_params_dict(bot_name)
        assert default_dict["cooldown_bars"] >= 1
        assert default_dict["breakout_atr_mult"] >= 0

    def test_dict_to_params_custom_values(self):
        params = dict_to_params("CloudTwist", {"cooldown_bars": 12, "breakout_atr_mult": 0.6})
        assert params.base.cooldown_bars == 12
        assert params.base.breakout_atr_mult == 0.6

    def test_dict_to_params_unknown_bot(self):
        with pytest.raises(ValueError, match="Unknown bot"):
            dict_to_params("NonExistentBot", {"cooldown_bars": 5})

    def test_all_bots_have_search_spaces(self):
        from solat_engine.strategies.elite8_hardened import get_available_bots
        available = get_available_bots()
        for bot in available:
            assert bot in BOT_SEARCH_SPACES, f"No search space for {bot}"

    def test_chikou_kaizen_specific_params(self):
        params = dict_to_params("ChikouKaizen", {
            "cooldown_bars": 8,
            "displacement": 30,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
        })
        assert params.displacement == 30
        assert params.sl_atr_mult == 1.5
        assert params.tp_atr_mult == 3.0


# =============================================================================
# AllowlistEntry Extended Fields Tests
# =============================================================================


class TestAllowlistEntryExtended:
    """Tests for extended AllowlistEntry fields."""

    def test_backward_compatible_defaults(self):
        entry = AllowlistEntry(symbol="EURUSD", bot="CloudTwist", timeframe="1h")
        assert entry.variant_id == "baseline"
        assert entry.params_override == {}
        assert entry.score_total == 0.0
        assert entry.score_breakdown == {}
        assert entry.evidence == {}

    def test_combo_id_baseline(self):
        entry = AllowlistEntry(symbol="EURUSD", bot="CloudTwist", timeframe="1h")
        assert entry.combo_id == "EURUSD:CloudTwist:1h"

    def test_combo_id_with_variant(self):
        entry = AllowlistEntry(
            symbol="EURUSD", bot="CloudTwist", timeframe="1h",
            variant_id="tunedA",
        )
        assert entry.combo_id == "EURUSD:CloudTwist:1h:tunedA"

    def test_serialization_roundtrip(self):
        entry = AllowlistEntry(
            symbol="EURUSD", bot="CloudTwist", timeframe="1h",
            variant_id="tunedA",
            params_override={"cooldown_bars": 12},
            score_total=75.5,
            score_breakdown={"sharpe_raw": 50.0, "return_raw": 30.0},
            evidence={"wf_run_id": "wf-abc123"},
        )
        data = entry.model_dump()
        restored = AllowlistEntry(**data)
        assert restored.variant_id == "tunedA"
        assert restored.params_override == {"cooldown_bars": 12}
        assert restored.score_total == 75.5


# =============================================================================
# FX Currency Exposure Tests
# =============================================================================


class TestFXCurrencyExposure:
    """Tests for FX currency mapping."""

    def test_major_pairs_mapped(self):
        for pair in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"]:
            assert pair in FX_CURRENCY_EXPOSURE

    def test_currency_tuple_structure(self):
        for pair, (base, quote) in FX_CURRENCY_EXPOSURE.items():
            assert len(base) == 3
            assert len(quote) == 3
            assert base != quote


# =============================================================================
# Integration Smoke Test
# =============================================================================


class TestIntegrationSmoke:
    """Smoke tests that verify components work together."""

    def test_score_then_portfolio(self):
        """Score multiple combos then build portfolio."""
        combos = []
        for bot in ["CloudTwist", "TKCrossSniper", "KijunBouncer"]:
            for symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
                cs = score_combo({
                    "bot": bot, "symbol": symbol, "timeframe": "4h",
                    "oos_sharpe": 2.5, "oos_return_pct": 0.15,
                    "max_drawdown_pct": 8.0, "total_trades": 50,
                    "trades_per_day": 0.5, "folds_profitable_pct": 0.75,
                    "sharpe_cv": 0.4, "exposure_time_pct": 30.0,
                })
                combos.append(cs)

        assert all(not c.rejected for c in combos)

        builder = PortfolioBuilder()
        result = builder.build(combos, PortfolioConstraints(max_slots=25, max_per_symbol=2))
        assert result.total_slots > 0
        assert result.total_slots <= 25

        # Check symbol cap
        for sym, count in result.symbol_distribution.items():
            assert count <= 2, f"{sym} has {count} slots, max 2"

    def test_params_to_factory_to_strategy(self):
        """Verify dict -> params -> factory -> strategy pipeline."""
        for bot_name in BOT_SEARCH_SPACES:
            default_dict = get_default_params_dict(bot_name)
            params_obj = dict_to_params(bot_name, default_dict)
            strategy = Elite8StrategyFactory.create(bot_name, params=params_obj)
            assert strategy.name == bot_name

    def test_scoring_deterministic(self):
        """Same inputs should always produce same score."""
        metrics = {
            "bot": "CloudTwist", "symbol": "USDJPY", "timeframe": "4h",
            "oos_sharpe": 3.5, "oos_return_pct": 0.25,
            "max_drawdown_pct": 7.0, "total_trades": 80,
            "trades_per_day": 1.2, "folds_profitable_pct": 0.9,
            "sharpe_cv": 0.3, "exposure_time_pct": 40.0,
        }
        score1 = score_combo(metrics)
        score2 = score_combo(metrics)
        assert score1.score_total == score2.score_total
        assert score1.score_breakdown == score2.score_breakdown
