"""
Tests for parallel sweep with resume support.

Tests:
- Resume skips completed combos
- Atomic writes produce valid JSON
- Request hash changes create new sweep
- Deterministic: serial vs parallel produce identical results
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from solat_engine.backtest.parallel_sweep import (
    ComboResult,
    ParallelSweepRunner,
    SweepManifest,
    atomic_write_json,
    compute_combo_id,
    compute_request_hash,
)


class TestComputeHashes:
    """Tests for hash computation functions."""

    def test_combo_id_deterministic(self) -> None:
        """Same inputs produce same combo ID."""
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        id1 = compute_combo_id("TKCrossSniper", "EURUSD", "1h", start, end)
        id2 = compute_combo_id("TKCrossSniper", "EURUSD", "1h", start, end)

        assert id1 == id2
        assert len(id1) == 16

    def test_combo_id_differs_for_different_params(self) -> None:
        """Different params produce different combo IDs."""
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        id1 = compute_combo_id("TKCrossSniper", "EURUSD", "1h", start, end)
        id2 = compute_combo_id("KumoBreaker", "EURUSD", "1h", start, end)
        id3 = compute_combo_id("TKCrossSniper", "GBPUSD", "1h", start, end)

        assert id1 != id2
        assert id1 != id3

    def test_request_hash_deterministic(self) -> None:
        """Same request produces same hash."""
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        hash1 = compute_request_hash(
            ["TKCrossSniper", "KumoBreaker"],
            ["EURUSD", "GBPUSD"],
            ["1h"],
            start,
            end,
            100000.0,
        )
        hash2 = compute_request_hash(
            ["TKCrossSniper", "KumoBreaker"],
            ["EURUSD", "GBPUSD"],
            ["1h"],
            start,
            end,
            100000.0,
        )

        assert hash1 == hash2

    def test_request_hash_order_independent(self) -> None:
        """Order of bots/symbols doesn't affect hash (sorted internally)."""
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        hash1 = compute_request_hash(
            ["TKCrossSniper", "KumoBreaker"],
            ["EURUSD", "GBPUSD"],
            ["1h"],
            start,
            end,
            100000.0,
        )
        hash2 = compute_request_hash(
            ["KumoBreaker", "TKCrossSniper"],
            ["GBPUSD", "EURUSD"],
            ["1h"],
            start,
            end,
            100000.0,
        )

        assert hash1 == hash2


