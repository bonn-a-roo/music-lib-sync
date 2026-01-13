import spotipy
from spotipy import SpotifyOAuth

from model.library import SpotifyLibrary
from utils import configutils


class User:

    def __init__(self, scope='user-library-read'):
        self.auth = spotipy.Spotify(
            requests_session=True,
            auth_manager=SpotifyOAuth(
                client_id=configutils.get_spotify_client_id(),
                client_secret=configutils.get_spotify_client_secret(),
                redirect_uri=configutils.get_spotify_redirect_uri(),
                scope=scope
            )
        )
        self.library = SpotifyLibrary(self.auth)

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