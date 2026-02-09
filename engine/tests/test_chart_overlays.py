"""
Tests for chart overlay API routes.

Tests indicator computation and chart data endpoints.
Uses synthetic data - NO REAL NETWORK CALLS.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from solat_engine.api.rate_limit import reset_rate_limiters
from solat_engine.data.models import HistoricalBar, SupportedTimeframe
from solat_engine.data.parquet_store import ParquetStore
from solat_engine.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiters_fixture():
    """Reset rate limiters before each test."""
    reset_rate_limiters()
    yield
    reset_rate_limiters()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_parquet_store():
    """Create a temporary parquet store with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ParquetStore(Path(tmpdir))

        # Create test bars
        bars = []
        base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        base_price = 1.1000

        for i in range(100):
            ts = base + timedelta(minutes=i)
            # Create slightly varying prices
            price = base_price + (i % 20) * 0.0001
            bars.append(
                HistoricalBar(
                    timestamp_utc=ts,
                    instrument_symbol="EURUSD",
                    timeframe=SupportedTimeframe.M1,
                    open=price,
                    high=price + 0.0005,
                    low=price - 0.0005,
                    close=price + 0.0002,
                    volume=100.0 + i,
                )
            )

        store.write_bars(bars)
        yield store


@pytest.fixture(autouse=True)
def reset_data_routes():
    """Reset data routes singleton between tests."""
    from solat_engine.api import data_routes

    original = data_routes._parquet_store
    yield
    data_routes._parquet_store = original


# =============================================================================
# Available Indicators Tests
# =============================================================================


class TestAvailableIndicators:
    """Tests for /chart/available-indicators endpoint."""

    def test_list_available_indicators(self) -> None:
        """Should return list of available indicators."""
        response = client.get("/chart/available-indicators")

        assert response.status_code == 200
        data = response.json()
        assert "indicators" in data

        # Check some expected indicators
        indicator_names = [i["name"] for i in data["indicators"]]
        assert "ema" in indicator_names
        assert "sma" in indicator_names
        assert "rsi" in indicator_names
        assert "macd" in indicator_names
        assert "bollinger" in indicator_names
        assert "ichimoku" in indicator_names

    def test_indicators_have_required_fields(self) -> None:
        """Each indicator should have required fields."""
        response = client.get("/chart/available-indicators")

        assert response.status_code == 200
        for indicator in response.json()["indicators"]:
            assert "name" in indicator
            assert "display" in indicator
            assert "description" in indicator
            assert "params" in indicator
            assert "example" in indicator


# =============================================================================
# Overlay Computation Tests
# =============================================================================


