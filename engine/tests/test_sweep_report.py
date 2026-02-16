"""Tests for the canonical sweep reporting module."""

import json
import tempfile
from pathlib import Path

import pytest

from solat_engine.reporting.sweep_report import (
    AggBucket,
    ComboResultRow,
    SweepReportMetadata,
    SweepSummary,
    compute_summary,
    compute_verdict,
    generate_sweep_report,
    render_markdown,
    row_from_metrics_summary,
    rows_from_combo_results,
    write_csv,
    write_json_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(**overrides) -> ComboResultRow:
    """Create a ComboResultRow with sensible defaults."""
    defaults = dict(
        bot="TKCross", symbol="EURUSD", timeframe="1h",
        trades=50, wins=30, losses=20,
        win_rate=0.6, sharpe=1.8, sortino=2.1, calmar=1.5,
        profit_factor=1.7, max_drawdown_pct=12.0,
        net_pnl=5000.0, net_return_pct=50.0,
        expectancy=100.0, days=365, bars=6000,
        runtime_s=5.3, pass_id="default",
    )
    defaults.update(overrides)
    return ComboResultRow(**defaults)


def _sample_rows() -> list[ComboResultRow]:
    """Generate a representative set of rows for testing."""
    return [
        _make_row(bot="TKCross", symbol="EURUSD", timeframe="1h",
                  sharpe=2.5, profit_factor=2.0, trades=80, win_rate=0.65,
                  max_drawdown_pct=8.0, net_return_pct=120.0),
        _make_row(bot="CloudTwist", symbol="GBPUSD", timeframe="4h",
                  sharpe=1.2, profit_factor=1.3, trades=40, win_rate=0.55,
                  max_drawdown_pct=15.0, net_return_pct=30.0),
        _make_row(bot="KumoBreaker", symbol="USDJPY", timeframe="1h",
                  sharpe=0.5, profit_factor=1.1, trades=25, win_rate=0.48,
                  max_drawdown_pct=22.0, net_return_pct=10.0),
        _make_row(bot="MomentumRider", symbol="EURUSD", timeframe="4h",
                  sharpe=-0.3, profit_factor=0.8, trades=60, win_rate=0.42,
                  max_drawdown_pct=35.0, net_return_pct=-15.0),
        _make_row(bot="ChikouConfirmer", symbol="GBPUSD", timeframe="1h",
                  sharpe=0.0, profit_factor=0.0, trades=0, win_rate=0.0,
                  max_drawdown_pct=0.0, net_return_pct=0.0),
        _make_row(bot="TKCross", symbol="USDJPY", timeframe="4h",
                  sharpe=0.0, profit_factor=0.0, trades=0, win_rate=0.0,
                  max_drawdown_pct=0.0, net_return_pct=0.0),
        _make_row(bot="ReversalHunter", symbol="AUDUSD", timeframe="1h",
                  sharpe=0.0, profit_factor=0.0, trades=0, win_rate=0.0,
                  success=False, error="Data gap too large"),
    ]


# ---------------------------------------------------------------------------
# compute_verdict tests
# ---------------------------------------------------------------------------

class TestComputeVerdict:
    def test_strong(self):
        assert compute_verdict(2.0, 1.8, 50, 10.0) == "Strong"

    def test_strong_boundary(self):
        assert compute_verdict(1.5, 1.5, 10, 30.0) == "Strong"

    def test_moderate(self):
        assert compute_verdict(1.0, 1.3, 20, 35.0) == "Moderate"

    def test_moderate_boundary(self):
        assert compute_verdict(0.75, 1.2, 10, 50.0) == "Moderate"

    def test_weak(self):
        assert compute_verdict(0.5, 0.9, 10, 40.0) == "Weak"

    def test_weak_boundary(self):
        assert compute_verdict(0.3, 0.5, 5, 80.0) == "Weak"

    def test_flat(self):
        assert compute_verdict(0.0, 1.0, 3, 5.0) == "Flat"

    def test_flat_boundary(self):
        assert compute_verdict(-0.15, 0.5, 1, 50.0) == "Flat"

    def test_no_trades(self):
        assert compute_verdict(0.0, 0.0, 0, 0.0) == "No Trades"

    def test_no_trades_ignores_other_metrics(self):
        assert compute_verdict(5.0, 10.0, 0, 0.0) == "No Trades"

    def test_poor(self):
        assert compute_verdict(-1.0, 0.5, 30, 50.0) == "Poor"

    def test_poor_negative_sharpe_few_trades(self):
        assert compute_verdict(-0.5, 0.8, 2, 20.0) == "Poor"


# ---------------------------------------------------------------------------
# ComboResultRow tests
# ---------------------------------------------------------------------------

class TestComboResultRow:
    def test_auto_verdict(self):
        row = _make_row(sharpe=2.0, profit_factor=2.0, trades=50, max_drawdown_pct=10.0)
        assert row.verdict == "Strong"

    def test_auto_zero_trade(self):
        row = _make_row(trades=0)
        assert row.zero_trade is True
        assert row.verdict == "No Trades"

    def test_to_dict(self):
        row = _make_row()
        d = row.to_dict()
        assert d["bot"] == "TKCross"
        assert d["symbol"] == "EURUSD"
        assert isinstance(d, dict)

    def test_field_names(self):
        names = ComboResultRow.field_names()
        assert "bot" in names
        assert "sharpe" in names
        assert "verdict" in names
        assert len(names) > 30

    def test_core_columns_subset(self):
        core = ComboResultRow.CORE_COLUMNS
        all_fields = ComboResultRow.field_names()
        for c in core:
            assert c in all_fields, f"Core column '{c}' not in field_names"


# ---------------------------------------------------------------------------
# row_from_metrics_summary tests
# ---------------------------------------------------------------------------

class TestRowFromMetricsSummary:
    def test_basic_mapping(self):
        """Test that MetricsSummary fields map correctly to ComboResultRow."""
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(
            bot="TKCross", symbol="EURUSD", timeframe="1h",
            total_trades=42, winning_trades=28, losing_trades=14,
            win_rate=0.667, sharpe_ratio=1.8, sortino_ratio=2.3,
            calmar_ratio=1.5, profit_factor=2.1,
            max_drawdown_pct=12.5, total_return=3000.0,
            total_return_pct=30.0, expectancy=71.43,
            duration_days=365.0, bar_count=6000,
            avg_trade_pnl=71.43, cagr=0.30,
            long_trades=20, short_trades=22,
            largest_win=500.0, largest_loss=-200.0,
            total_orders=50, rejected_orders=8,
            trades_per_day=0.115, avg_bars_held=12.3,
        )
        row = row_from_metrics_summary(
            m, bot="TKCross", symbol="EURUSD", timeframe="1h",
            pass_id="test", runtime_s=3.5,
        )
        assert row.trades == 42
        assert row.wins == 28
        assert row.losses == 14
        assert row.sharpe == 1.8
        assert row.sortino == 2.3
        assert row.profit_factor == 2.1
        assert row.max_drawdown_pct == 12.5
        assert row.days == 365.0
        assert row.bars == 6000
        assert row.long_trades == 20
        assert row.short_trades == 22
        assert row.largest_win == 500.0
        assert row.largest_loss == -200.0
        assert row.total_orders == 50
        assert row.rejected_orders == 8
        assert row.runtime_s == 3.5
        assert row.verdict == "Strong"

    def test_none_metrics_default_zero(self):
        """Test that None values in MetricsSummary become 0."""
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary()
        row = row_from_metrics_summary(m)
        assert row.trades == 0
        assert row.sharpe == 0.0
        assert row.verdict == "No Trades"


# ---------------------------------------------------------------------------
# rows_from_combo_results tests
# ---------------------------------------------------------------------------

class TestRowsFromComboResults:
    def test_basic_conversion(self):
        from solat_engine.backtest.parallel_sweep import ComboResult
        combos = [
            ComboResult(
                combo_id="c1", bot="TKCross", symbol="EURUSD", timeframe="1h",
                success=True, sharpe=1.5, total_trades=40, win_rate=0.6,
                profit_factor=1.8, max_drawdown=10.0, pnl=2000.0,
                duration_s=3.0, winning_trades=24, losing_trades=16,
                duration_days=365.0, bar_count=6000,
            ),
            ComboResult(
                combo_id="c2", bot="KumoBreaker", symbol="GBPUSD", timeframe="4h",
                success=False, error="timeout",
            ),
        ]
        rows = rows_from_combo_results(combos, pass_id="sweep1")
        assert len(rows) == 2
        assert rows[0].bot == "TKCross"
        assert rows[0].sharpe == 1.5
        assert rows[0].wins == 24
        assert rows[0].losses == 16
        assert rows[0].days == 365.0
        assert rows[0].bars == 6000
        assert rows[0].pass_id == "sweep1"
        assert rows[1].success is False
        assert rows[1].error == "timeout"


# ---------------------------------------------------------------------------
# compute_summary tests
# ---------------------------------------------------------------------------

class TestComputeSummary:
    def test_basic_counts(self):
        rows = _sample_rows()
        s = compute_summary(rows)
        assert s.total_combos == 7
        assert s.succeeded == 6  # 1 failed
        assert s.failed == 1
        assert s.active_combos == 4  # 4 with trades > 0 and success
        assert s.zero_trade_combos == 2  # 2 with trades == 0 and success

    def test_sharpe_percentiles(self):
        rows = _sample_rows()
        s = compute_summary(rows)
        assert s.best_sharpe == 2.5
        assert s.worst_sharpe == -0.3

    def test_by_bot_aggregation(self):
        rows = _sample_rows()
        s = compute_summary(rows)
        bot_names = [b.key for b in s.by_bot]
        assert "TKCross" in bot_names
        assert "CloudTwist" in bot_names

    def test_by_symbol_aggregation(self):
        rows = _sample_rows()
        s = compute_summary(rows)
        sym_names = [b.key for b in s.by_symbol]
        assert "EURUSD" in sym_names
        assert "GBPUSD" in sym_names

    def test_by_timeframe_aggregation(self):
        rows = _sample_rows()
        s = compute_summary(rows)
        tf_names = [b.key for b in s.by_timeframe]
        assert "1h" in tf_names
        assert "4h" in tf_names

    def test_empty_rows(self):
        s = compute_summary([])
        assert s.total_combos == 0
        assert s.active_combos == 0


# ---------------------------------------------------------------------------
# render_markdown tests
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_contains_required_sections(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(
            sweep_name="Test Sweep",
            dataset="2024 FX",
            date_start="2024-01-01",
            date_end="2024-12-31",
        )
        md = render_markdown(rows, meta, top_n=5)
        assert "# Test Sweep" in md
        assert "## Executive Summary" in md
        assert "## Leaderboards" in md
        assert "## Zero-Trade Combos" in md
        assert "## Aggregates" in md
        assert "## Recommendations" in md
        assert "## Appendix: Verdict Rules" in md

    def test_leaderboard_order(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta, top_n=5)
        # Best sharpe should appear before worse ones
        idx_25 = md.find("2.50")
        idx_12 = md.find("1.20")
        assert idx_25 < idx_12, "Top Sharpe should come first in leaderboard"

    def test_includes_metadata(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(
            sweep_name="My Sweep",
            date_start="2024-01-01",
            date_end="2024-12-31",
            engine_version="3.1.0",
            git_hash="abc12345",
        )
        md = render_markdown(rows, meta)
        assert "2024-01-01" in md
        assert "2024-12-31" in md
        assert "v3.1.0" in md
        assert "abc12345" in md

    def test_full_table_mode(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta, include_full_table=True)
        assert "## Full Results" in md

    def test_verdict_rules_appendix(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta)
        assert "Strong" in md
        assert "Moderate" in md
        assert "Weak" in md


# ---------------------------------------------------------------------------
# write_csv tests
# ---------------------------------------------------------------------------

class TestWriteCsv:
    def test_writes_all_columns(self):
        rows = _sample_rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            write_csv(rows, path)
            assert path.exists()
            content = path.read_text()
            # Check header contains all field names
            header = content.split("\n")[0]
            for col in ["bot", "symbol", "timeframe", "sharpe", "verdict"]:
                assert col in header
            # Check row count (header + data)
            lines = [l for l in content.strip().split("\n") if l]
            assert len(lines) == len(rows) + 1

    def test_creates_parent_dirs(self):
        rows = [_make_row()]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "dir" / "test.csv"
            write_csv(rows, path)
            assert path.exists()


# ---------------------------------------------------------------------------
# write_json_summary tests
# ---------------------------------------------------------------------------

class TestWriteJsonSummary:
    def test_json_structure(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test JSON")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            write_json_summary(rows, meta, None, path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["schema_version"] == "2.0"
            assert "summary" in data
            assert "by_bot" in data
            assert "by_symbol" in data
            assert "by_timeframe" in data
            assert "missing_fields" in data
            assert "verdict_rules" in data

    def test_summary_counts_match(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            write_json_summary(rows, meta, None, path)
            data = json.loads(path.read_text())
            assert data["summary"]["total_combos"] == len(rows)


# ---------------------------------------------------------------------------
# generate_sweep_report (integration) tests
# ---------------------------------------------------------------------------

class TestGenerateSweepReport:
    def test_generates_all_formats(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Integration Test")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "reports"
            outputs = generate_sweep_report(rows, meta, out_dir)
            assert "md" in outputs
            assert "csv" in outputs
            assert "json" in outputs
            for path in outputs.values():
                assert path.exists()
                assert path.stat().st_size > 0

    def test_selective_formats(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Selective")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "reports"
            outputs = generate_sweep_report(
                rows, meta, out_dir, formats={"csv"}
            )
            assert "csv" in outputs
            assert "md" not in outputs
            assert "json" not in outputs


# ---------------------------------------------------------------------------
# Days computation
# ---------------------------------------------------------------------------

class TestDaysComputation:
    def test_days_from_metrics_summary(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(duration_days=252.0)
        row = row_from_metrics_summary(m)
        assert row.days == 252.0

    def test_days_zero_when_missing(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary()
        row = row_from_metrics_summary(m)
        assert row.days == 0.0


# ---------------------------------------------------------------------------
# Win rate computation
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_win_rate_passthrough(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(win_rate=0.65, total_trades=100)
        row = row_from_metrics_summary(m)
        assert row.win_rate == 0.65

    def test_win_rate_zero_no_trades(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(total_trades=0)
        row = row_from_metrics_summary(m)
        assert row.win_rate == 0.0


# ---------------------------------------------------------------------------
# Profit factor
# ---------------------------------------------------------------------------

class TestProfitFactor:
    def test_pf_passthrough(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(profit_factor=2.5)
        row = row_from_metrics_summary(m)
        assert row.profit_factor == 2.5


# ---------------------------------------------------------------------------
# Verdict flags
# ---------------------------------------------------------------------------

class TestVerdictFlags:
    def test_no_trades_flag(self):
        row = _make_row(trades=0)
        assert "NO_TRADES" in row.verdict_flags

    def test_high_dd_flag(self):
        row = _make_row(trades=50, max_drawdown_pct=40.0)
        assert "HIGH_DD" in row.verdict_flags

    def test_low_trades_flag(self):
        row = _make_row(trades=5, sharpe=1.0)
        assert "LOW_TRADES" in row.verdict_flags

    def test_unprofitable_flag(self):
        row = _make_row(trades=50, profit_factor=0.8)
        assert "UNPROFITABLE" in row.verdict_flags

    def test_no_flags_healthy(self):
        row = _make_row(trades=50, max_drawdown_pct=10.0, profit_factor=1.5)
        assert row.verdict_flags == ""

    def test_multiple_flags(self):
        row = _make_row(trades=5, max_drawdown_pct=40.0, profit_factor=0.5)
        flags = row.verdict_flags.split(",")
        assert "HIGH_DD" in flags
        assert "LOW_TRADES" in flags
        assert "UNPROFITABLE" in flags


# ---------------------------------------------------------------------------
# Extended field mapping (v3)
# ---------------------------------------------------------------------------

class TestExtendedFieldMapping:
    def test_equity_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(start_equity=10000, end_equity=15000, equity_peak=16000)
        row = row_from_metrics_summary(m)
        assert row.start_equity == 10000
        assert row.end_equity == 15000
        assert row.equity_peak == 16000

    def test_initial_cash(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(initial_cash=100000)
        row = row_from_metrics_summary(m)
        assert row.initial_cash == 100000

    def test_max_drawdown_absolute(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(max_drawdown=5000.0)
        row = row_from_metrics_summary(m)
        assert row.max_drawdown == 5000.0

    def test_downside_volatility(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(downside_volatility=0.12)
        row = row_from_metrics_summary(m)
        assert row.downside_volatility == 0.12

    def test_trade_detail_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(median_bars_held=8.5, avg_win=200.0, avg_loss=-100.0)
        row = row_from_metrics_summary(m)
        assert row.median_bars_held == 8.5
        assert row.avg_win == 200.0
        assert row.avg_loss == -100.0

    def test_distribution_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(skewness=0.5, kurtosis=3.2)
        row = row_from_metrics_summary(m)
        assert row.skewness == 0.5
        assert row.kurtosis == 3.2

    def test_execution_detail_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(
            filled_orders=40, partial_fills_count=2,
            total_spread_cost=100, total_slippage_cost=50, total_fees=25,
        )
        row = row_from_metrics_summary(m)
        assert row.filled_orders == 40
        assert row.partial_fills_count == 2
        assert row.total_spread_cost == 100
        assert row.total_slippage_cost == 50
        assert row.total_fees == 25

    def test_annualized_exposure_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(
            annualized_return=0.25, exposure_adjusted_return=0.30,
            avg_drawdown_duration_bars=50.0,
            avg_exposure=0.6, max_exposure=1.2, warnings_count=3,
        )
        row = row_from_metrics_summary(m)
        assert row.annualized_return == 0.25
        assert row.exposure_adjusted_return == 0.30
        assert row.avg_drawdown_duration_bars == 50.0
        assert row.avg_exposure == 0.6
        assert row.max_exposure == 1.2
        assert row.warnings_count == 3

    def test_data_quality_fields(self):
        from solat_engine.backtest.models import MetricsSummary
        m = MetricsSummary(missing_bar_pct=0.5, data_gaps_detected=3)
        row = row_from_metrics_summary(m)
        assert row.missing_bar_pct == 0.5
        assert row.data_gaps_detected == 3


# ---------------------------------------------------------------------------
# New leaderboard sections
# ---------------------------------------------------------------------------

class TestNewLeaderboardSections:
    def test_return_leaderboard_present(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta)
        assert "by Return%" in md

    def test_drawdown_leaderboard_present(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta)
        assert "by Max Drawdown%" in md

    def test_most_active_leaderboard_present(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta)
        assert "by Trades/Day" in md


# ---------------------------------------------------------------------------
# Column glossary
# ---------------------------------------------------------------------------

class TestColumnGlossary:
    def test_glossary_present(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(sweep_name="Test")
        md = render_markdown(rows, meta)
        assert "## Appendix: Column Glossary" in md

    def test_glossary_covers_key_columns(self):
        from solat_engine.reporting.sweep_report import COLUMN_GLOSSARY
        for col in ["sharpe", "sortino", "calmar", "profit_factor",
                     "verdict", "verdict_flags", "skewness", "kurtosis",
                     "start_equity", "end_equity", "missing_bar_pct"]:
            assert col in COLUMN_GLOSSARY, f"Glossary missing column: {col}"

    def test_glossary_matches_field_names(self):
        from solat_engine.reporting.sweep_report import COLUMN_GLOSSARY
        field_names = set(ComboResultRow.field_names())
        glossary_cols = set(COLUMN_GLOSSARY.keys())
        assert glossary_cols == field_names, (
            f"Glossary/fields mismatch. "
            f"Missing from glossary: {field_names - glossary_cols}. "
            f"Extra in glossary: {glossary_cols - field_names}"
        )


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    def test_identical_input_identical_output(self):
        rows = _sample_rows()
        meta = SweepReportMetadata(
            sweep_name="Determinism Test",
            generated_at="2026-02-15 12:00 UTC",
        )
        md1 = render_markdown(rows, meta)
        md2 = render_markdown(rows, meta)
        assert md1 == md2, "Same inputs must produce identical markdown"


# ---------------------------------------------------------------------------
# CSV all columns
# ---------------------------------------------------------------------------

class TestCsvAllColumns:
    def test_csv_contains_all_new_fields(self):
        rows = [_make_row(skewness=0.5, kurtosis=3.0, missing_bar_pct=1.2)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            write_csv(rows, path)
            header = path.read_text().split("\n")[0]
            for col in ["skewness", "kurtosis", "missing_bar_pct",
                         "data_gaps_detected", "filled_orders", "verdict_flags",
                         "start_equity", "end_equity", "sweep_id",
                         "annualized_return", "avg_exposure", "warnings_count"]:
                assert col in header, f"CSV missing column: {col}"


# ---------------------------------------------------------------------------
# Sweep ID passthrough
# ---------------------------------------------------------------------------

class TestSweepId:
    def test_sweep_id_in_row(self):
        row = _make_row(sweep_id="abc123")
        assert row.sweep_id == "abc123"
        assert row.to_dict()["sweep_id"] == "abc123"

    def test_sweep_id_in_field_names(self):
        assert "sweep_id" in ComboResultRow.field_names()
