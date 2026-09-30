import configparser
import os
from pathlib import Path

import pytest
from utils import configutils

pytestmark = pytest.mark.unit


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / 'config.ini'
    monkeypatch.setattr(configutils, 'CONFIG_FILE', str(path))
    return path


def test_project_paths_are_absolute_and_cwd_independent(tmp_path, monkeypatch):
    root = Path(configutils.__file__).resolve().parent.parent
    monkeypatch.chdir(tmp_path)
    assert Path(configutils.CONFIG_FILE) == root / 'config.ini'
    assert Path(configutils.get_token_cache_path()) == root / '.spotipy_cache'


def test_config_reads_from_other_cwd_with_percent_values(config_file, tmp_path, monkeypatch):
    other = tmp_path / 'elsewhere'
    other.mkdir()
    monkeypatch.chdir(other)
    configutils.set_value('Settings', 'download_path', '~/Music/100% 中文')
    configutils.set_value('Settings', 'cookies_file', '100% cookies.txt')
    configutils.set_value('Spotify', 'client_secret', 'secret%42')
    assert configutils.get_download_path() == os.path.expanduser('~/Music/100% 中文')
    assert configutils.get_cookies_file() == '100% cookies.txt'
    assert configutils.get_spotify_client_secret() == 'secret%42'
    assert not (other / 'config.ini').exists()


def test_default_config_has_credentials_section(config_file):
    assert configutils.get_download_path() == os.path.expanduser('~/Music/downloads')
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_file, encoding='utf-8')
    assert dict(parser['Spotify']) == {
        'client_id': '', 'client_secret': '',
        'redirect_uri': 'http://127.0.0.1:8888/callback'}


def test_empty_value_clears_and_preserves_other_settings(config_file):
    configutils.set_value('Settings', 'cookies_file', 'cookies.txt')
    configutils.set_value('Spotify', 'client_id', 'client')
    configutils.set_value('Settings', 'cookies_file', '')
    assert configutils.get_cookies_file() == ''
    assert configutils.get_spotify_client_id() == 'client'


def test_failed_atomic_replace_preserves_original(config_file, monkeypatch):
    configutils.set_value('Spotify', 'client_id', 'original')
    before = config_file.read_bytes()
    def fail_replace(*args):
        raise OSError('replace denied')
    monkeypatch.setattr(configutils.os, 'replace', fail_replace)
    with pytest.raises(OSError):
        configutils.set_value('Spotify', 'client_id', 'new')
    assert config_file.read_bytes() == before
    assert list(config_file.parent.iterdir()) == [config_file]


def test_existing_config_is_not_overwritten(config_file):
    text = '[Settings]\ncookies_file = present\n'
    config_file.write_text(text, encoding='utf-8')
    configutils._ensure_config_exists()
    assert config_file.read_text(encoding='utf-8') == text
    assert configutils.get_spotify_redirect_uri() == 'http://127.0.0.1:8888/callback'


@pytest.mark.parametrize('audio_format', ['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])
def test_audio_format_is_preserved(config_file, audio_format):
    configutils.set_value('Settings', 'audio_format', audio_format)
    assert configutils.get_audio_format() == audio_format
