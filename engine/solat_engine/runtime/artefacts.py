"""
Artefact management for run outputs.

Handles directory structure, file naming, and cleanup.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from solat_engine.runtime.run_context import RunContext


class ArtefactManager:
    """
    Manages artefact directories and files for runs.

    Directory structure:
    {data_dir}/
        runs/
            {run_id}/
                config.json      # Run configuration snapshot
                signals.parquet  # Generated signals
                orders.parquet   # Orders placed
                fills.parquet    # Order fills
                equity.parquet   # Equity curve
                metrics.json     # Performance metrics
                logs/
                    engine.log   # Engine logs
                    trades.log   # Trade-specific logs
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize artefact manager.

        Args:
            base_dir: Base data directory
        """
        self.base_dir = base_dir
        self.runs_dir = base_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_run_directory(self, run_context: RunContext) -> Path:
        """
        Create directory for a run.

        Args:
            run_context: Run context

        Returns:
            Path to run directory.
        """
        run_dir = self.runs_dir / run_context.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (run_dir / "logs").mkdir(exist_ok=True)

        # Save config snapshot
        self.save_config(run_context, run_dir)

        # Update run context with artefacts dir
        run_context.artefacts_dir = run_dir

        return run_dir

    def save_config(self, run_context: RunContext, run_dir: Path) -> Path:
        """
        Save run configuration.

        Args:
            run_context: Run context
            run_dir: Run directory

        Returns:
            Path to config file.
        """
        config_path = run_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(run_context.to_dict(), f, indent=2, default=str)
        return config_path

    def save_metrics(self, metrics: dict[str, Any], run_dir: Path) -> Path:
        """
        Save performance metrics.

        Args:
            metrics: Metrics dictionary
            run_dir: Run directory

        Returns:
            Path to metrics file.
        """
        metrics_path = run_dir / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
        return metrics_path

    def get_run_directory(self, run_id: str) -> Path | None:
        """
        Get directory for an existing run.

        Args:
            run_id: Run ID

        Returns:
            Path to run directory, or None if not found.
        """
        run_dir = self.runs_dir / run_id
        if run_dir.exists():
            return run_dir
        return None

    def list_runs(
        self,
        run_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List recent runs.

        Args:
            run_type: Filter by run type (backtest/paper/live)
            limit: Maximum number of runs to return

        Returns:
            List of run info dicts.
        """
        runs = []
        for run_dir in sorted(self.runs_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue

            config_path = run_dir / "config.json"
            if not config_path.exists():
                continue

            with open(config_path) as f:
                config = json.load(f)

            if run_type and config.get("run_type") != run_type:
                continue

            runs.append(config)
            if len(runs) >= limit:
                break

        return runs

    def cleanup_old_runs(
        self,
        keep_days: int = 30,
        run_type: str | None = None,
    ) -> int:
        """
        Clean up old run directories.

        Args:
            keep_days: Number of days to keep
            run_type: Only clean up specific run type

        Returns:
            Number of runs deleted.
        """
        cutoff = datetime.now(UTC).timestamp() - (keep_days * 86400)
        deleted = 0

        for run_dir in self.runs_dir.iterdir():
            if not run_dir.is_dir():
                continue

            config_path = run_dir / "config.json"
            if not config_path.exists():
                continue

            with open(config_path) as f:
                config = json.load(f)

            if run_type and config.get("run_type") != run_type:
                continue

            created_at = config.get("created_at", "")
            try:
                created_ts = datetime.fromisoformat(created_at).timestamp()
            except (ValueError, TypeError):
                continue

            if created_ts < cutoff:
                import shutil

                shutil.rmtree(run_dir)
                deleted += 1

        return deleted