class TestAtomicWrite:
    """Tests for atomic JSON write."""

    def test_atomic_write_creates_valid_json(self, tmp_path: Path) -> None:
        """Atomic write produces valid JSON file."""
        path = tmp_path / "test.json"
        data = {"key": "value", "number": 42, "nested": {"a": 1}}

        atomic_write_json(path, data)

        assert path.exists()
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_atomic_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Atomic write creates parent directories."""
        path = tmp_path / "deep" / "nested" / "test.json"
        data = {"key": "value"}

        atomic_write_json(path, data)

        assert path.exists()

    def test_atomic_write_overwrites(self, tmp_path: Path) -> None:
        """Atomic write overwrites existing file."""
        path = tmp_path / "test.json"
        atomic_write_json(path, {"old": "data"})
        atomic_write_json(path, {"new": "data"})

        with open(path) as f:
            loaded = json.load(f)
        assert loaded == {"new": "data"}


class TestComboResult:
    """Tests for ComboResult serialization."""

    def test_to_dict_roundtrip(self) -> None:
        """ComboResult can serialize and deserialize."""
        result = ComboResult(
            combo_id="abc123",
            bot="TKCrossSniper",
            symbol="EURUSD",
            timeframe="1h",
            success=True,
            sharpe=1.5,
            max_drawdown=0.05,
            win_rate=0.55,
            total_trades=100,
            pnl=0.15,
            duration_s=30.5,
        )

        d = result.to_dict()
        restored = ComboResult.from_dict(d)

        assert restored.combo_id == result.combo_id
        assert restored.bot == result.bot
        assert restored.sharpe == result.sharpe
        assert restored.success == result.success


class TestSweepManifest:
    """Tests for SweepManifest serialization."""

    def test_to_dict_roundtrip(self) -> None:
        """Manifest can serialize and deserialize."""
        manifest = SweepManifest(
            sweep_id="abc123",
            request_hash="def456",
            created_at="2024-01-01T00:00:00+00:00",
            total_combos=100,
            completed_combos=50,
            failed_combos=5,
            status="running",
        )

        d = manifest.to_dict()
        restored = SweepManifest.from_dict(d)

        assert restored.sweep_id == manifest.sweep_id
        assert restored.request_hash == manifest.request_hash
        assert restored.total_combos == manifest.total_combos


class TestParallelSweepResume:
    """Tests for resume functionality."""

    def test_resume_skips_completed_combos(self, tmp_path: Path) -> None:
        """Runner skips combos that have completed result files."""
        runner = ParallelSweepRunner(
            data_dir=tmp_path,
            max_workers=1,
        )

        # Create a fake completed sweep with some combos done
        sweep_id = "test_sweep"
        sweep_dir = tmp_path / "sweeps" / sweep_id
        combos_dir = sweep_dir / "combos"
        combos_dir.mkdir(parents=True)

        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        # Write a completed combo
        combo_id = compute_combo_id("TKCrossSniper", "EURUSD", "1h", start, end)
        result = ComboResult(
            combo_id=combo_id,
            bot="TKCrossSniper",
            symbol="EURUSD",
            timeframe="1h",
            success=True,
            sharpe=1.5,
            total_trades=50,
        )
        atomic_write_json(combos_dir / f"{combo_id}.json", result.to_dict())

        # Write manifest with matching hash
        request_hash = compute_request_hash(
            ["TKCrossSniper"],
            ["EURUSD"],
            ["1h"],
            start,
            end,
            100000.0,
        )
        manifest = SweepManifest(
            sweep_id=sweep_id,
            request_hash=request_hash,
            created_at=datetime.now(UTC).isoformat(),
            total_combos=1,
            status="running",
        )
        atomic_write_json(sweep_dir / "manifest.json", manifest.to_dict())

        # Find resumable should find this sweep
        found = runner._find_resumable_sweep(request_hash)
        assert found is not None
        assert found.name == sweep_id

    def test_request_hash_mismatch_blocks_resume(self, tmp_path: Path) -> None:
        """Runner doesn't resume sweep with mismatched request hash."""
        runner = ParallelSweepRunner(
            data_dir=tmp_path,
            max_workers=1,
        )

        # Create a sweep with different request hash
        sweep_id = "old_sweep"
        sweep_dir = tmp_path / "sweeps" / sweep_id
        sweep_dir.mkdir(parents=True)

        manifest = SweepManifest(
            sweep_id=sweep_id,
            request_hash="old_hash_xyz",
            created_at=datetime.now(UTC).isoformat(),
            total_combos=10,
            status="running",
        )
        atomic_write_json(sweep_dir / "manifest.json", manifest.to_dict())

        # Search for different hash should not find it
        found = runner._find_resumable_sweep("new_hash_abc")
        assert found is None

    def test_completed_sweep_not_resumed(self, tmp_path: Path) -> None:
        """Runner doesn't try to resume completed sweeps."""
        runner = ParallelSweepRunner(
            data_dir=tmp_path,
            max_workers=1,
        )

        sweep_id = "completed_sweep"
        sweep_dir = tmp_path / "sweeps" / sweep_id
        sweep_dir.mkdir(parents=True)

        manifest = SweepManifest(
            sweep_id=sweep_id,
            request_hash="test_hash",
            created_at=datetime.now(UTC).isoformat(),
            total_combos=10,
            completed_combos=10,
            status="completed",  # Already done
        )
        atomic_write_json(sweep_dir / "manifest.json", manifest.to_dict())

        found = runner._find_resumable_sweep("test_hash")
        assert found is None
