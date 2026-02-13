"""
Tests for optimization API routes.

Covers:
- POST /optimization/walk-forward returns real run_id
- POST /optimization/selector/run with mock WFO result
- Proposal CRUD + apply (DEMO only)
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from solat_engine.optimization.models import (
    WalkForwardConfig,
    WalkForwardResult,
)
from solat_engine.optimization.walk_forward import WalkForwardEngine
from solat_engine.scheduler.service import SchedulerService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_optimization_singletons():
    """Reset optimization singletons between tests."""
    from solat_engine.api import optimization_routes
    optimization_routes._wf_engine = None
    optimization_routes._scheduler_service = None
    optimization_routes._allowlist_manager = None


# =============================================================================
# Walk-Forward Tests
# =============================================================================


class TestWalkForwardRunId:
    """POST /optimization/walk-forward returns real run_id (not 'wf-pending')."""

    def test_returns_real_run_id(self, app_client: TestClient):
        response = app_client.post("/optimization/walk-forward", json={
            "symbols": ["EURUSD"],
            "bots": ["TKCrossSniper"],
            "start_date": "2023-01-01T00:00:00Z",
            "end_date": "2024-12-31T00:00:00Z",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["run_id"].startswith("wf-")
        assert data["run_id"] != "wf-pending"
        assert len(data["run_id"]) > 5


# =============================================================================
# Selector Tests
# =============================================================================


class TestSelectorRoute:
    """POST /optimization/selector/run with mock WFO result."""

    def test_selector_returns_selected_combos(self, app_client: TestClient, overrider):
        """Inject a fake WFO result and run the selector."""
        from solat_engine.api.optimization_routes import get_walk_forward_engine

        # Create a mock engine with a fake completed result
        mock_engine = MagicMock(spec=WalkForwardEngine)

        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
        )

        mock_result = WalkForwardResult(
            run_id="wf-mock123",
            config=config,
            status="completed",
            recommended_combos=[
                {
                    "combo_id": "EURUSD:TKCross:1h",
                    "symbol": "EURUSD",
                    "bot": "TKCross",
                    "timeframe": "1h",
                    "avg_sharpe": 2.0,
                    "avg_win_rate": 0.6,
                    "avg_return_pct": 10.0,
                    "total_trades": 100,
                    "avg_drawdown_pct": 5.0,
                    "sharpe_std": 0.5,
                    "sharpe_cv": 0.25,
                    "folds_profitable_pct": 0.9,
                    "windows_count": 5,
                    "consistency_score": 4.0,
                },
            ],
        )
        mock_engine.get_result.return_value = mock_result

        overrider.override(get_walk_forward_engine, lambda: mock_engine)

        response = app_client.post("/optimization/selector/run", json={
            "wfo_run_id": "wf-mock123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert len(data["selected"]) == 1
        assert data["selected"][0]["symbol"] == "EURUSD"
        assert data["selected"][0]["rank"] == 1
        assert "rationale" in data["selected"][0]

    def test_selector_404_for_missing_run(self, app_client: TestClient, overrider):
        from solat_engine.api.optimization_routes import get_walk_forward_engine

        mock_engine = MagicMock(spec=WalkForwardEngine)
        mock_engine.get_result.return_value = None
        overrider.override(get_walk_forward_engine, lambda: mock_engine)

        response = app_client.post("/optimization/selector/run", json={
            "wfo_run_id": "wf-nonexistent",
        })
        assert response.status_code == 404


# =============================================================================
# Proposal Tests
# =============================================================================


class TestProposalCRUD:
    """Proposal CRUD and apply endpoints."""

    def test_list_proposals_empty(self, app_client: TestClient, mock_settings):
        from solat_engine.api.optimization_routes import set_scheduler_service

        svc = SchedulerService(data_dir=mock_settings.data_dir)
        set_scheduler_service(svc)

        try:
            response = app_client.get("/optimization/proposals")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            set_scheduler_service(None)

    def test_create_and_get_proposal(self, app_client: TestClient, mock_settings):
        from solat_engine.api.optimization_routes import set_scheduler_service

        svc = SchedulerService(data_dir=mock_settings.data_dir)
        set_scheduler_service(svc)

        try:
            # Create a proposal manually
            proposal = svc.create_proposal(
                selected_combos=[
                    {"symbol": "EURUSD", "bot": "TKCross", "timeframe": "1h"}
                ],
                wfo_run_id="wf-test",
                message="Test proposal",
            )

            # Get by ID
            response = app_client.get(f"/optimization/proposals/{proposal.proposal_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["proposal_id"] == proposal.proposal_id
            assert data["status"] == "pending"
            assert len(data["selected_combos"]) == 1

            # List
            response = app_client.get("/optimization/proposals")
            assert response.status_code == 200
            assert len(response.json()) == 1
        finally:
            set_scheduler_service(None)

    def test_apply_proposal_demo(self, app_client: TestClient, mock_settings):
        """Applying proposal in DEMO mode should work."""
        from solat_engine.api.optimization_routes import set_scheduler_service

        svc = SchedulerService(data_dir=mock_settings.data_dir)
        set_scheduler_service(svc)

        try:
            proposal = svc.create_proposal(
                selected_combos=[
                    {
                        "symbol": "EURUSD",
                        "bot": "TKCross",
                        "timeframe": "1h",
                        "metrics": {"avg_sharpe": 2.0, "avg_win_rate": 0.6, "total_trades": 50},
                    }
                ],
                wfo_run_id="wf-test",
            )

            response = app_client.post(
                f"/optimization/deploy/proposal/{proposal.proposal_id}/apply"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "applied"
        finally:
            set_scheduler_service(None)

    def test_apply_proposal_not_found(self, app_client: TestClient, mock_settings):
        from solat_engine.api.optimization_routes import set_scheduler_service

        svc = SchedulerService(data_dir=mock_settings.data_dir)
        set_scheduler_service(svc)

        try:
            response = app_client.post("/optimization/deploy/proposal/nonexistent/apply")
            assert response.status_code == 404
        finally:
            set_scheduler_service(None)

    def test_scheduler_status(self, app_client: TestClient, mock_settings):
        from solat_engine.api.optimization_routes import set_scheduler_service

        svc = SchedulerService(data_dir=mock_settings.data_dir)
        set_scheduler_service(svc)

        try:
            response = app_client.get("/optimization/scheduler/status")
            assert response.status_code == 200
            data = response.json()
            assert "jobs" in data
            assert "nightly_data_check" in data["jobs"]
            assert "weekly_optimize" in data["jobs"]
        finally:
            set_scheduler_service(None)


# =============================================================================
# Allowlist Tests
# =============================================================================


class TestGroupedAllowlist:
    """Tests for GET /optimization/allowlist/grouped endpoint."""

    def test_grouped_empty(self, app_client: TestClient, mock_settings, overrider):
        """Should return empty list when no allowlist entries."""
        from solat_engine.api.optimization_routes import get_allowlist_manager
        from solat_engine.optimization.allowlist import AllowlistManager

        mgr = AllowlistManager(data_dir=mock_settings.data_dir)
        overrider.override(get_allowlist_manager, lambda: mgr)

        response = app_client.get("/optimization/allowlist/grouped")
        assert response.status_code == 200
        assert response.json() == []

    def test_grouped_returns_by_symbol(self, app_client: TestClient, mock_settings, overrider):
        """Should group entries by symbol."""
        from solat_engine.api.optimization_routes import get_allowlist_manager
        from solat_engine.optimization.allowlist import AllowlistManager
        from solat_engine.optimization.models import AllowlistEntry

        mgr = AllowlistManager(data_dir=mock_settings.data_dir)
        mgr.add_entry(AllowlistEntry(
            symbol="EURUSD", bot="CloudTwist", timeframe="1h",
            sharpe=2.5, total_trades=50, enabled=True,
            validated_at=datetime.now(UTC),
        ))
        mgr.add_entry(AllowlistEntry(
            symbol="EURUSD", bot="MomentumRider", timeframe="1h",
            sharpe=1.8, total_trades=40, enabled=True,
            validated_at=datetime.now(UTC),
        ))
        mgr.add_entry(AllowlistEntry(
            symbol="GBPUSD", bot="CloudTwist", timeframe="1h",
            sharpe=2.0, total_trades=45, enabled=False,
            validated_at=datetime.now(UTC),
        ))
        overrider.override(get_allowlist_manager, lambda: mgr)

        response = app_client.get("/optimization/allowlist/grouped")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # EURUSD and GBPUSD

        # Sorted by symbol
        assert data[0]["symbol"] == "EURUSD"
        assert len(data[0]["bots"]) == 2
        assert data[1]["symbol"] == "GBPUSD"
        assert len(data[1]["bots"]) == 1
        assert data[1]["bots"][0]["enabled"] is False
