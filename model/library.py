import abc
import os
import re

from downloaders.spotifydl import SpotifyDownloader
from model.playlist import Playlist
from model.song import Song
from model.sync_result import SyncResult
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)


def extract_track_id_from_url(spotify_url: str) -> str | None:
    """Extract track ID from Spotify URL."""
    match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
    return match.group(1) if match else None


class LibrarySyncSource(abc.ABC):
    @abc.abstractmethod
    def sync_songs(self):
        pass

    def sync_playlists(self):
        pass


class SpotifyLibrary(LibrarySyncSource):
    def __init__(self, auth):
        self.auth = auth

    def _extract_track_id(self, spotify_url: str) -> str | None:
        """Extract track ID from Spotify URL."""
        match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
        return match.group(1) if match else None

    def get_saved_tracks(self, limit_step=50):
        tracks = []
        songs = []
        offset = 0
        while True:
            response = self.auth.current_user_saved_tracks(
                limit=limit_step,
                offset=offset,
            )

            if len(response['items']) == 0:
                break
            tracks.extend(response['items'])
            offset += limit_step

        for idx, item in enumerate(tracks):
            track = item['track']
            track_id = track.get('id')
            song = Song(
                name=track['name'],
                artist=track['artists'][0]['name'],
                url=track['external_urls']['spotify'],
                track_id=track_id
            )
            songs.append(song)
        return songs

    def get_playlists(self, limit_step=50):
        playlists = []
        results = []
        offset = 0

        while True:
            response = self.auth.current_user_playlists(
                limit=limit_step,
                offset=offset,
            )

            if len(response['items']) == 0:
                break
            playlists.extend(response['items'])
            offset += limit_step

        for item in playlists:
            playlist_url = item['external_urls']['spotify']
            # Fetch songs for each playlist
            playlist_songs = self._get_playlist_songs(item['id'])
            playlist = Playlist(name=item['name'], songs=playlist_songs, url=playlist_url)
            results.append(playlist)

        return results

    def _get_playlist_songs(self, playlist_id: str) -> list[Song]:
        """Fetch all songs from a playlist."""
        songs = []
        offset = 0
        limit_step = 100

        while True:
            response = self.auth.playlist_items(
                playlist_id,
                limit=limit_step,
                offset=offset,
                additional_types=('track',)
            )

            if len(response['items']) == 0:
                break

            for item in response['items']:
                track = item.get('track')
                if track is None:
                    continue  # Track might be removed/unavailable
                track_id = track.get('id')
                song = Song(
                    name=track['name'],
                    artist=track['artists'][0]['name'],
                    url=track['external_urls']['spotify'],
                    track_id=track_id
                )
                songs.append(song)

            offset += limit_step

        return songs

    def _get_downloaded_track_ids(self, directory: str) -> set[str]:
        """Extract track IDs from downloaded files using spotdl's filename pattern."""
        track_ids = set()
        if not os.path.exists(directory):
            return track_ids

        # spotdl uses pattern: {artist} - {track} [{track_id}].mp3
        pattern = re.compile(r'\[([a-zA-Z0-9]+)\]\.mp3$')

        for filename in os.listdir(directory):
            match = pattern.search(filename)
            if match:
                track_ids.add(match.group(1))

        return track_ids

    def sync_songs(self) -> SyncResult:
        cookies = configutils.get_cookies_file()
        downloader = SpotifyDownloader(cookies=cookies if cookies else None)
        download_path = configutils.get_download_path()

        my_songs = self.get_saved_tracks()
        logger.info(f"Found {len(my_songs)} saved tracks")

        my_songs_dir = os.path.join(download_path, "my_songs")
        if not os.path.exists(my_songs_dir):
            os.makedirs(my_songs_dir)

        # Use track IDs for more reliable matching
        downloaded_track_ids = self._get_downloaded_track_ids(my_songs_dir)
        songs_to_download = [song for song in my_songs if song.track_id and song.track_id not in downloaded_track_ids]

        logger.info(f"Downloading {len(songs_to_download)} new songs (skipping {len(my_songs) - len(songs_to_download)} already downloaded)")

        result = downloader.download(songs_to_download, download_path, num_threads=16)
        result.skipped_count = len(my_songs) - len(songs_to_download)
        return result

    def sync_playlists(self) -> SyncResult:
        cookies = configutils.get_cookies_file()
        downloader = SpotifyDownloader(cookies=cookies if cookies else None)
        download_path = configutils.get_download_path()

        my_playlists = self.get_playlists()
        logger.info(f"Found {len(my_playlists)} playlists")

        # For each playlist, check which songs are already downloaded
        result = SyncResult()

        for playlist in my_playlists:
            playlist_dir = os.path.join(download_path, "playlists", playlist.name)
            if not os.path.exists(playlist_dir):
                os.makedirs(playlist_dir)

            downloaded_track_ids = self._get_downloaded_track_ids(playlist_dir)
            songs_to_download = [song for song in playlist.songs if song.track_id and song.track_id not in downloaded_track_ids]

            logger.info(f"Playlist '{playlist.name}': {len(songs_to_download)} new songs out of {len(playlist.songs)} total")

            if songs_to_download:
                playlist_result = downloader.download(songs_to_download, download_path, num_threads=1)
                result.success_count += playlist_result.success_count
                result.failure_count += playlist_result.failure_count
                result.errors.extend(playlist_result.errors)
            else:
                result.skipped_count += len(playlist.songs)

        return result

# class AppleMusicLibrary(LibrarySyncSource):
#    def __init__(self, developer_token):
#        self.apple_music_api = AppleMusicAPI(developer_token)

#    def get_saved_songs(self):
#        # Implementation specific to Apple Music API
#        pass

#    def get_saved_albums(self):
#        # Implementation specific to Apple Music API
#        pass

#    def sync_library_locally(self):
#        # Implementation specific to Apple Music library sync
#        pass
