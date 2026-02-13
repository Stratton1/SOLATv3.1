"""
Tests for recommendation API routes.

Covers:
- POST /optimization/recommendations/generate
- GET /optimization/recommendations/latest
- GET /optimization/recommendations/{id}
- GET /optimization/recommendations
- POST /optimization/recommendations/{id}/apply-demo
- LIVE mode blocking
- Supersede behaviour
- Empty WFO results
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from solat_engine.optimization.models import (
    WalkForwardConfig,
    WalkForwardResult,
)
from solat_engine.optimization.recommended_set import RecommendedSetManager
from solat_engine.optimization.walk_forward import WalkForwardEngine


def _make_completed_wfo(run_id: str = "wf-test1") -> WalkForwardResult:
    """Create a completed WFO result with recommended combos."""
    return WalkForwardResult(
        run_id=run_id,
        config=WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["CloudTwist"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        status="completed",
        progress=100.0,
        total_windows=3,
        completed_windows=3,
        recommended_combos=[
            {
                "symbol": "EURUSD",
                "bot": "CloudTwist",
                "timeframe": "1h",
                "avg_sharpe": 2.5,
                "avg_win_rate": 0.6,
                "avg_return_pct": 15.0,
                "total_trades": 50,
                "sharpe_cv": 0.5,
                "folds_profitable_pct": 0.8,
                "consistency_score": 5.0,
                "windows_count": 3,
            },
            {
                "symbol": "GBPUSD",
                "bot": "CloudTwist",
                "timeframe": "1h",
                "avg_sharpe": 1.8,
                "avg_win_rate": 0.55,
                "avg_return_pct": 10.0,
                "total_trades": 40,
                "sharpe_cv": 0.8,
                "folds_profitable_pct": 0.7,
                "consistency_score": 2.25,
                "windows_count": 3,
            },
        ],
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_recommendation_singletons():
    """Reset recommendation singletons between tests."""
    from solat_engine.api import recommendation_routes
    recommendation_routes._recommended_set_manager = None


@pytest.fixture
def mock_wf_engine():
    """Mock WalkForwardEngine with a completed result."""
    engine = MagicMock(spec=WalkForwardEngine)
    engine.get_result.return_value = _make_completed_wfo()
    return engine


@pytest.fixture
def app_client_rec(app_client: TestClient, mock_settings, mock_wf_engine, overrider):
    """Test client with recommendation-specific overrides."""
    from solat_engine.api.recommendation_routes import (
        get_recommended_set_manager,
        get_wf_engine_for_recommendations,
    )

    mgr = RecommendedSetManager(data_dir=mock_settings.data_dir)

    overrider.override(get_wf_engine_for_recommendations, lambda: mock_wf_engine)
    overrider.override(get_recommended_set_manager, lambda: mgr)

    return app_client


# =============================================================================
# Tests
# =============================================================================


class TestGenerateRecommendations:
    def test_generate_returns_set(self, app_client_rec):
        resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"].startswith("recset-")
        assert data["status"] == "pending"
        assert len(data["combos"]) == 2
        assert data["rejected_count"] == 0
        assert "wf-test1" in data["source_run_ids"]

    def test_generate_with_custom_constraints(self, app_client_rec):
        resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={
                "wfo_run_ids": ["wf-test1"],
                "min_oos_sharpe": 2.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only EURUSD has sharpe >= 2.0
        assert len(data["combos"]) == 1
        assert data["combos"][0]["symbol"] == "EURUSD"

    def test_generate_wfo_not_found(self, app_client_rec, mock_wf_engine):
        mock_wf_engine.get_result.return_value = None
        resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-missing"]},
        )
        assert resp.status_code == 404

    def test_generate_wfo_not_completed(self, app_client_rec, mock_wf_engine):
        result = _make_completed_wfo()
        result.status = "running"
        mock_wf_engine.get_result.return_value = result
        resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        assert resp.status_code == 400


class TestGetRecommendations:
    def test_get_latest_empty(self, app_client_rec):
        resp = app_client_rec.get("/optimization/recommendations/latest")
        assert resp.status_code == 404

    def test_get_by_id(self, app_client_rec):
        # Generate first
        gen_resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        rec_id = gen_resp.json()["id"]

        resp = app_client_rec.get(f"/optimization/recommendations/{rec_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rec_id

    def test_get_latest_after_generate(self, app_client_rec):
        app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        resp = app_client_rec.get("/optimization/recommendations/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_list_all(self, app_client_rec):
        app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        resp = app_client_rec.get("/optimization/recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "combos_count" in data[0]

    def test_get_by_id_not_found(self, app_client_rec):
        resp = app_client_rec.get("/optimization/recommendations/recset-notexist")
        assert resp.status_code == 404


class TestApplyDemo:
    def test_apply_demo_success(self, app_client_rec):
        gen_resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        rec_id = gen_resp.json()["id"]

        resp = app_client_rec.post(f"/optimization/recommendations/{rec_id}/apply-demo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "applied"
        assert data["combos_applied"] == 2

        # Verify status changed
        get_resp = app_client_rec.get(f"/optimization/recommendations/{rec_id}")
        assert get_resp.json()["status"] == "applied"

    def test_apply_demo_blocked_in_live(self, app_client_rec, mock_settings):
        mock_settings.mode = "LIVE"
        
        gen_resp = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        rec_id = gen_resp.json()["id"]

        resp = app_client_rec.post(f"/optimization/recommendations/{rec_id}/apply-demo")
        assert resp.status_code == 403

    def test_apply_supersedes_previous(self, app_client_rec):
        # Generate and apply first set
        gen1 = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        id1 = gen1.json()["id"]
        app_client_rec.post(f"/optimization/recommendations/{id1}/apply-demo")

        # Generate and apply second set
        gen2 = app_client_rec.post(
            "/optimization/recommendations/generate",
            json={"wfo_run_ids": ["wf-test1"]},
        )
        id2 = gen2.json()["id"]
        app_client_rec.post(f"/optimization/recommendations/{id2}/apply-demo")

        # First should be superseded
        get1 = app_client_rec.get(f"/optimization/recommendations/{id1}")
        assert get1.json()["status"] == "superseded"

        # Second should be applied
        get2 = app_client_rec.get(f"/optimization/recommendations/{id2}")
        assert get2.json()["status"] == "applied"

    def test_apply_not_found(self, app_client_rec):
        resp = app_client_rec.post("/optimization/recommendations/recset-notexist/apply-demo")
        assert resp.status_code == 404
