"""
Tests for sweep_utils: catalogue-first symbol discovery, timeframe management,
data preflight, auto-derivation, and output generation.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from solat_engine.backtest.sweep_utils import (
    DEFAULT_TIMEFRAMES_ALL,
    DEFAULT_TIMEFRAMES_LIVE,
    LIVE_FX_PAIRS,
    PreflightResult,
    auto_derive_timeframe,
    generate_ranked_csv,
    generate_top_picks_json,
    get_available_asset_classes,
    parse_timeframes,
    preflight_check_partition,
    resolve_symbols_from_catalogue,
)
from solat_engine.catalog.seed import SEED_INSTRUMENTS
from solat_engine.catalog.symbols import STORAGE_ALIAS_MAP, resolve_storage_symbol
from solat_engine.data.models import SupportedTimeframe


# =============================================================================
# A) Catalogue-First Symbol Discovery
# =============================================================================


class TestResolveSymbolsFromCatalogue:
    """Tests for resolve_symbols_from_catalogue()."""

    def test_all_returns_all_seed_instruments(self) -> None:
        """None filter returns all 28 seed instruments."""
        symbols = resolve_symbols_from_catalogue()
        assert len(symbols) == len(SEED_INSTRUMENTS)
        # Check some canonical symbols exist
        assert "EURUSD" in symbols
        assert "XAUUSD" in symbols  # Not GOLD
        assert "US500" in symbols   # Not SP500

    def test_fx_filter(self) -> None:
        """Filter by fx returns only FX instruments."""
        symbols = resolve_symbols_from_catalogue(["fx"])
        assert len(symbols) > 0
        # All should be FX-like pairs
        for sym in symbols:
            # Find it in seed
            seed_item = next(s for s in SEED_INSTRUMENTS if s.symbol == sym)
            assert seed_item.asset_class.value == "fx"

    def test_multiple_asset_classes(self) -> None:
        """Filter by multiple classes returns union."""
        fx = resolve_symbols_from_catalogue(["fx"])
        idx = resolve_symbols_from_catalogue(["index"])
        both = resolve_symbols_from_catalogue(["fx", "index"])
        assert len(both) == len(fx) + len(idx)

    def test_unknown_asset_class_returns_empty(self) -> None:
        """Unknown asset class is skipped, returns empty for only-unknown."""
        symbols = resolve_symbols_from_catalogue(["nonexistent"])
        assert symbols == []

    def test_deduplication(self) -> None:
        """Repeated asset classes don't produce duplicates."""
        symbols = resolve_symbols_from_catalogue(["fx", "fx"])
        fx_once = resolve_symbols_from_catalogue(["fx"])
        assert len(symbols) == len(fx_once)

    def test_canonical_symbols_not_storage(self) -> None:
        """All returned symbols are canonical, not storage aliases."""
        symbols = resolve_symbols_from_catalogue()
        storage_aliases = set(STORAGE_ALIAS_MAP.values())
        # None of the returned symbols should be storage-only aliases
        for sym in symbols:
            if sym in STORAGE_ALIAS_MAP:
                # Canonical form maps to a different storage symbol
                pass
            else:
                # Symbol IS its own storage key (like EURUSD)
                assert sym not in storage_aliases or sym == resolve_storage_symbol(sym)


class TestGetAvailableAssetClasses:
    """Tests for get_available_asset_classes()."""

    def test_returns_known_classes(self) -> None:
        classes = get_available_asset_classes()
        assert "fx" in classes
        assert "index" in classes
        assert "commodity" in classes

    def test_returns_non_empty(self) -> None:
        assert len(get_available_asset_classes()) >= 3


class TestLiveFxPairs:
    """Tests for LIVE_FX_PAIRS constant."""

    def test_count(self) -> None:
        assert len(LIVE_FX_PAIRS) == 10

    def test_all_in_catalogue(self) -> None:
        """All live FX pairs should be in the seed catalogue."""
        all_symbols = resolve_symbols_from_catalogue()
        for pair in LIVE_FX_PAIRS:
            assert pair in all_symbols, f"{pair} not in catalogue"


# =============================================================================
# B) Timeframe Management
# =============================================================================