class TestOverlayComputation:
    """Tests for /chart/overlays endpoint."""

    def test_overlays_requires_indicators(self) -> None:
        """Should require at least one indicator."""
        response = client.post(
            "/chart/overlays",
            json={
                "symbol": "EURUSD",
                "timeframe": "1m",
                "indicators": [],
            },
        )

        assert response.status_code == 422  # Validation error

    def test_overlays_validates_timeframe(self) -> None:
        """Should reject invalid timeframe."""
        response = client.post(
            "/chart/overlays",
            json={
                "symbol": "EURUSD",
                "timeframe": "invalid",
                "indicators": ["ema_20"],
            },
        )

        assert response.status_code == 400
        assert "Invalid timeframe" in response.json()["detail"]

    def test_overlays_returns_empty_for_no_data(self) -> None:
        """Should return empty for symbol with no data."""
        response = client.post(
            "/chart/overlays",
            json={
                "symbol": "UNKNOWN",
                "timeframe": "1m",
                "indicators": ["ema_20"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bars"] == []
        assert data["overlays"] == []
        assert data["count"] == 0

    def test_overlays_computes_ema(self, temp_parquet_store) -> None:
        """Should compute EMA overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["ema_20"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["bars"]) == 50
            assert len(data["overlays"]) == 1
            assert data["overlays"][0]["name"] == "EMA(20)"
            assert data["overlays"][0]["type"] == "line"
            assert len(data["overlays"][0]["data"]) == 50

    def test_overlays_computes_sma(self, temp_parquet_store) -> None:
        """Should compute SMA overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["sma_50"],
                    "limit": 100,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["overlays"]) == 1
            assert data["overlays"][0]["name"] == "SMA(50)"

    def test_overlays_computes_rsi(self, temp_parquet_store) -> None:
        """Should compute RSI overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["rsi_14"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "RSI(14)"
            assert overlay["type"] == "oscillator"

            # RSI values should be between 0 and 100
            for point in overlay["data"]:
                assert 0 <= point["value"] <= 100

    def test_overlays_computes_macd(self, temp_parquet_store) -> None:
        """Should compute MACD overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["macd"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "MACD"
            assert overlay["type"] == "macd"

            # MACD data should have macd, signal, histogram
            for point in overlay["data"]:
                assert "macd" in point
                assert "signal" in point
                assert "histogram" in point

    def test_overlays_computes_bollinger(self, temp_parquet_store) -> None:
        """Should compute Bollinger Bands overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["bb_20_2"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "BB(20,2.0)"
            assert overlay["type"] == "band"

            # Band data should have upper, middle, lower
            for point in overlay["data"]:
                assert "upper" in point
                assert "middle" in point
                assert "lower" in point
                # Upper > middle > lower
                assert point["upper"] >= point["middle"] >= point["lower"]

    def test_overlays_computes_ichimoku(self, temp_parquet_store) -> None:
        """Should compute Ichimoku overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["ichimoku"],
                    "limit": 100,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "Ichimoku"
            assert overlay["type"] == "cloud"

            # Ichimoku data should have all components
            for point in overlay["data"]:
                assert "tenkan" in point
                assert "kijun" in point
                assert "senkou_a" in point
                assert "senkou_b" in point
                assert "chikou" in point

    def test_overlays_computes_stochastic(self, temp_parquet_store) -> None:
        """Should compute Stochastic overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["stoch_14_3"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "Stoch(14,3)"
            assert overlay["type"] == "oscillator"

            # Stochastic data should have k and d
            for point in overlay["data"]:
                assert "k" in point
                assert "d" in point
                # Values should be between 0 and 100
                assert 0 <= point["k"] <= 100
                assert 0 <= point["d"] <= 100

    def test_overlays_computes_atr(self, temp_parquet_store) -> None:
        """Should compute ATR overlay."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["atr_14"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            overlay = data["overlays"][0]
            assert overlay["name"] == "ATR(14)"
            assert overlay["type"] == "line"

            # ATR values should be positive
            for point in overlay["data"]:
                assert point["value"] >= 0

    def test_overlays_multiple_indicators(self, temp_parquet_store) -> None:
        """Should compute multiple overlays at once."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["ema_20", "sma_50", "rsi_14"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["overlays"]) == 3

            names = [o["name"] for o in data["overlays"]]
            assert "EMA(20)" in names
            assert "SMA(50)" in names
            assert "RSI(14)" in names

    def test_overlays_ignores_invalid_indicators(self, temp_parquet_store) -> None:
        """Should skip invalid indicators and continue."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.post(
                "/chart/overlays",
                json={
                    "symbol": "EURUSD",
                    "timeframe": "1m",
                    "indicators": ["ema_20", "invalid_indicator", "sma_50"],
                    "limit": 50,
                },
            )

            assert response.status_code == 200
            data = response.json()
            # Should have 2 overlays (invalid one skipped)
            assert len(data["overlays"]) == 2


# =============================================================================
# GET Overlay Endpoint Tests
# =============================================================================


class TestOverlayGet:
    """Tests for GET /chart/overlays/{symbol} endpoint."""

    def test_get_overlays_simple(self, temp_parquet_store) -> None:
        """GET endpoint should work with query params."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.get(
                "/chart/overlays/EURUSD?timeframe=1m&indicators=ema_20,sma_50&limit=50"
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["overlays"]) == 2

    def test_get_overlays_default_indicators(self, temp_parquet_store) -> None:
        """GET endpoint should use default indicators."""
        with patch(
            "solat_engine.api.data_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ), patch(
            "solat_engine.api.chart_routes.get_parquet_store",
            return_value=temp_parquet_store,
        ):
            response = client.get("/chart/overlays/EURUSD")

            assert response.status_code == 200
            data = response.json()
            # Default is ema_20, ema_50
            assert len(data["overlays"]) == 2


# =============================================================================
# Signals Endpoint Tests
# =============================================================================


class TestSignals:
    """Tests for /chart/signals endpoint."""

    def test_signals_returns_empty(self) -> None:
        """Signals should return empty list initially."""
        response = client.post(
            "/chart/signals",
            json={
                "symbol": "EURUSD",
                "timeframe": "1m",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["markers"] == []
        assert data["count"] == 0

    def test_get_signals_simple(self) -> None:
        """GET signals endpoint should work."""
        response = client.get("/chart/signals/EURUSD")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "EURUSD"


# =============================================================================
# Indicator Parsing Tests
# =============================================================================


class TestIndicatorParsing:
    """Tests for indicator string parsing."""

    def test_parse_ema_with_period(self) -> None:
        """Should parse ema_20 correctly."""
        from solat_engine.api.chart_routes import parse_indicator

        name, params = parse_indicator("ema_20")
        assert name == "ema"
        assert params["period"] == 20

    def test_parse_macd_with_params(self) -> None:
        """Should parse macd_12_26_9 correctly."""
        from solat_engine.api.chart_routes import parse_indicator

        name, params = parse_indicator("macd_12_26_9")
        assert name == "macd"
        assert params["fast"] == 12
        assert params["slow"] == 26
        assert params["signal"] == 9

    def test_parse_bollinger_with_params(self) -> None:
        """Should parse bb_20_2 correctly."""
        from solat_engine.api.chart_routes import parse_indicator

        name, params = parse_indicator("bb_20_2")
        assert name == "bollinger"
        assert params["period"] == 20
        assert params["std_dev"] == 2.0

    def test_parse_ichimoku(self) -> None:
        """Should parse ichimoku correctly."""
        from solat_engine.api.chart_routes import parse_indicator

        name, params = parse_indicator("ichimoku")
        assert name == "ichimoku"
        assert params == {}

    def test_parse_stochastic_with_params(self) -> None:
        """Should parse stoch_14_3 correctly."""
        from solat_engine.api.chart_routes import parse_indicator

        name, params = parse_indicator("stoch_14_3")
        assert name == "stochastic"
        assert params["k_period"] == 14
        assert params["d_period"] == 3

    def test_parse_unknown_indicator_raises(self) -> None:
        """Should raise for unknown indicator."""
        from solat_engine.api.chart_routes import parse_indicator

        with pytest.raises(ValueError, match="Unknown indicator"):
            parse_indicator("unknown")
