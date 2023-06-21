import spotipy
from spotipy import SpotifyOAuth

from model.playlist import Playlist
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

    def get_all_saved_songs(self, limit_step=50):
        tracks = []
        songs = []
        for offset in range(0, 10000000, limit_step):
            response = self.auth.current_user_saved_tracks(
                limit=limit_step,
                offset=offset,
            )

            if len(response['items']) == 0:
                break
            tracks.extend(response['items'])
            print(offset)

        for idx, item in enumerate(tracks):
            track = item['track']
            song = Song(name=track['name'], artist=track['artists'][0]['name'], url=track['external_urls']['spotify'])
            songs.append(song)
        return songs

    def get_playlists(self, limit_step=50):
        playlists = []
        results = []

        for offset in range(0, 10000000, limit_step):
            response = self.auth.current_user_playlists(
                limit=limit_step,
                offset=offset,
            )

            if len(response['items']) == 0:
                break
            playlists.extend(response['items'])
            print(offset)

        for idx, item in enumerate(playlists):
            download_url = item['external_urls']['spotify']
            playlist = Playlist(name=item['name'], songs=[], url=download_url)
            results.append(playlist)

        return results
