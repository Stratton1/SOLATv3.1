"""
Tier 1: Ledger corruption recovery.

Tests that system handles corrupted ledger entries gracefully,
skipping bad lines with warnings rather than failing completely.
"""

import pytest
from pathlib import Path
from uuid import uuid4


@pytest.mark.chaos
@pytest.mark.tier1
class TestLedgerCorruptionScenarios:
    """Tests for ledger corruption and recovery."""

    def test_invalid_jsonl_entry__ledger_repair_or_reject(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Ledger contains malformed JSON line (partial write scenario)
        EXPECTED: Corrupted line skipped with warning OR read fails gracefully
        FAILURE MODE: Pydantic validation raises, entire ledger unreadable
        """
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.execution.models import ExecutionConfig, ExecutionMode

        # Setup: Create ledger
        config = ExecutionConfig(mode=ExecutionMode.DEMO)
        ledger = ExecutionLedger(chaos_temp_dir, config, run_id="test_corruption_001")

        # Get the ledger file path
        ledger_file = ledger.run_dir / "ledger.jsonl"

        # Create valid UUIDs for test data
        id1 = str(uuid4())
        id2 = str(uuid4())

        # Overwrite with corrupted content
        ledger_file.write_text(
            f'{{"entry_type":"intent","intent_id":"{id1}","timestamp":"2024-01-01T10:00:00Z"}}\n'
            '{"entry_type":"ack","deal_id":"DEAL123","timestamp":"2024-01-01T10:00:05Z"}\n'
            f'{{"entry_type":"intent","intent_id":"{id2}","timestamp":"2024-01-01T10:00:10Z","corrupted\n'  # Invalid JSON
            '{"entry_type":"ack","deal_id":"DEAL456","timestamp":"2024-01-01T10:00:15Z"}\n'
        )

        # INJECT CHAOS: Attempt to read corrupted ledger
        try:
            entries = ledger.get_entries()

            # VERIFICATION: Should skip corrupted line and continue
            # Valid entries: lines 1, 2, and 4 (line 3 is corrupted)
            # Acceptable outcomes:
            # 1. Returns 3 valid entries (skips corrupted line)
            # 2. Returns 2 entries (stops at corruption)
            # 3. Raises exception with clear error message

            if entries:
                # If entries returned, should have valid data
                assert len(entries) >= 2, "Should return at least 2 valid entries"

                # Check first two entries are valid (attribute access on LedgerEntry)
                assert str(entries[0].intent_id) == id1
                assert entries[1].deal_id == "DEAL123"

                # If 3rd entry exists, should be the last valid line
                if len(entries) >= 3:
                    assert entries[2].deal_id == "DEAL456"

        except Exception as e:
            # VERIFICATION: If exception raised, should have clear error message
            error_msg = str(e).lower()
            assert any(
                keyword in error_msg
                for keyword in ["json", "corrupt", "invalid", "parse", "decode", "validation"]
            ), f"Error message should indicate JSON corruption: {e}"

    def test_truncated_ledger_file__partial_recovery(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Ledger file truncated mid-line (crash during write)
        EXPECTED: Valid lines read, truncated line skipped or error reported
        FAILURE MODE: Entire ledger unreadable, audit trail lost
        """
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.execution.models import ExecutionConfig, ExecutionMode

        # Setup: Create ledger
        config = ExecutionConfig(mode=ExecutionMode.DEMO)
        ledger = ExecutionLedger(chaos_temp_dir, config, run_id="test_truncated_001")

        # Create valid UUIDs for test data
        id1 = str(uuid4())
        id2 = str(uuid4())

        # Get ledger file path and overwrite with truncated content
        ledger_file = ledger.run_dir / "ledger.jsonl"
        # Overwrite with truncated content
        ledger_file.write_text(
            f'{{"entry_type":"intent","intent_id":"{id1}","timestamp":"2024-01-01T10:00:00Z"}}\n'
            '{"entry_type":"ack","deal_id":"DEAL123","timestamp":"2024-01-01T10:00:05Z"}\n'
            f'{{"entry_type":"intent","intent_id":"{id2}"'  # Truncated (no closing brace, no newline)
        )

        # INJECT CHAOS: Attempt to read truncated ledger
        try:
            entries = ledger.get_entries()

            # VERIFICATION: Should recover first 2 valid entries
            assert len(entries) >= 2, "Should recover at least 2 valid entries"
            assert str(entries[0].intent_id) == id1
            assert entries[1].deal_id == "DEAL123"

        except Exception as e:
            # Acceptable: Raises exception but indicates which lines are valid
            error_msg = str(e).lower()
            assert any(
                keyword in error_msg
                for keyword in ["json", "parse", "corrupt", "validation", "invalid", "decode"]
            ), f"Error message should indicate corruption: {e}"

    def test_empty_lines_in_ledger__skipped_gracefully(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Ledger contains empty lines or whitespace-only lines
        EXPECTED: Empty lines skipped, valid entries parsed
        FAILURE MODE: JSON parsing fails on empty lines
        """
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.execution.models import ExecutionConfig, ExecutionMode
        from uuid import UUID

        # Setup: Create ledger
        config = ExecutionConfig(mode=ExecutionMode.DEMO)
        ledger = ExecutionLedger(chaos_temp_dir, config, run_id="test_empty_lines_001")

        # Create valid UUIDs for test data
        id1 = str(uuid4())
        id2 = str(uuid4())

        # Get ledger file path and overwrite with content containing empty lines
        ledger_file = ledger.run_dir / "ledger.jsonl"
        # Overwrite with content containing empty lines
        ledger_file.write_text(
            f'{{"entry_type":"intent","intent_id":"{id1}","timestamp":"2024-01-01T10:00:00Z"}}\n'
            "\n"  # Empty line
            '{"entry_type":"ack","deal_id":"DEAL123","timestamp":"2024-01-01T10:00:05Z"}\n'
            "   \n"  # Whitespace-only line
            f'{{"entry_type":"intent","intent_id":"{id2}","timestamp":"2024-01-01T10:00:10Z"}}\n'
        )

        # Read ledger
        entries = ledger.get_entries()

        # VERIFICATION: Should skip empty lines and return 3 valid entries
        assert len(entries) == 3
        assert entries[0].intent_id == UUID(id1)
        assert entries[1].deal_id == "DEAL123"
        assert entries[2].intent_id == UUID(id2)

    def test_ledger_with_future_schema__backward_compat(
        self, chaos_temp_dir: Path
    ) -> None:
        """
        SCENARIO: Ledger contains entries with additional fields (future schema)
        EXPECTED: Extra fields ignored, known fields parsed
        FAILURE MODE: Validation fails on unknown fields
        """
        from solat_engine.execution.ledger import ExecutionLedger
        from solat_engine.execution.models import ExecutionConfig, ExecutionMode

        # Setup: Create ledger
        config = ExecutionConfig(mode=ExecutionMode.DEMO)
        ledger = ExecutionLedger(chaos_temp_dir, config, run_id="test_future_schema_001")

        # Create valid UUID for test data
        id1 = str(uuid4())

        # Get ledger file path and overwrite with future schema entries
        ledger_file = ledger.run_dir / "ledger.jsonl"
        # Overwrite with future schema entries (extra fields)
        ledger_file.write_text(
            f'{{"entry_type":"intent","intent_id":"{id1}","timestamp":"2024-01-01T10:00:00Z"}}\n'
            '{"entry_type":"ack","deal_id":"DEAL123","timestamp":"2024-01-01T10:00:05Z",'
            '"new_field_v2":"future_value","another_field":123}\n'  # Extra fields
        )

        # Read ledger
        try:
            entries = ledger.get_entries()

            # VERIFICATION: Should parse entries, ignoring unknown fields
            assert len(entries) >= 2
            assert str(entries[0].intent_id) == id1
            assert entries[1].deal_id == "DEAL123"

        except Exception as e:
            # If validation is strict, this is acceptable
            # But document that forward compatibility is not supported
            error_msg = str(e).lower()
            assert "field" in error_msg or "valid" in error_msg
            pytest.xfail("Ledger validation is strict, no forward compatibility")
