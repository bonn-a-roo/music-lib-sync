import spotipy
from spotipy import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

from model.library import SpotifyLibrary
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)


class User:

    def __init__(self, scope='user-library-read'):
        client_id = configutils.get_spotify_client_id()
        client_secret = configutils.get_spotify_client_secret()
        redirect_uri = configutils.get_spotify_redirect_uri()

        if not client_id or not client_secret:
            raise ValueError(
                "Spotify credentials not configured. Please edit config.ini and add your "
                "client_id and client_secret from https://developer.spotify.com/dashboard"
            )

        # Use cache handler to persist tokens, avoiding re-authentication
        cache_handler = CacheFileHandler(cache_path='.spotipy_cache')

        self.auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_handler=cache_handler,
            open_browser=True,  # Ensure browser opens for authentication
            show_dialog=True,   # Always show login dialog
        )

        logger.info("Initializing Spotify authentication (browser will open if not cached)")
        self.auth = spotipy.Spotify(auth_manager=self.auth_manager)
        self.library = SpotifyLibrary(self.auth)

        # Verify authentication worked
        try:
            user_info = self.auth.current_user()
            logger.info(f"Authenticated as: {user_info.get('display_name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def sync_music_library(self):
        return self.library.sync_library_locally()

    def get_raw_info(self):
        return self.auth.current_user()

    def get_email(self):
        return self.auth.current_user().get("email", "N/A")

    def get_name(self):
        return self.auth.current_user().get("display_name", "N/A")

    def get_id(self):
        return self.auth.current_user().get("id", "N/A")