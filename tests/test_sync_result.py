"""
Tests for sync_result.py - Sync operation result tracking.
"""
import pytest

from model.sync_result import DownloadError, SyncResult


class TestDownloadError:
    """Tests for the DownloadError dataclass."""

    @pytest.mark.unit
    def test_download_error_creation(self):
        """Test creating a DownloadError with all fields."""
        error = DownloadError(
            item_name="Test Song",
            item_url="https://example.com/song",
            error_message="Download failed"
        )

        assert error.item_name == "Test Song"
        assert error.item_url == "https://example.com/song"
        assert error.error_message == "Download failed"

    @pytest.mark.unit
    def test_download_error_with_none_url(self):
        """Test creating a DownloadError with optional URL as None."""
        error = DownloadError(
            item_name="Test Song",
            item_url=None,
            error_message="No URL available"
        )

        assert error.item_name == "Test Song"
        assert error.item_url is None
        assert error.error_message == "No URL available"


class TestSyncResult:
    """Tests for the SyncResult dataclass."""

    @pytest.mark.unit
    def test_sync_result_initialization_with_defaults(self):
        """Test creating a SyncResult with default values."""
        result = SyncResult()

        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.skipped_count == 0
        assert result.errors == []

    @pytest.mark.unit
    def test_sync_result_initialization_with_values(self):
        """Test creating a SyncResult with specific values."""
        errors = [DownloadError("Song1", None, "Error 1")]
        result = SyncResult(
            success_count=5,
            failure_count=2,
            skipped_count=1,
            errors=errors
        )

        assert result.success_count == 5
        assert result.failure_count == 2
        assert result.skipped_count == 1
        assert len(result.errors) == 1

    @pytest.mark.unit
    def test_add_success_increments_counter(self):
        """Test that add_success increments the success counter."""
        result = SyncResult()
        result.add_success()
        result.add_success()

        assert result.success_count == 2

    @pytest.mark.unit
    def test_add_skipped_increments_counter(self):
        """Test that add_skipped increments the skipped counter."""
        result = SyncResult()
        result.add_skipped()
        result.add_skipped()
        result.add_skipped()

        assert result.skipped_count == 3

    @pytest.mark.unit
    def test_add_failure_increments_counter_and_adds_error(self):
        """Test that add_failure increments counter and records error."""
        result = SyncResult()
        result.add_failure("Song1", "http://example.com/1", "Network error")
        result.add_failure("Song2", None, "File not found")

        assert result.failure_count == 2
        assert len(result.errors) == 2
        assert result.errors[0].item_name == "Song1"
        assert result.errors[1].item_name == "Song2"

    @pytest.mark.unit
    def test_total_property(self):
        """Test the total property calculation."""
        result = SyncResult()
        result.add_success()
        result.add_success()
        result.add_failure("Song", None, "Error")
        result.add_skipped()

        assert result.total == 4  # 2 + 1 + 1

    @pytest.mark.unit
    def test_total_property_with_zero_values(self):
        """Test total property when all counters are zero."""
        result = SyncResult()
        assert result.total == 0

    @pytest.mark.unit
    def test_has_failures_property(self):
        """Test the has_failures property."""
        result = SyncResult()

        assert result.has_failures is False

        result.add_failure("Song", None, "Error")

        assert result.has_failures is True

    @pytest.mark.unit
    def test_success_rate_with_all_successes(self):
        """Test success rate calculation with 100% success."""
        result = SyncResult()
        result.add_success()
        result.add_success()
        result.add_success()

        assert result.success_rate == 100.0

    @pytest.mark.unit
    def test_success_rate_with_mixed_results(self):
        """Test success rate calculation with mixed results."""
        result = SyncResult()
        result.add_success()
        result.add_success()
        result.add_failure("Song", None, "Error")
        result.add_success()

        # 3 success out of 4 total = 75%
        assert result.success_rate == 75.0

    @pytest.mark.unit
    def test_success_rate_with_zero_total(self):
        """Test success rate when no items were processed."""
        result = SyncResult()
        assert result.success_rate == 0.0

    @pytest.mark.unit
    def test_success_rate_with_failures_only(self):
        """Test success rate when all items failed."""
        result = SyncResult()
        result.add_failure("Song1", None, "Error1")
        result.add_failure("Song2", None, "Error2")

        assert result.success_rate == 0.0

    @pytest.mark.unit
    def test_get_summary_all_successes(self):
        """Test summary generation when all items succeeded."""
        result = SyncResult()
        result.add_success()
        result.add_success()
        result.add_success()

        summary = result.get_summary()
        assert "3 succeeded" in summary
        assert "failed" not in summary
        assert "skipped" not in summary

    @pytest.mark.unit
    def test_get_summary_with_failures(self):
        """Test summary generation when there are failures."""
        result = SyncResult()
        result.add_success()
        result.add_failure("Song1", "url1", "Error message 1")
        result.add_failure("Song2", "url2", "Error message 2")

        summary = result.get_summary()
        assert "1 succeeded" in summary
        assert "2 failed" in summary
        assert "Errors:" in summary
        assert "Song1: Error message 1" in summary
        assert "Song2: Error message 2" in summary

    @pytest.mark.unit
    def test_get_summary_with_skipped(self):
        """Test summary generation when items were skipped."""
        result = SyncResult()
        result.add_success()
        result.add_skipped()
        result.add_skipped()

        summary = result.get_summary()
        assert "1 succeeded" in summary
        assert "2 skipped" in summary

    @pytest.mark.unit
    def test_get_summary_with_mixed_results(self):
        """Test summary with successes, failures, and skips."""
        result = SyncResult()
        for _ in range(5):
            result.add_success()
        for _ in range(2):
            result.add_failure("Song", None, "Error")
        result.add_skipped()

        summary = result.get_summary()
        assert "5 succeeded" in summary
        assert "2 failed" in summary
        assert "1 skipped" in summary

    @pytest.mark.unit
    def test_get_summary_limits_errors_to_ten(self):
        """Test that summary shows only first 10 errors."""
        result = SyncResult()
        for i in range(15):
            result.add_failure(f"Song{i}", None, f"Error {i}")

        summary = result.get_summary()

        # Should show first 10 errors
        assert "Song0: Error 0" in summary
        assert "Song9: Error 9" in summary

        # Should NOT show errors 10-14
        assert "Song10: Error 10" not in summary

        # Should show "and X more errors"
        assert "and 5 more errors" in summary

    @pytest.mark.unit
    def test_get_summary_exactly_ten_errors(self):
        """Test summary with exactly 10 errors (no 'more' message)."""
        result = SyncResult()
        for i in range(10):
            result.add_failure(f"Song{i}", None, f"Error {i}")

        summary = result.get_summary()

        # All 10 errors should be shown
        assert "Song0: Error 0" in summary
        assert "Song9: Error 9" in summary

        # Should NOT show "and X more errors"
        assert "more errors" not in summary

    @pytest.mark.unit
    def test_str_returns_summary(self):
        """Test that __str__ returns the summary."""
        result = SyncResult()
        result.add_success()

        assert str(result) == result.get_summary()
