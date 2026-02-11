"""
Tests for walk-forward window generation and fold logic.

_generate_windows is a pure static method (date math only, no IO).
"""

import pytest
from datetime import UTC, datetime, timedelta

from solat_engine.optimization.models import (
    WalkForwardConfig,
    WindowType,
)
from solat_engine.optimization.walk_forward import WalkForwardEngine

_gen = WalkForwardEngine._generate_windows


class TestRollingWindowCount:
    """Test that rolling windows are generated correctly."""

    def test_basic_window_count(self):
        """With 360 days, IS=180, OOS=45, step=45, expect windows to fit."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 1, tzinfo=UTC),  # 365 days
            window_type=WindowType.ROLLING,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        # First window: IS 0-180, OOS 180-225 (day 225)
        # Step = 45 -> second window: IS 45-225, OOS 225-270 (day 270)
        # Third: IS 90-270, OOS 270-315 (day 315)
        # Fourth: IS 135-315, OOS 315-360 (day 360) <= 365 -> fits
        # Fifth: IS 180-360, OOS 360-405 > 365 -> doesn't fit
        assert len(windows) == 4

    def test_no_windows_short_range(self):
        """Date range shorter than IS+OOS -> no windows."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 6, 1, tzinfo=UTC),  # ~150 days
            window_type=WindowType.ROLLING,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        assert len(windows) == 0

    def test_single_window(self):
        """Exactly enough for one window."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2023, 8, 15, tzinfo=UTC),  # 226 days
            window_type=WindowType.ROLLING,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        assert len(windows) == 1


class TestOOSBounds:
    """Test that OOS windows don't exceed end_date."""

    def test_oos_end_within_bounds(self):
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            window_type=WindowType.ROLLING,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        for (is_start, is_end, oos_start, oos_end) in windows:
            assert oos_end <= config.end_date, (
                f"OOS end {oos_end} exceeds end_date {config.end_date}"
            )

    def test_oos_start_equals_is_end(self):
        """OOS always starts immediately after IS ends."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            window_type=WindowType.ROLLING,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        for (is_start, is_end, oos_start, oos_end) in windows:
            assert oos_start == is_end


class TestAnchoredWindows:
    """Test anchored window generation."""

    def test_anchored_all_start_from_anchor(self):
        """In anchored mode, all IS windows start from the anchor date."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            window_type=WindowType.ANCHORED,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        assert len(windows) > 0

        anchor = config.start_date
        for (is_start, is_end, oos_start, oos_end) in windows:
            assert is_start == anchor, (
                f"Anchored window IS start {is_start} != anchor {anchor}"
            )

    def test_anchored_oos_within_bounds(self):
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            window_type=WindowType.ANCHORED,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        for (is_start, is_end, oos_start, oos_end) in windows:
            assert oos_end <= config.end_date

    def test_anchored_is_window_grows(self):
        """In anchored mode, IS window grows (more data) each iteration."""
        config = WalkForwardConfig(
            symbols=["EURUSD"],
            bots=["TKCross"],
            start_date=datetime(2023, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            window_type=WindowType.ANCHORED,
            in_sample_days=180,
            out_of_sample_days=45,
            step_days=45,
        )
        windows = _gen(config)
        assert len(windows) >= 2
        for i in range(1, len(windows)):
            prev_is_end = windows[i - 1][1]
            curr_is_end = windows[i][1]
            assert curr_is_end > prev_is_end, (
                f"Window {i} IS end {curr_is_end} did not advance from {prev_is_end}"
            )


class TestIterationSafety:
    """Test that the iteration cap prevents infinite loops."""

    def test_zero_step_raises(self):
        """step_days=0 should be rejected by Pydantic validation (ge=1)."""
        with pytest.raises(Exception):
            WalkForwardConfig(
                symbols=["EURUSD"],
                bots=["TKCross"],
                start_date=datetime(2023, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 1, 1, tzinfo=UTC),
                window_type=WindowType.ROLLING,
                in_sample_days=180,
                out_of_sample_days=45,
                step_days=0,
            )