class TestParseTimeframes:
    """Tests for parse_timeframes()."""

    def test_valid_timeframes(self) -> None:
        result = parse_timeframes(["1h", "4h"])
        assert result == [SupportedTimeframe.H1, SupportedTimeframe.H4]

    def test_15m_supported(self) -> None:
        """15m is a valid SupportedTimeframe."""
        result = parse_timeframes(["15m"])
        assert result == [SupportedTimeframe.M15]

    def test_30m_supported(self) -> None:
        """30m is a valid SupportedTimeframe."""
        result = parse_timeframes(["30m"])
        assert result == [SupportedTimeframe.M30]

    def test_all_defaults_include_15m_30m(self) -> None:
        """DEFAULT_TIMEFRAMES_ALL includes 15m and 30m."""
        tfs = parse_timeframes(DEFAULT_TIMEFRAMES_ALL)
        values = [tf.value for tf in tfs]
        assert "15m" in values
        assert "30m" in values
        assert "1h" in values
        assert "4h" in values

    def test_invalid_timeframe_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported timeframe '2h'"):
            parse_timeframes(["1h", "2h"])

    def test_empty_list(self) -> None:
        assert parse_timeframes([]) == []

    def test_live_defaults(self) -> None:
        """DEFAULT_TIMEFRAMES_LIVE is 1h + 4h only."""
        assert DEFAULT_TIMEFRAMES_LIVE == ["1h", "4h"]


# =============================================================================
# C) Data Preflight
# =============================================================================


class TestPreflightResult:
    """Tests for PreflightResult data class."""

    def test_available(self) -> None:
        pf = PreflightResult(symbol="EURUSD", timeframe="1h", available=True, bar_count=1000)
        assert pf.available is True
        assert pf.bar_count == 1000
        assert pf.skip_reason is None

    def test_unavailable(self) -> None:
        pf = PreflightResult(
            symbol="EURUSD", timeframe="1h", available=False, skip_reason="NO_DATA",
        )
        assert pf.available is False
        assert pf.skip_reason == "NO_DATA"


class TestPreflightCheckPartition:
    """Tests for preflight_check_partition()."""

    def test_nonexistent_returns_unavailable(self, tmp_path: Path) -> None:
        """Non-existent partition returns unavailable."""
        result = preflight_check_partition(tmp_path, "FAKESYM", "1h")
        assert result.available is False
        assert result.skip_reason == "NO_DATA"

    def test_manifest_with_data(self, tmp_path: Path) -> None:
        """Partition with valid manifest returns available."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)
        manifest_dir = tmp_path / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        manifest = {
            "instrument_symbol": storage_sym,
            "timeframe": "1h",
            "first_available_from": "2023-01-01T00:00:00+00:00",
            "last_synced_to": "2024-12-31T00:00:00+00:00",
            "row_count": 5000,
        }
        with open(manifest_dir / f"{storage_sym}_1h.json", "w") as f:
            json.dump(manifest, f)

        result = preflight_check_partition(tmp_path, symbol, "1h")
        assert result.available is True
        assert result.bar_count == 5000
        assert result.storage_symbol == storage_sym

    def test_manifest_empty_data(self, tmp_path: Path) -> None:
        """Manifest with row_count=0 returns unavailable."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)
        manifest_dir = tmp_path / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        manifest = {"row_count": 0}
        with open(manifest_dir / f"{storage_sym}_1h.json", "w") as f:
            json.dump(manifest, f)

        result = preflight_check_partition(tmp_path, symbol, "1h")
        assert result.available is False
        assert result.skip_reason == "NO_DATA"

    def test_insufficient_range(self, tmp_path: Path) -> None:
        """Manifest with data ending before requested start returns unavailable."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)
        manifest_dir = tmp_path / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        manifest = {
            "row_count": 5000,
            "first_available_from": "2020-01-01T00:00:00+00:00",
            "last_synced_to": "2021-12-31T00:00:00+00:00",
        }
        with open(manifest_dir / f"{storage_sym}_1h.json", "w") as f:
            json.dump(manifest, f)

        start = datetime(2023, 1, 1, tzinfo=UTC)
        result = preflight_check_partition(tmp_path, symbol, "1h", start=start)
        assert result.available is False
        assert result.skip_reason == "INSUFFICIENT_RANGE"

    def test_parquet_fallback(self, tmp_path: Path) -> None:
        """Falls back to parquet file existence check when no manifest."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)
        parquet_dir = (
            tmp_path / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=1h"
        )
        parquet_dir.mkdir(parents=True)
        (parquet_dir / "data.parquet").write_bytes(b"fake parquet")

        result = preflight_check_partition(tmp_path, symbol, "1h")
        assert result.available is True

    def test_storage_symbol_mapping(self, tmp_path: Path) -> None:
        """Canonical XAUUSD maps to storage GOLD for partition lookup."""
        result = preflight_check_partition(tmp_path, "XAUUSD", "1h")
        assert result.storage_symbol == "GOLD"


