import abc
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from spotipy import SpotifyException

from model.playlist import Playlist
from model.song import Song
from model.sync_result import SyncResult
from model.library_state import CollectionKey, CollectionSnapshot, LocalFileIndex
from utils import configutils, durationcheck, metadatautils, repair
from utils.fileutils import sanitize_path_component, track_id_from_filename
from utils.logutils import get_logger

logger = get_logger(__name__)
_sleep = time.sleep
_spotify_semaphore = threading.Semaphore(4)


class LibraryFetchError(Exception):
    """Spotify could not provide a complete library listing."""


class _FetchCancelled(Exception):
    pass


class LibrarySyncSource(abc.ABC):
    @abc.abstractmethod
    def sync_songs(self, downloader, progress_callback=None):
        pass

    @abc.abstractmethod
    def sync_playlists(self, downloader, progress_callback=None):
        pass


class SpotifyLibrary(LibrarySyncSource):
    def __init__(self, auth):
        self.auth = auth
        self._user_id = None
        self._saved_unavailable = 0
        self._playlist_unavailable = {}

    def _spotify_call(self, fn, *args, cancel_check=None, **kwargs):
        """Retry transport/transient API failures without making waits uninterruptible.

        Spotipy may already have exhausted urllib3 retries: that path produces
        a 429 SpotifyException without response headers. HTTP errors otherwise
        preserve the response's reason and Retry-After header.
        """
        for attempt in range(5):
            if cancel_check and cancel_check():
                raise _FetchCancelled()
            try:
                with _spotify_semaphore:
                    return fn(*args, **kwargs)
            except Exception as error:
                quota = isinstance(error, SpotifyException) and error.http_status == 429 and 'QUOTA_EXCEEDED' in str(error.reason or error.msg)
                retryable = isinstance(error, (requests.ConnectionError, requests.Timeout)) or (
                    isinstance(error, SpotifyException) and error.http_status in (429, 500, 502, 503, 504)
                )
                if not retryable or attempt == 4 or (quota and attempt >= 1):
                    message = f'Spotify application quota exceeded (QUOTA_EXCEEDED): {error}' if quota else str(error)
                    raise LibraryFetchError(message) from error
                headers = getattr(error, 'headers', {}) or {}
                retry_after = next((value for key, value in headers.items() if key.lower() == 'retry-after'), None)
                try:
                    delay = max(0.0, float(retry_after)) if retry_after is not None else min(30, 2 ** (attempt + 1))
                except (TypeError, ValueError):
                    delay = min(30, 2 ** (attempt + 1))
                logger.debug('Retrying Spotify request after %.1fs: %s', delay, error)
                while delay > 0:
                    if cancel_check and cancel_check():
                        raise _FetchCancelled()
                    interval = min(delay, 0.1)
                    _sleep(interval)
                    delay = max(0, delay - interval)

    def _pages(self, fn, limit, cancel_check=None, *args, **kwargs):
        offset = 0
        while True:
            response = self._spotify_call(fn, *args, limit=limit, offset=offset, cancel_check=cancel_check, **kwargs)
            if not isinstance(response, dict) or not isinstance(response.get('items'), list):
                raise LibraryFetchError('Spotify returned an invalid page')
            items = response['items']
            logger.debug('Fetched %d Spotify items at offset %d', len(items), offset)
            yield items
            offset += len(items)
            total = response.get('total')
            if not items or (total is not None and offset >= total):
                return
            if not response.get('next') and (total is None or offset >= total):
                return

    @staticmethod
    def _song(item):
        track = item.get('item') or item.get('track')
        if not track or track.get('is_local') or item.get('is_local') or not track.get('id') or track.get('type', 'track') != 'track':
            return None
        return Song.from_spotify_track(track)

    def get_saved_tracks(self, cancel_check=None):
        self._saved_unavailable = 0
        songs = []
        for items in self._pages(self.auth.current_user_saved_tracks, 50, cancel_check):
            for item in items:
                song = self._song(item)
                if song:
                    songs.append(song)
                else:
                    self._saved_unavailable += 1
        return songs

    def _get_playlist_songs(self, playlist_id, cancel_check=None):
        songs = []
        unavailable = 0
        for items in self._pages(self.auth.playlist_items, 100, cancel_check, playlist_id, additional_types=('track',)):
            for item in items:
                song = self._song(item)
                if song is None:
                    unavailable += 1
                else:
                    songs.append(song)
        self._playlist_unavailable[playlist_id] = unavailable
        return songs

    def get_playlist_metadata(self, cancel_check=None):
        if self._user_id is None:
            profile = self._spotify_call(self.auth.current_user, cancel_check=cancel_check)
            self._user_id = profile.get('id') if isinstance(profile, dict) else None
            if not self._user_id:
                raise LibraryFetchError('Spotify did not return the current user id')
        items = [item for page in self._pages(self.auth.current_user_playlists, 50, cancel_check) for item in page]

        playlists = []
        for item in items:
            playlist = Playlist(name=item.get('name'), url=(item.get('external_urls') or {}).get('spotify'), id=item.get('id'))
            if (item.get('owner') or {}).get('id') != self._user_id and not item.get('collaborative'):
                playlist.skipped_reason = 'not owned or collaborative; Spotify does not expose its tracks'
            playlists.append(playlist)
        return playlists

    def _load_playlist(self, playlist, cancel_check=None):
        if playlist.skipped_reason:
            return playlist
        try:
            if not playlist.id:
                raise LibraryFetchError('Playlist has no id')
            playlist.songs = self._get_playlist_songs(playlist.id, cancel_check)
        except LibraryFetchError as error:
            playlist.error = str(error)
        return playlist

    def get_playlists(self, cancel_check=None):
        playlists = self.get_playlist_metadata(cancel_check)
        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(lambda playlist: self._load_playlist(playlist, cancel_check), playlists))

    def browse_collections(self, download_path, cancel_check=None, selected_key=None):
        """Yield the complete sidebar before fetching contents; never write files."""
        root = os.path.abspath(os.path.expanduser(os.fspath(download_path)))
        playlists = self.get_playlist_metadata(cancel_check)
        destinations = self._playlist_directories(root, playlists)
        saved_key = CollectionKey(self._user_id, 'saved')
        saved_destination = os.path.join(root, 'my_songs')
        yield CollectionSnapshot(saved_key, 'Saved tracks', saved_destination, metadata='not_loaded')
        for playlist, destination in zip(playlists, destinations):
            yield CollectionSnapshot(CollectionKey(self._user_id, playlist.id or ''), playlist.name or 'Untitled playlist', destination,
                                     metadata='restricted' if playlist.skipped_reason else 'not_loaded', error=playlist.skipped_reason)
        if cancel_check and cancel_check():
            return
        index = LocalFileIndex(root, cancel_check)
        if cancel_check and cancel_check():
            return
        try:
            songs = self.get_saved_tracks(cancel_check)
            yield CollectionSnapshot(saved_key, 'Saved tracks', saved_destination,
                                     tracks=index.reconcile(songs, saved_destination), skipped_count=self._saved_unavailable,
                                     error=index.error, refreshed_at=time.time(), scan_complete=index.complete)
        except LibraryFetchError as error:
            yield CollectionSnapshot(saved_key, 'Saved tracks', saved_destination, metadata='error', error=str(error))
        pending = list(zip(playlists, destinations))
        while pending:
            priority = selected_key() if callable(selected_key) else selected_key
            if priority is not None:
                pending.sort(key=lambda pair: CollectionKey(self._user_id, pair[0].id or '') != priority)
            playlist, destination = pending.pop(0)
            if cancel_check and cancel_check():
                return
            if playlist.skipped_reason:
                continue
            self._load_playlist(playlist, cancel_check)
            key = CollectionKey(self._user_id, playlist.id or '')
            if playlist.error:
                yield CollectionSnapshot(key, playlist.name or 'Untitled playlist', destination, metadata='error', error=playlist.error)
            else:
                yield CollectionSnapshot(key, playlist.name or 'Untitled playlist', destination,
                                         tracks=index.reconcile(playlist.songs, destination),
                                         skipped_count=self._playlist_unavailable.get(playlist.id, 0),
                                         error=index.error, refreshed_at=time.time(), scan_complete=index.complete)

    def _get_downloaded_track_ids(self, directory):
        if not os.path.isdir(directory):
            return set()
        return {track_id for entry in os.scandir(directory) if entry.is_file() and (track_id := track_id_from_filename(entry.name))}

    @staticmethod
    def _playlist_directories(download_path, playlists):
        names = [sanitize_path_component(playlist.name) for playlist in playlists]
        counts = {}
        for name in names:
            counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
        return [os.path.join(download_path, 'playlists', name + (f' [{(playlist.id or "unknown")[:6]}]' if counts[name.casefold()] > 1 else '')) for name, playlist in zip(names, playlists)]

    @staticmethod
    def _new_songs(songs, downloaded):
        seen = set(downloaded)
        new = []
        for song in songs:
            if song.track_id and song.track_id not in seen:
                new.append(song)
                seen.add(song.track_id)
        return new

    def sync_songs(self, downloader, progress_callback=None):
        result = SyncResult()
        try:
            songs = self.get_saved_tracks(cancel_check=downloader.is_cancelled)
            if self._saved_unavailable:
                result.add_note(f'Skipped {self._saved_unavailable} unavailable, local, or id-less saved tracks.')
            if downloader.is_cancelled():
                raise _FetchCancelled()
            directory = os.path.join(configutils.get_download_path(), 'my_songs')
            os.makedirs(directory, exist_ok=True)
            repair.flatten_nested_tracks(directory)
            new = self._new_songs(songs, self._get_downloaded_track_ids(directory))
            result.add_skipped(len(songs) - len(new))
            logger.info('Saved tracks: downloading %d new songs out of %d', len(new), len(songs))
            if new:
                result.merge(downloader.download(new, directory, progress_callback=progress_callback))
        except _FetchCancelled:
            result.cancelled = True
        except (LibraryFetchError, OSError) as error:
            result.add_failure('Saved tracks', None, str(error))
        result.cancelled |= downloader.is_cancelled()
        return result

    def sync_playlists(self, downloader, progress_callback=None):
        result = SyncResult()
        plans = []
        try:
            playlists = self.get_playlists(cancel_check=downloader.is_cancelled)
            directories = self._playlist_directories(configutils.get_download_path(), playlists)
            for playlist, directory in zip(playlists, directories):
                if downloader.is_cancelled():
                    raise _FetchCancelled()
                if playlist.skipped_reason:
                    result.add_note(f'Playlist {playlist.name} skipped: {playlist.skipped_reason}')
                    continue
                if playlist.error:
                    result.add_failure(playlist.name, playlist.url, playlist.error)
                    continue
                try:
                    os.makedirs(directory, exist_ok=True)
                    repair.flatten_nested_tracks(directory)
                    new = self._new_songs(playlist.songs, self._get_downloaded_track_ids(directory))
                except OSError as error:
                    result.add_failure(playlist.name, playlist.url, str(error))
                    continue
                result.add_skipped(len(playlist.songs) - len(new))
                if new:
                    plans.append((new, directory))
            total = sum(len(songs) for songs, _ in plans)
            if progress_callback:
                progress_callback(0, total, '')
            offset = 0
            last_done = 0
            progress_lock = threading.Lock()
            for songs, directory in plans:
                if downloader.is_cancelled():
                    raise _FetchCancelled()
                def progress(done, _total, name, base=offset):
                    nonlocal last_done
                    if done == 0:
                        return
                    if progress_callback:
                        with progress_lock:
                            last_done = max(last_done, min(total, base + done))
                            progress_callback(last_done, total, name)
                result.merge(downloader.download(songs, directory, progress_callback=progress))
                offset += len(songs)
                if result.cancelled:
                    break
        except _FetchCancelled:
            result.cancelled = True
        except LibraryFetchError as error:
            result.add_failure('Playlists', None, str(error))
        result.cancelled |= downloader.is_cancelled()
        return result

    def repair_library(self, progress_callback=None, cancel_check=None):
        result = SyncResult()
        cancel_check = cancel_check or (lambda: False)
        songs = {}
        playlists = []
        try:
            for song in self.get_saved_tracks(cancel_check):
                songs[song.track_id] = song
            playlists = self.get_playlists(cancel_check)
            for playlist in playlists:
                if playlist.error:
                    result.add_failure(playlist.name, playlist.url, playlist.error)
                elif playlist.skipped_reason:
                    result.add_note(f'Playlist {playlist.name} skipped: {playlist.skipped_reason}')
                for song in playlist.songs:
                    songs.setdefault(song.track_id, song)
            root = configutils.get_download_path()
            directories = [os.path.join(root, 'my_songs')] + self._playlist_directories(root, playlists)
            files = []
            for directory in dict.fromkeys(directories):
                if cancel_check():
                    raise _FetchCancelled()
                if not os.path.isdir(directory):
                    continue
                try:
                    moved = repair.flatten_nested_tracks(directory)
                    if moved:
                        result.add_note(f'Flattened {moved} nested tracks in {directory}.')
                    for entry in sorted(os.scandir(directory), key=lambda entry: entry.name):
                        track_id = track_id_from_filename(entry.name)
                        if entry.is_file() and track_id in songs:
                            files.append((entry.path, directory, songs[track_id]))
                except OSError as error:
                    result.add_failure(directory, None, str(error))
            if progress_callback:
                progress_callback(0, len(files), '')
            rejected = []
            for done, (path, directory, song) in enumerate(files, 1):
                if cancel_check():
                    raise _FetchCancelled()
                try:
                    duration = metadatautils.read_duration(path)
                    if duration is None or not durationcheck.within_tolerance(duration, song.duration_ms, lenient=True):
                        repair.quarantine(path, directory)
                        rejected.append(os.path.basename(path))
                        result.add_success()
                    elif not metadatautils.has_basic_tags(path):
                        if not metadatautils.embed_metadata(path, song, embed_art=True):
                            raise OSError('Could not embed metadata')
                        result.add_success()
                    else:
                        result.add_skipped()
                except Exception as error:
                    result.add_failure(os.path.basename(path), song.url, str(error))
                if progress_callback:
                    progress_callback(done, len(files), f'{song.artist} - {song.name}')
            if rejected:
                result.add_note(f'Quarantined {len(rejected)} wrong-length or unreadable tracks: ' + ', '.join(rejected[:5]) + (' …' if len(rejected) > 5 else ''))
        except _FetchCancelled:
            result.cancelled = True
        except LibraryFetchError as error:
            result.add_failure('Spotify library', None, str(error))
        return result
