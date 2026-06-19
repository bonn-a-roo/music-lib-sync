"""
Tests for fileutils.py - File system operations and filename sanitization.
"""
import os
import tempfile
import shutil
from pathlib import Path

import pytest

from utils.fileutils import create_directory, sanitize_filename


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    @pytest.mark.unit
    def test_removes_windows_forbidden_characters(self):
        """Test that Windows forbidden characters are removed."""
        # < > : " / \ | ? *
        # Note: First forbidden chars are removed, then non-word chars become underscores
        # 'file<>name' -> 'filename' (removed) -> 'filename' (no non-word chars)
        assert sanitize_filename('file<>name') == 'filename'
        assert sanitize_filename('file:name') == 'filename'  # ':' removed, then 'filename'
        assert sanitize_filename('file"name') == 'filename'  # '"' removed
        assert sanitize_filename('file/name') == 'filename'  # '/' removed
        assert sanitize_filename('file\\name') == 'filename'  # '\' removed
        assert sanitize_filename('file|name') == 'filename'  # '|' removed
        assert sanitize_filename('file?name') == 'filename'  # '?' removed
        assert sanitize_filename('file*name') == 'filename'  # '*' removed

    @pytest.mark.unit
    def test_replaces_non_word_characters_with_underscore(self):
        """Test that non-word characters are replaced with underscores."""
        assert sanitize_filename('file name') == 'file_name'
        assert sanitize_filename('file@name') == 'file_name'
        assert sanitize_filename('file#name') == 'file_name'
        assert sanitize_filename('file$name') == 'file_name'
        assert sanitize_filename('file%name') == 'file_name'
        assert sanitize_filename('file&name') == 'file_name'

    @pytest.mark.unit
    def test_multiple_special_characters_become_single_underscore(self):
        """Test that consecutive special characters become one underscore."""
        assert sanitize_filename('file!!!name') == 'file_name'
        assert sanitize_filename('file   name') == 'file_name'
        assert sanitize_filename('file@#$name') == 'file_name'

    @pytest.mark.unit
    def test_preserves_alphanumeric_characters(self):
        """Test that alphanumeric characters are preserved."""
        assert sanitize_filename('filename123') == 'filename123'
        assert sanitize_filename('FileName123') == 'FileName123'

    @pytest.mark.unit
    def test_preserves_underscores(self):
        """Test that underscores are preserved."""
        assert sanitize_filename('file_name') == 'file_name'
        assert sanitize_filename('file_name_test') == 'file_name_test'

    @pytest.mark.unit
    def test_empty_string_returns_empty_string(self):
        """Test that empty string returns empty string."""
        assert sanitize_filename('') == ''

    @pytest.mark.unit
    def test_real_world_song_titles(self):
        """Test sanitization of realistic song titles."""
        # 'Song: Title/Name' -> 'Song TitleName' (forbidden removed) -> 'Song_TitleName' (spaces -> _)
        assert sanitize_filename('Song: Title/Name') == 'Song_TitleName'
        # 'Artist "Feat" Other - Song' -> 'Artist Feat Other - Song' -> 'Artist_Feat_Other_Song' (hyphen is non-word)
        assert sanitize_filename('Artist "Feat" Other - Song') == 'Artist_Feat_Other_Song'
        # 'Song? (Remix)' -> 'Song (Remix)' -> 'Song_Remix_' (space+paren -> single _)
        assert sanitize_filename('Song? (Remix)') == 'Song_Remix_'


class TestCreateDirectory:
    """Tests for directory creation."""

    @pytest.mark.unit
    def test_creates_new_directory(self, tmp_path, capsys):
        """Test that a new directory is created."""
        new_dir = tmp_path / "new_folder"
        create_directory(str(new_dir))

        assert new_dir.exists()
        assert new_dir.is_dir()

        captured = capsys.readouterr()
        assert "created successfully" in captured.out

    @pytest.mark.unit
    def test_handles_existing_directory(self, tmp_path, capsys):
        """Test that existing directory is handled gracefully."""
        existing_dir = tmp_path / "existing_folder"
        existing_dir.mkdir()

        create_directory(str(existing_dir))

        assert existing_dir.exists()
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    @pytest.mark.unit
    def test_creates_nested_directories(self, tmp_path, capsys):
        """Test that nested directories are created."""
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        create_directory(str(nested_dir))

        assert nested_dir.exists()
        assert nested_dir.is_dir()

        captured = capsys.readouterr()
        assert "created successfully" in captured.out
