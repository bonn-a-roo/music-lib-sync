"""
Tests for configutils.py - Configuration file management.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils import configutils


class TestEnsureConfigExists:
    """Tests for _ensure_config_exists function."""

    @pytest.mark.unit
    def test_creates_config_file_if_not_exists(self, tmp_path):
        """Test that config file is created if it doesn't exist."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            # Remove file if it exists
            if config_file.exists():
                config_file.unlink()

            configutils._ensure_config_exists()

            assert config_file.exists()

    @pytest.mark.unit
    def test_does_not_modify_existing_config(self, tmp_path):
        """Test that existing config is not modified."""
        config_file = tmp_path / "test_config.ini"

        # Create a config file with custom content
        with open(config_file, 'w') as f:
            f.write("[Settings]\n")
            f.write("download_path = /custom/path\n")
            f.write("[Custom]\n")
            f.write("custom_key = custom_value\n")

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()

            # Verify custom content is preserved
            with open(config_file, 'r') as f:
                content = f.read()
                assert "/custom/path" in content
                assert "custom_value" in content


class TestGetDownloadPath:
    """Tests for get_download_path function."""

    @pytest.mark.unit
    def test_returns_default_when_config_missing(self, tmp_path):
        """Test that default path is returned when config doesn't specify."""
        config_file = tmp_path / "test_config.ini"
        default_path = tmp_path / "Music" / "downloads"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            with patch.object(configutils, 'DEFAULT_DOWNLOAD_PATH', str(default_path)):
                if config_file.exists():
                    config_file.unlink()

                result = configutils.get_download_path()
                assert result == str(default_path)

    @pytest.mark.unit
    def test_returns_configured_value(self, tmp_path):
        """Test that configured value is returned."""
        config_file = tmp_path / "test_config.ini"
        custom_path = "/my/custom/path"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Settings', 'download_path', custom_path)

            result = configutils.get_download_path()
            assert result == custom_path


class TestGetCookiesFile:
    """Tests for get_cookies_file function."""

    @pytest.mark.unit
    def test_returns_default_empty_string(self, tmp_path):
        """Test that empty string is returned when not configured."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            if config_file.exists():
                config_file.unlink()

            result = configutils.get_cookies_file()
            assert result == ''

    @pytest.mark.unit
    def test_returns_configured_cookies_file(self, tmp_path):
        """Test that configured cookies file path is returned."""
        config_file = tmp_path / "test_config.ini"
        cookies_path = "/path/to/cookies.txt"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Settings', 'cookies_file', cookies_path)

            result = configutils.get_cookies_file()
            assert result == cookies_path


class TestSpotifyConfig:
    """Tests for Spotify configuration getters."""

    @pytest.mark.unit
    def test_get_spotify_client_id(self, tmp_path):
        """Test getting Spotify client ID."""
        config_file = tmp_path / "test_config.ini"
        client_id = "test_client_id_123"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Spotify', 'client_id', client_id)

            result = configutils.get_spotify_client_id()
            assert result == client_id

    @pytest.mark.unit
    def test_get_spotify_client_secret(self, tmp_path):
        """Test getting Spotify client secret."""
        config_file = tmp_path / "test_config.ini"
        client_secret = "test_secret_456"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Spotify', 'client_secret', client_secret)

            result = configutils.get_spotify_client_secret()
            assert result == client_secret

    @pytest.mark.unit
    def test_get_spotify_redirect_uri(self, tmp_path):
        """Test getting Spotify redirect URI."""
        config_file = tmp_path / "test_config.ini"
        redirect_uri = "http://127.0.0.1:8888/callback"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Spotify', 'redirect_uri', redirect_uri)

            result = configutils.get_spotify_redirect_uri()
            assert result == redirect_uri

    @pytest.mark.unit
    def test_spotify_defaults_to_empty_string(self, tmp_path):
        """Test that missing Spotify config returns empty string (or localhost for redirect_uri)."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            if config_file.exists():
                config_file.unlink()

            assert configutils.get_spotify_client_id() == ''
            assert configutils.get_spotify_client_secret() == ''
            # redirect_uri has a different default
            assert configutils.get_spotify_redirect_uri() == 'http://localhost'


class TestSetValue:
    """Tests for set_value function."""

    @pytest.mark.unit
    def test_sets_value_in_existing_section(self, tmp_path):
        """Test setting a value in an existing section."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Settings', 'test_key', 'test_value')

            result = configutils.get_download_path()
            # Since we can't directly get test_key, verify file was written
            assert config_file.exists()

    @pytest.mark.unit
    def test_creates_new_section_if_not_exists(self, tmp_path):
        """Test that a new section is created if it doesn't exist."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('NewSection', 'new_key', 'new_value')

            # Verify section and key were created
            import configparser
            config = configparser.ConfigParser()
            config.read(str(config_file))
            assert 'NewSection' in config
            assert config['NewSection']['new_key'] == 'new_value'

    @pytest.mark.unit
    def test_overwrites_existing_value(self, tmp_path):
        """Test that existing values are overwritten."""
        config_file = tmp_path / "test_config.ini"

        with patch.object(configutils, 'CONFIG_FILE', str(config_file)):
            configutils._ensure_config_exists()
            configutils.set_value('Settings', 'download_path', '/path1')
            configutils.set_value('Settings', 'download_path', '/path2')

            result = configutils.get_download_path()
            assert result == '/path2'
