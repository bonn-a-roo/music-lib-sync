import abc
import os

from downloaders.spotifydl import SpotifyDownloader
from model.playlist import Playlist
from model.song import Song
from model.sync_result import SyncResult
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)


class LibrarySyncSource(abc.ABC):
    @abc.abstractmethod
    def sync_songs(self):
        pass

    def sync_playlists(self):
        pass


class SpotifyLibrary(LibrarySyncSource):
    def __init__(self, auth):
        self.auth = auth

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
            song = Song(name=track['name'], artist=track['artists'][0]['name'], url=track['external_urls']['spotify'])
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

        for idx, item in enumerate(playlists):
            download_url = item['external_urls']['spotify']
            playlist = Playlist(name=item['name'], songs=[], url=download_url)
            results.append(playlist)

        return results

    def sync_songs(self) -> SyncResult:
        cookies = configutils.get_cookies_file()
        downloader = SpotifyDownloader(cookies=cookies if cookies else None)
        download_path = configutils.get_download_path()

        my_songs = self.get_saved_tracks()
        logger.info(f"Found {len(my_songs)} saved tracks")

        my_songs_dir = os.path.join(download_path, "my_songs")
        if not os.path.exists(my_songs_dir):
            os.makedirs(my_songs_dir)

        downloaded_files = set(os.listdir(my_songs_dir))
        songs_to_download = [song.desc_filename() for song in my_songs]
        songs_to_download = set(songs_to_download) - downloaded_files
        songs_to_download = list(songs_to_download)
        # TODO: (Still gets many songs that are already downloaded: ej. with combined artists)
        my_songs_to_download = [song for song in my_songs if song.desc_filename() in songs_to_download]

        logger.info(f"Downloading {len(my_songs_to_download)} new songs (skipping {len(my_songs) - len(my_songs_to_download)} already downloaded)")

        result = downloader.download(my_songs_to_download, download_path, num_threads=16)
        result.skipped_count = len(my_songs) - len(my_songs_to_download)
        return result

    def sync_playlists(self) -> SyncResult:
        cookies = configutils.get_cookies_file()
        downloader = SpotifyDownloader(cookies=cookies if cookies else None)
        download_path = configutils.get_download_path()

        my_playlists = self.get_playlists()
        logger.info(f"Found {len(my_playlists)} playlists")

        # TODO: (Playlists songs should be checked individually before avoiding the whole playlist)
        return downloader.download(my_playlists, download_path, num_threads=1)

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
