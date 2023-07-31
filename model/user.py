import spotipy
from spotipy import SpotifyOAuth

from model.library import SpotifyLibrary
from model.song import Song


def get_all_saved_songs_stub():
    # Predefined list of songs
    songs = [
        Song(name="Song 1", artist="Artist 1"),
        Song(name="Song 2", artist="Artist 2"),
        Song(name="Song 3", artist="Artist 3"),
    ]
    return songs


class User:

    def __init__(self, scope='user-library-read'):
        self.auth = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
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

    def desc(self):
        return "algo"