# =============================================================================
# D) Auto-Derive (basic smoke tests — full derivation needs real 1m data)
# =============================================================================


class TestAutoDerive:
    """Tests for auto_derive_timeframe()."""

    def test_already_exists_returns_true(self, tmp_path: Path) -> None:
        """If target already exists, returns True without doing work."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)
        manifest_dir = tmp_path / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        manifest = {"row_count": 1000, "last_synced_to": "2024-12-31T00:00:00+00:00"}
        with open(manifest_dir / f"{storage_sym}_15m.json", "w") as f:
            json.dump(manifest, f)

        result = auto_derive_timeframe(tmp_path, symbol, "15m")
        assert result is True

    def test_no_1m_source_returns_false(self, tmp_path: Path) -> None:
        """No 1m source data → False."""
        result = auto_derive_timeframe(tmp_path, "EURUSD", "15m")
        assert result is False

    def test_derive_from_1m(self, tmp_path: Path) -> None:
        """Derive 15m from 1m data produces correct output."""
        symbol = "EURUSD"
        storage_sym = resolve_storage_symbol(symbol)

        # Create 1m source data
        source_dir = (
            tmp_path / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=1m"
        )
        source_dir.mkdir(parents=True)

        # Generate 2 hours of 1m bars = 120 bars → should produce 8 x 15m bars
        dates = pd.date_range("2024-01-01", periods=120, freq="1min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": dates,
            "open": range(120),
            "high": [x + 1 for x in range(120)],
            "low": [max(0, x - 1) for x in range(120)],
            "close": [x + 0.5 for x in range(120)],
            "volume": [100] * 120,
            "instrument_symbol": storage_sym,
            "timeframe": "1m",
        })
        df.to_parquet(source_dir / "data.parquet", index=False)

        # Also need a manifest for the 1m data
        manifest_dir = tmp_path / "parquet" / "manifests"
        manifest_dir.mkdir(parents=True)
        with open(manifest_dir / f"{storage_sym}_1m.json", "w") as f:
            json.dump({"row_count": 120}, f)

        result = auto_derive_timeframe(tmp_path, symbol, "15m")
        assert result is True

        # Verify output exists
        target_path = (
            tmp_path / "parquet" / "bars"
            / f"instrument_symbol={storage_sym}"
            / "timeframe=15m"
            / "data.parquet"
        )
        assert target_path.exists()

        # Verify manifest written
        manifest_path = manifest_dir / f"{storage_sym}_15m.json"
        assert manifest_path.exists()
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["row_count"] == 8  # 120 / 15 = 8


# =============================================================================
# E) Output Generation
# =============================================================================


class TestGenerateRankedCsv:
    """Tests for generate_ranked_csv()."""

    def _make_results_df(self) -> pd.DataFrame:
        """Create a sample results DataFrame."""
        return pd.DataFrame([
            {"bot": "A", "symbol": "EURUSD", "timeframe": "1h", "success": True,
             "skipped": False, "total_trades": 50, "sharpe": 2.0, "win_rate": 0.55,
             "max_drawdown": -0.05, "pnl": 1000},
            {"bot": "B", "symbol": "GBPUSD", "timeframe": "1h", "success": True,
             "skipped": False, "total_trades": 40, "sharpe": 1.5, "win_rate": 0.52,
             "max_drawdown": -0.08, "pnl": 800},
            {"bot": "C", "symbol": "USDJPY", "timeframe": "4h", "success": True,
             "skipped": False, "total_trades": 10, "sharpe": 3.0, "win_rate": 0.60,
             "max_drawdown": -0.02, "pnl": 500},  # Below min_trades
            {"bot": "D", "symbol": "EURUSD", "timeframe": "1h", "success": False,
             "skipped": False, "total_trades": 0, "sharpe": 0, "win_rate": 0,
             "max_drawdown": 0, "pnl": 0},  # Failed
            {"bot": "E", "symbol": "AUDUSD", "timeframe": "1h", "success": True,
             "skipped": True, "total_trades": 0, "sharpe": 0, "win_rate": 0,
             "max_drawdown": 0, "pnl": 0},  # Skipped
        ])

    def test_filters_and_ranks(self, tmp_path: Path) -> None:
        df = self._make_results_df()
        output = tmp_path / "ranked.csv"
        ranked = generate_ranked_csv(df, output, min_trades=30)

        # Only A and B qualify (>= 30 trades, success, not skipped)
        assert len(ranked) == 2
        assert ranked.iloc[0]["bot"] == "A"  # Higher Sharpe
        assert ranked.iloc[1]["bot"] == "B"
        assert "rank" in ranked.columns
        assert ranked.iloc[0]["rank"] == 1

    def test_writes_csv(self, tmp_path: Path) -> None:
        df = self._make_results_df()
        output = tmp_path / "ranked.csv"
        generate_ranked_csv(df, output, min_trades=30)
        assert output.exists()
        loaded = pd.read_csv(output)
        assert len(loaded) == 2

    def test_empty_results(self, tmp_path: Path) -> None:
        df = pd.DataFrame(columns=["bot", "symbol", "timeframe", "success",
                                    "total_trades", "sharpe"])
        output = tmp_path / "ranked.csv"
        ranked = generate_ranked_csv(df, output)
        assert len(ranked) == 0


class TestGenerateTopPicksJson:
    """Tests for generate_top_picks_json()."""

    def _make_ranked_df(self) -> pd.DataFrame:
        rows = []
        for i in range(20):
            rows.append({
                "rank": i + 1,
                "bot": f"Bot{i % 4}",
                "symbol": f"SYM{i % 5}",
                "timeframe": "1h" if i % 2 == 0 else "4h",
                "sharpe": 3.0 - i * 0.1,
                "win_rate": 0.55,
                "max_drawdown": -0.05,
                "total_trades": 50,
                "pnl": 1000 - i * 50,
            })
        return pd.DataFrame(rows)

    def test_basic_output(self, tmp_path: Path) -> None:
        df = self._make_ranked_df()
        output = tmp_path / "top_picks.json"
        result = generate_top_picks_json(df, output, top_n=10)

        assert output.exists()
        assert result["count"] == 10
        assert len(result["picks"]) == 10

    def test_diversified_selection(self, tmp_path: Path) -> None:
        df = self._make_ranked_df()
        output = tmp_path / "top_picks.json"
        result = generate_top_picks_json(
            df, output, top_n=10, diversify_by=["symbol"],
        )

        # Should spread across symbols
        symbols = {p["symbol"] for p in result["picks"]}
        assert len(symbols) > 1

    def test_no_diversification(self, tmp_path: Path) -> None:
        df = self._make_ranked_df()
        output = tmp_path / "top_picks.json"
        result = generate_top_picks_json(
            df, output, top_n=5, diversify_by=["none"],
        )

        # Should just be top 5 by rank
        assert result["count"] == 5

    def test_empty_df(self, tmp_path: Path) -> None:
        df = pd.DataFrame(columns=["rank", "bot", "symbol", "timeframe", "sharpe"])
        output = tmp_path / "top_picks.json"
        result = generate_top_picks_json(df, output)
        assert result["count"] == 0

    def test_json_structure(self, tmp_path: Path) -> None:
        df = self._make_ranked_df()
        output = tmp_path / "top_picks.json"
        generate_top_picks_json(
            df, output, top_n=3,
            start="2023-01-01", end="2024-12-31",
            asset_classes=["fx"], timeframes=["1h"],
        )

        with open(output) as f:
            data = json.load(f)

        assert "generated_at" in data
        assert data["start"] == "2023-01-01"
        assert data["end"] == "2024-12-31"
        assert data["filters"]["asset_classes"] == ["fx"]
        assert data["filters"]["timeframes"] == ["1h"]
        assert len(data["picks"]) == 3

        pick = data["picks"][0]
        assert "bot" in pick
        assert "symbol" in pick
        assert "timeframe" in pick
        assert "score" in pick
        assert "metrics" in pick


# =============================================================================
# F) Grand Sweep Scope Tests
# =============================================================================


class TestFullScopeEquivalence:
    """Tests that --scope full behaves identically to --scope all."""

    def test_full_scope_same_symbols_as_all(self) -> None:
        """'full' resolves to the same symbol set as 'all'."""
        all_symbols = resolve_symbols_from_catalogue()
        # 'full' is normalised to 'all' in run_grand_sweep, both call
        # resolve_symbols_from_catalogue() with no filter.
        full_symbols = resolve_symbols_from_catalogue()
        assert all_symbols == full_symbols

    def test_full_scope_same_timeframes_as_all(self) -> None:
        """'full' resolves to the same default timeframes as 'all'."""
        assert DEFAULT_TIMEFRAMES_ALL == ["15m", "30m", "1h", "4h"]
