"""
Tier 4: Position snapshot memory leak verification.

Tests that position snapshots are cleared after flush,
preventing unbounded memory growth.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from solat_engine.api.execution_routes import get_ig_client
from solat_engine.config import get_settings_dep


@pytest.mark.chaos
@pytest.mark.tier4
class TestSnapshotFlushScenarios:
    """Tests for snapshot flush and memory leak prevention."""

    def test_snapshot_list_cleared_after_flush(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: Multiple reconciliations create snapshots, snapshots are flushed
        EXPECTED: _snapshots list cleared after each flush
        FAILURE MODE: _snapshots list grows unbounded, memory leak
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import PositionSnapshot, PositionView, OrderSide
        from solat_engine.main import app
        from datetime import datetime, UTC

        reset_execution_state()

        # Setup with temp directory
        mock_settings.data_dir = tmp_path
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        # Mock broker with open positions
        mock_ig_client.list_positions = AsyncMock(
            return_value=[
                {
                    "dealId": f"POS{i}",
                    "position": {
                        "dealId": f"POS{i}",
                        "size": 1.0,
                        "direction": "BUY",
                    },
                    "market": {
                        "epic": "CS.D.EURUSD.CFD.IP",
                        "instrumentName": "EUR/USD",
                    },
                }
                for i in range(3)
            ]
        )

        mock_ig_client.list_accounts = AsyncMock(
            return_value=[
                {
                    "accountId": "ABC123",
                    "accountType": "CFD",
                    "balance": {"balance": 10000.0, "available": 10000.0},
                    "currency": "USD",
                }
            ]
        )

        with TestClient(app) as client:
            # Connect
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router = execution_routes._execution_router
            ledger = router._ledger

            # Verify ledger has snapshots attribute
            assert hasattr(ledger, "_snapshots"), "Ledger should have _snapshots list"

            # Manually add snapshots to test flush
            for i in range(5):
                snapshot = PositionSnapshot(
                    timestamp=datetime.now(UTC),
                    positions=[
                        PositionView(
                            deal_id=f"POS{i}",
                            epic="CS.D.EURUSD.CFD.IP",
                            direction=OrderSide.BUY,
                            size=1.0,
                            open_level=1.0850,
                        )
                    ],
                    total_count=1,
                )
                ledger._snapshots.append(snapshot)

            # Verify snapshots were added
            initial_count = len(ledger._snapshots)
            assert initial_count > 0, "Snapshots should be added"

            # Trigger snapshot flush (private method)
            ledger._flush_snapshots()

            # CRITICAL: Verify _snapshots list was cleared after flush
            final_count = len(ledger._snapshots)
            assert final_count == 0, (
                f"Snapshots should be cleared after flush. "
                f"Initial: {initial_count}, Final: {final_count}"
            )

            # Verify snapshot file was written
            snapshots_file = ledger._snapshots_path
            assert snapshots_file.exists(), (
                f"Snapshot file should be written at {snapshots_file}"
            )

    def test_repeated_flushes_no_memory_leak(
        self, overrider, mock_settings, mock_ig_client, tmp_path
    ) -> None:
        """
        SCENARIO: 100 reconciliations, each followed by flush
        EXPECTED: _snapshots list remains empty/small after each flush
        FAILURE MODE: _snapshots list grows to 100+ entries, memory leak
        """
        from solat_engine.api.execution_routes import reset_execution_state
        from solat_engine.api import execution_routes
        from solat_engine.execution.models import PositionSnapshot, PositionView, OrderSide
        from solat_engine.main import app
        from datetime import datetime, UTC

        reset_execution_state()

        mock_settings.data_dir = tmp_path
        overrider.override(get_settings_dep, lambda: mock_settings)
        overrider.override(get_ig_client, lambda: mock_ig_client)

        mock_ig_client.list_positions = AsyncMock(return_value=[])
        mock_ig_client.list_accounts = AsyncMock(
            return_value=[
                {
                    "accountId": "ABC123",
                    "accountType": "CFD",
                    "balance": {"balance": 10000.0, "available": 10000.0},
                    "currency": "USD",
                }
            ]
        )

        with TestClient(app) as client:
            connect_resp = client.post("/execution/connect")
            assert connect_resp.status_code == 200

            router = execution_routes._execution_router
            ledger = router._ledger

            # Simulate 100 reconciliation cycles
            for i in range(100):
                # Add snapshot
                snapshot = PositionSnapshot(
                    timestamp=datetime.now(UTC),
                    positions=[
                        PositionView(
                            deal_id=f"POS{i}",
                            epic="CS.D.EURUSD.CFD.IP",
                            direction=OrderSide.BUY,
                            size=1.0,
                            open_level=1.0850,
                        )
                    ],
                    total_count=1,
                )
                ledger._snapshots.append(snapshot)

                # Flush immediately
                ledger._flush_snapshots()

                # Verify list is cleared after EACH flush
                assert len(ledger._snapshots) == 0, (
                    f"Iteration {i}: Snapshots should be cleared after flush. "
                    f"Found {len(ledger._snapshots)} entries (memory leak!)"
                )

            # If we got here, no memory leak occurred
            assert True, "No memory leak detected"
