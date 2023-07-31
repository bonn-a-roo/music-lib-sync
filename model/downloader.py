import threading
from abc import ABC, abstractmethod

from model.playlist import Playlist
from model.song import Song
from utils.fileutils import create_directory


class Downloader(ABC):
    _lock = threading.Lock()

    @abstractmethod
    def download_playlist(self, playlist, download_path):
        pass

    @abstractmethod
    def download_song(self, song, download_path):
        pass

    def download_songs_worker(self, songs, download_path):
        with self._lock:
            create_directory(download_path)

        for song in songs:
            self.download_song(song, download_path)

    def download_playlists_worker(self, playlists, download_path):
        for playlist in playlists:
            self.download_playlist(playlist, download_path)

    def download(self, objects, download_path, num_threads=2):
        if all(item.is_downloadable() for item in objects):
            if all(isinstance(item, Song) for item in objects):
                worker = self.download_songs_worker
            elif all(isinstance(item, Playlist) for item in objects):
                worker = self.download_playlists_worker
            else:
                raise Exception("Method can only be used with Downloadable types.")

            segment_size = len(objects) // num_threads

            threads = []
            for i in range(num_threads):
                start = i * segment_size
                end = start + segment_size
                objects_segment = objects[start:end]

                thread = threading.Thread(target=worker, args=(objects_segment, download_path))
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()
        else:
            print("Method can only be used with Downloadable types.")

    def parse_songs_from_file(file_path):
        songs = []
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()

                for line in lines:
                    parts = line.strip().split(' - ')

                    if len(parts) == 2:
                        name = parts[0].strip()
                        artist = parts[1].strip()

                        song = Song(name, artist)
                        songs.append(song)

        except Exception as e:
            print(f"An error occurred while parsing the file: {str(e)}")

        return songs
