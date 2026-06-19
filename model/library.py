import abc
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from downloaders.spotifydl import SpotifyDownloader

# Cap total concurrent Spotify API requests across all thread pools
_spotify_semaphore = threading.Semaphore(4)
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
            try:
                response = self.auth.current_user_saved_tracks(
                    limit=limit_step,
                    offset=offset,
                )

                if len(response['items']) == 0:
                    break
                tracks.extend(response['items'])
                offset += limit_step
            except Exception as e:
                logger.error(f"Failed to fetch saved tracks at offset {offset}: {e}")
                break

        for idx, item in enumerate(tracks):
            track = item['track']
            song = Song.from_spotify_track(track)
            if song:
                songs.append(song)
        return songs

    def get_playlists(self, limit_step=50):
        playlists = []
        results = []
        offset = 0

        logger.info("Fetching playlist list from Spotify...")
        while True:
            try:
                response = self.auth.current_user_playlists(
                    limit=limit_step,
                    offset=offset,
                )

                if len(response['items']) == 0:
                    break
                playlists.extend(response['items'])
                logger.info(f"Fetched {len(playlists)} playlists so far...")
                offset += limit_step
            except Exception as e:
                logger.error(f"Failed to fetch playlists at offset {offset}: {e}")
                break

        logger.info(f"Fetched {len(playlists)} playlists total. Now fetching songs for each...")

        def _fetch_playlist(item):
            playlist_url = item['external_urls']['spotify']
            logger.info(f"Fetching songs for playlist: {item['name']}")
            playlist_songs = self._get_playlist_songs(item['id'])
            return Playlist(name=item['name'], songs=playlist_songs, url=playlist_url)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_fetch_playlist, item): item for item in playlists}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Failed to process playlist {item.get('name', 'Unknown')}: {e}")

        return results

    def _get_playlist_songs(self, playlist_id: str) -> list[Song]:
        """Fetch all songs from a playlist, using parallel requests once total is known."""
        limit_step = 100

        # First page to get total count
        try:
            with _spotify_semaphore:
                first = self.auth.playlist_items(
                    playlist_id,
                    limit=limit_step,
                    offset=0,
                    additional_types=('track',)
                )
        except Exception as e:
            logger.error(f"Failed to fetch playlist items: {e}")
            return []

        total = first.get('total', 0)
        logger.info(f"  -> Got {len(first['items'])} tracks at offset 0 (total: {total})")

        pages: dict[int, list] = {0: first['items']}
        remaining_offsets = list(range(limit_step, total, limit_step))

        if remaining_offsets:
            def _fetch_page(offset):
                with _spotify_semaphore:
                    response = self.auth.playlist_items(
                        playlist_id,
                        limit=limit_step,
                        offset=offset,
                        additional_types=('track',)
                    )
                logger.info(f"  -> Got {len(response['items'])} tracks at offset {offset}")
                return offset, response['items']

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(_fetch_page, off): off for off in remaining_offsets}
                for future in as_completed(futures):
                    try:
                        offset, items = future.result()
                        pages[offset] = items
                    except Exception as e:
                        logger.error(f"Failed to fetch page: {e}")

        songs = []
        for offset in sorted(pages):
            for item in pages[offset]:
                track = item.get('track')
                if track is None:
                    continue
                song = Song.from_spotify_track(track)
                if song:
                    songs.append(song)

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

    def sync_songs(self, downloader=None, progress_callback=None) -> SyncResult:
        if downloader is None:
            cookies = configutils.get_cookies_file()
            downloader = SpotifyDownloader(
                cookies=cookies if cookies else None,
                client_id=configutils.get_spotify_client_id(),
                client_secret=configutils.get_spotify_client_secret(),
            )
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

        result = downloader.download(songs_to_download, my_songs_dir, num_threads=4, progress_callback=progress_callback)
        result.skipped_count = len(my_songs) - len(songs_to_download)
        if downloader.is_cancelled():
            result.cancelled = True
        return result

    def sync_playlists(self, downloader=None, progress_callback=None) -> SyncResult:
        if downloader is None:
            cookies = configutils.get_cookies_file()
            downloader = SpotifyDownloader(
                cookies=cookies if cookies else None,
                client_id=configutils.get_spotify_client_id(),
                client_secret=configutils.get_spotify_client_secret(),
            )
        download_path = configutils.get_download_path()

        my_playlists = self.get_playlists()
        logger.info(f"Found {len(my_playlists)} playlists")

        # For each playlist, check which songs are already downloaded
        result = SyncResult()

        for playlist in my_playlists:
            if downloader.is_cancelled():
                break

            playlist_dir = os.path.join(download_path, "playlists", playlist.name)
            if not os.path.exists(playlist_dir):
                os.makedirs(playlist_dir)

            downloaded_track_ids = self._get_downloaded_track_ids(playlist_dir)
            songs_to_download = [song for song in playlist.songs if song.track_id and song.track_id not in downloaded_track_ids]

            logger.info(f"Playlist '{playlist.name}': {len(songs_to_download)} new songs out of {len(playlist.songs)} total")

            if songs_to_download:
                playlist_result = downloader.download(songs_to_download, playlist_dir, num_threads=1, progress_callback=progress_callback)
                result.success_count += playlist_result.success_count
                result.failure_count += playlist_result.failure_count
                result.errors.extend(playlist_result.errors)
            else:
                result.skipped_count += len(playlist.songs)

        if downloader.is_cancelled():
            result.cancelled = True
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
