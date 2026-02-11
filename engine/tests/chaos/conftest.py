"""
Chaos testing configuration and shared fixtures.

Provides common fixtures and configuration for chaos/failure injection tests.
"""

import random
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def seed_random():
    """Seed random for reproducible chaos scenarios."""
    random.seed(42)
    yield
    random.seed()  # Reset after test


@pytest.fixture
def chaos_temp_dir():
    """Temporary directory for chaos tests."""
    with tempfile.TemporaryDirectory(prefix="chaos_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_ledger_file(chaos_temp_dir: Path) -> Path:
    """Create mock ledger JSONL file."""
    from uuid import uuid4

    ledger_file = chaos_temp_dir / "ledger.jsonl"
    id1 = str(uuid4())
    ledger_file.write_text(
        f'{{"entry_type":"intent","intent_id":"{id1}","timestamp":"2024-01-01T10:00:00Z"}}\n'
        '{"entry_type":"ack","deal_id":"DEAL123","timestamp":"2024-01-01T10:00:05Z"}\n'
    )
    return ledger_file


@pytest.fixture
def mock_snapshot_file(chaos_temp_dir: Path) -> Path:
    """Create mock position snapshot parquet file."""
    import pandas as pd

    snapshot_file = chaos_temp_dir / "snapshots.parquet"

    df = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T10:00:00Z"],
            "symbol": ["EURUSD"],
            "size": [1.0],
            "entry_price": [1.0850],
        }
    )
    df.to_parquet(snapshot_file, index=False)

    return snapshot_file
