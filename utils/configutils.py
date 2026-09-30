import configparser
import os
from pathlib import Path
import tempfile

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = str(_PROJECT_ROOT / 'config.ini')
TOKEN_CACHE_FILE = str(_PROJECT_ROOT / '.spotipy_cache')
DEFAULT_DOWNLOAD_PATH = '~/Music/downloads'
DEFAULT_COOKIES_FILE = ''
SUPPORTED_AUDIO_FORMATS = ('mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav')
DEFAULT_AUDIO_FORMAT = 'mp3'
DEFAULT_REDIRECT_URI = 'http://127.0.0.1:8888/callback'


def _write_config(config):
    """Replace the config only after its complete UTF-8 contents are written."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=os.path.dirname(os.path.abspath(CONFIG_FILE)),
                                         delete=False) as file:
            temp_path = file.name
            config.write(file)
        os.replace(temp_path, CONFIG_FILE)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def _ensure_config_exists():
    """Create a config with settings and OAuth credentials if absent."""
    if not os.path.exists(CONFIG_FILE):
        config = configparser.ConfigParser(interpolation=None)
        config['Settings'] = {
            'download_path': DEFAULT_DOWNLOAD_PATH,
            'cookies_file': DEFAULT_COOKIES_FILE,
            'audio_format': DEFAULT_AUDIO_FORMAT,
        }
        config['Spotify'] = {
            'client_id': '',
            'client_secret': '',
            'redirect_uri': DEFAULT_REDIRECT_URI,
        }
        _write_config(config)


def _read_config():
    _ensure_config_exists()
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_FILE, encoding='utf-8')
    return config


def get_download_path() -> str:
    """Return the configured path with a leading home-directory tilde expanded."""
    return os.path.expanduser(_read_config().get(
        'Settings', 'download_path', fallback=DEFAULT_DOWNLOAD_PATH))


def get_cookies_file() -> str:
    return _read_config().get('Settings', 'cookies_file', fallback=DEFAULT_COOKIES_FILE)


def get_audio_format() -> str:
    return _read_config().get('Settings', 'audio_format', fallback=DEFAULT_AUDIO_FORMAT)


def get_spotify_client_id() -> str:
    return _read_config().get('Spotify', 'client_id', fallback='')


def get_spotify_client_secret() -> str:
    return _read_config().get('Spotify', 'client_secret', fallback='')


def get_spotify_redirect_uri() -> str:
    return _read_config().get('Spotify', 'redirect_uri', fallback=DEFAULT_REDIRECT_URI)


def get_token_cache_path() -> str:
    return TOKEN_CACHE_FILE


def set_value(section: str, key: str, value: str):
    """Persist a value atomically; an empty string clears the value."""
    config = _read_config()
    if section not in config:
        config[section] = {}
    config[section][key] = value
    _write_config(config)
