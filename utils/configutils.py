import configparser
import os
from pathlib import Path

CONFIG_FILE = 'config.ini'
DEFAULT_DOWNLOAD_PATH = str(Path.home() / 'Music' / 'downloads')
DEFAULT_COOKIES_FILE = ''
DEFAULT_AUDIO_FORMAT = 'mp3'


def ask_download_path():
    while True:
        download_path = input("Enter the download path: ")
        if download_path.strip():
            return download_path
        else:
            print("Invalid input. Please provide a valid download path.")


def _ensure_config_exists():
    """Create config file with defaults if it doesn't exist."""
    if not os.path.exists(CONFIG_FILE):
        config = configparser.ConfigParser()
        config['Settings'] = {
            'download_path': DEFAULT_DOWNLOAD_PATH,
            'cookies_file': DEFAULT_COOKIES_FILE,
        }
        with open(CONFIG_FILE, 'w') as f:
            config.write(f)


def get_download_path() -> str:
    """Get download path from config, with fallback to default."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Settings', 'download_path', fallback=DEFAULT_DOWNLOAD_PATH)


def get_cookies_file() -> str:
    """Get cookies file path from config, with fallback to empty string."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Settings', 'cookies_file', fallback=DEFAULT_COOKIES_FILE)


def get_audio_format() -> str:
    """Get preferred audio format from config."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Settings', 'audio_format', fallback=DEFAULT_AUDIO_FORMAT)


def get_spotify_client_id() -> str:
    """Get Spotify client ID from config."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Spotify', 'client_id', fallback='')


def get_spotify_client_secret() -> str:
    """Get Spotify client secret from config."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Spotify', 'client_secret', fallback='')


def get_spotify_redirect_uri() -> str:
    """Get Spotify redirect URI from config."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config.get('Spotify', 'redirect_uri', fallback='http://localhost')


def set_value(section: str, key: str, value: str):
    """Set a config value and write to disk."""
    _ensure_config_exists()
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if section not in config:
        config[section] = {}

    config[section][key] = value

    with open(CONFIG_FILE, 'w') as f:
        config.write(f)
