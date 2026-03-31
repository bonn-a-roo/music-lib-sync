import os
import threading
from abc import ABC, abstractmethod
from typing import List, Union

from model.playlist import Playlist
from model.song import Song
from model.sync_result import SyncResult
from utils.fileutils import create_directory
from utils.logutils import get_logger

logger = get_logger(__name__)


class Downloader(ABC):
    _lock = threading.Lock()
    _progress_counter = 0
    _total_items = 0

    @abstractmethod
    def download_playlist(self, playlist, download_path) -> bool:
        """Download a playlist. Returns True if successful."""
        pass

    @abstractmethod
    def download_song(self, song, download_path) -> bool:
        """Download a song. Returns True if successful."""
        pass

    def post_process_song(self, song, download_path: str) -> bool:
        """
        Post-process a downloaded song (e.g., embed metadata).
        Override in subclasses to add custom post-processing.

        Args:
            song: Song object with metadata
            download_path: Directory where the song was downloaded

        Returns:
            True if successful, False otherwise
        """
        return True

    def _find_downloaded_file(self, song: Song, download_path: str) -> str | None:
        """
        Find the downloaded file for a song in the download directory.

        Args:
            song: Song object
            download_path: Directory to search

        Returns:
            Path to the found file or None
        """
        if not os.path.exists(download_path):
            return None

        # Try to find file by track_id (spotdl pattern: {artist} - {name} [{id}].mp3)
        if song.track_id:
            for filename in os.listdir(download_path):
                if song.track_id in filename and filename.endswith('.mp3'):
                    return os.path.join(download_path, filename)

        # Try to find file by name pattern
        pattern = f"{song.artist} - {song.name}"
        for filename in os.listdir(download_path):
            if pattern.lower() in filename.lower() and filename.endswith('.mp3'):
                return os.path.join(download_path, filename)

        return None

    def download_songs_worker(self, songs, download_path, result: SyncResult):
        with self._lock:
            create_directory(download_path)

        for song in songs:
            # Increment progress counter atomically
            with self._lock:
                self._progress_counter += 1
                current = self._progress_counter
                total = self._total_items
            
            logger.info(f"Downloading ({current}/{total}): {song.artist} - {song.name}")
            if self.download_song(song, download_path):
                # Post-process the downloaded song
                self.post_process_song(song, download_path)
                result.add_success()
                logger.info(f"[OK] Completed: {song.name}")
            else:
                result.add_failure(str(song), song.url, "Download failed")
                logger.warning(f"[FAIL] Failed: {song.name}")

    def download_playlists_worker(self, playlists, download_path, result: SyncResult):
        for playlist in playlists:
            # Increment progress counter atomically
            with self._lock:
                self._progress_counter += 1
                current = self._progress_counter
                total = self._total_items
            
            logger.info(f"Downloading playlist ({current}/{total}): {playlist.name}")
            if self.download_playlist(playlist, download_path):
                result.add_success()
                logger.info(f"[OK] Completed playlist: {playlist.name}")
            else:
                result.add_failure(playlist.name, playlist.url, "Download failed")
                logger.warning(f"[FAIL] Failed playlist: {playlist.name}")

    def download(self, objects: List[Union[Song, Playlist]], download_path, num_threads=2) -> SyncResult:
        result = SyncResult()

        if not objects:
            logger.warning("No objects to download")
            return result

        if not all(item.is_downloadable() for item in objects):
            logger.error("Method can only be used with Downloadable types.")
            return result

        if all(isinstance(item, Song) for item in objects):
            worker = self.download_songs_worker
        elif all(isinstance(item, Playlist) for item in objects):
            worker = self.download_playlists_worker
        else:
            logger.error("Method can only be used with homogeneous Downloadable types.")
            return result

        # Limit threads to number of objects
        num_threads = max(1, min(num_threads, len(objects)))
        segment_size = len(objects) // num_threads

        # Reset and initialize progress tracking
        self._progress_counter = 0
        self._total_items = len(objects)

        threads = []
        for i in range(num_threads):
            start = i * segment_size
            # For the last thread, include all remaining objects
            end = len(objects) if i == num_threads - 1 else start + segment_size
            objects_segment = objects[start:end]

            # Skip creating thread if segment is empty
            if not objects_segment:
                continue

            thread = threading.Thread(target=worker, args=(objects_segment, download_path, result))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        logger.info(f"Download complete: {result.success_count} succeeded, {result.failure_count} failed, {result.skipped_count} skipped")
        return result
