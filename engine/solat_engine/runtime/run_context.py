"""
Run context for tracking backtest/live runs.

Provides unique run IDs and context management.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


def generate_run_id(prefix: str = "run") -> str:
    """
    Generate a unique run ID.

    Format: {prefix}_{timestamp}_{uuid8}
    Example: run_20240115_143022_a1b2c3d4

    Args:
        prefix: ID prefix (e.g., "backtest", "live")

    Returns:
        Unique run ID string.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{short_uuid}"


class RunType(str, Enum):
    """Type of run."""

    BACKTEST = "backtest"
    PAPER = "paper"  # Demo/paper trading
    LIVE = "live"


@dataclass
class RunContext:
    """
    Context for a backtest or live trading run.

    Tracks run metadata, configuration snapshot, and artefact paths.
    """

    # Identification
    run_id: str
    run_type: RunType
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Configuration snapshot (for reproducibility)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    strategy_id: str | None = None
    strategy_params: dict[str, Any] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    timeframe: str | None = None

    # Date range (for backtests)
    start_date: datetime | None = None
    end_date: datetime | None = None

    # Paths
    artefacts_dir: Path | None = None

    # Status
    is_completed: bool = False
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "run_type": self.run_type.value,
            "created_at": self.created_at.isoformat(),
            "config_snapshot": self.config_snapshot,
            "strategy_id": self.strategy_id,
            "strategy_params": self.strategy_params,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "artefacts_dir": str(self.artefacts_dir) if self.artefacts_dir else None,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    @classmethod
    def create_backtest(
        cls,
        strategy_id: str,
        symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        params: dict[str, Any] | None = None,
    ) -> "RunContext":
        """
        Create a run context for a backtest.

        Args:
            strategy_id: Strategy identifier
            symbols: List of symbols to test
            timeframe: Trading timeframe
            start_date: Backtest start date
            end_date: Backtest end date
            params: Strategy parameters

        Returns:
            New RunContext configured for backtesting.
        """
        return cls(
            run_id=generate_run_id("backtest"),
            run_type=RunType.BACKTEST,
            strategy_id=strategy_id,
            strategy_params=params or {},
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

    @classmethod
    def create_live(
        cls,
        strategy_id: str,
        symbols: list[str],
        timeframe: str,
        is_demo: bool = True,
        params: dict[str, Any] | None = None,
    ) -> "RunContext":
        """
        Create a run context for live/paper trading.

        Args:
            strategy_id: Strategy identifier
            symbols: List of symbols to trade
            timeframe: Trading timeframe
            is_demo: Whether this is demo/paper trading
            params: Strategy parameters

        Returns:
            New RunContext configured for live trading.
        """
        run_type = RunType.PAPER if is_demo else RunType.LIVE
        return cls(
            run_id=generate_run_id(run_type.value),
            run_type=run_type,
            strategy_id=strategy_id,
            strategy_params=params or {},
            symbols=symbols,
            timeframe=timeframe,
        )

    def mark_completed(self, error: str | None = None) -> None:
        """Mark the run as completed."""
        self.is_completed = True
        self.completed_at = datetime.now(UTC)
        self.error = error
