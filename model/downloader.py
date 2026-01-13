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

    @abstractmethod
    def download_playlist(self, playlist, download_path) -> bool:
        """Download a playlist. Returns True if successful."""
        pass

    @abstractmethod
    def download_song(self, song, download_path) -> bool:
        """Download a song. Returns True if successful."""
        pass

    def download_songs_worker(self, songs, download_path, result: SyncResult):
        with self._lock:
            create_directory(download_path)

        for song in songs:
            if self.download_song(song, download_path):
                result.add_success()
            else:
                result.add_failure(str(song), song.url, "Download failed")

    def download_playlists_worker(self, playlists, download_path, result: SyncResult):
        for playlist in playlists:
            if self.download_playlist(playlist, download_path):
                result.add_success()
            else:
                result.add_failure(playlist.name, playlist.url, "Download failed")

    def download(self, objects: List[Union[Song, Playlist]], download_path, num_threads=2) -> SyncResult:
        result = SyncResult()

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

        segment_size = len(objects) // num_threads

        threads = []
        for i in range(num_threads):
            start = i * segment_size
            end = start + segment_size
            objects_segment = objects[start:end]

            thread = threading.Thread(target=worker, args=(objects_segment, download_path, result))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        return result
