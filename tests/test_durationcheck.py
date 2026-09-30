"""Tests for utils.durationcheck - rejecting wrong-length audio."""
import pytest

from utils.durationcheck import duration_bounds, within_tolerance

THREE_MIN_MS = 180_000


class TestWithinTolerance:

    @pytest.mark.unit
    def test_thirty_second_preview_of_a_full_track_is_rejected(self):
        assert not within_tolerance(30, THREE_MIN_MS)

    @pytest.mark.unit
    def test_multi_hour_upload_is_rejected(self):
        assert not within_tolerance(277 * 60, 5 * 60 * 1000)

    @pytest.mark.unit
    def test_close_match_is_accepted(self):
        assert within_tolerance(184, THREE_MIN_MS)

    @pytest.mark.unit
    def test_short_track_uses_absolute_floor(self):
        # 40 s track: +-10 s floor applies, 10 % would only be 4 s.
        assert within_tolerance(48, 40_000)
        assert not within_tolerance(60, 40_000)

    @pytest.mark.unit
    def test_lenient_mode_only_flags_gross_mismatches(self):
        assert within_tolerance(220, THREE_MIN_MS, lenient=True)
        assert not within_tolerance(220, THREE_MIN_MS)
        assert not within_tolerance(30, THREE_MIN_MS, lenient=True)

    @pytest.mark.unit
    def test_unknown_expected_duration_cannot_be_judged(self):
        assert within_tolerance(30, None)
        assert within_tolerance(30, 0)

    @pytest.mark.unit
    def test_unreadable_file_is_rejected(self):
        assert not within_tolerance(None, THREE_MIN_MS)


class TestDurationBounds:

    @pytest.mark.unit
    def test_bounds_never_negative(self):
        low, high = duration_bounds(5_000)
        assert low == 0.0 and high == 15.0

    @pytest.mark.unit
    def test_unknown_duration_has_no_bounds(self):
        assert duration_bounds(None) is None
