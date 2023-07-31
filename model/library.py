import abc
import os

from downloaders.spotifydl import SpotifyDownloader
from model.playlist import Playlist
from model.song import Song
from utils import configutils


class LibrarySyncSource(abc.ABC):
    @abc.abstractmethod
    def synchronize(self):
        pass


class SpotifyLibrary(LibrarySyncSource):
    def __init__(self, auth):
        self.auth = auth

    def get_saved_tracks(self, limit_step=50):
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

    def synchronize(self):
        downloader = SpotifyDownloader()
        download_path = configutils.get_download_path()
        # download_path = ask_download_path()

        my_songs = self.get_saved_tracks()
        # my_songs = get_all_saved_songs_stub()
        my_playlists = self.get_playlists()

        downloaded_files = set(os.listdir(download_path + "/my_songs"))
        songs_to_download = [song.desc_filename() for song in my_songs]
        songs_to_download = set(songs_to_download) - downloaded_files
        songs_to_download = list(songs_to_download)

        my_songs = [song for song in my_songs if song.desc_filename() in songs_to_download]
        # TODO: (Still gets many songs that are already downloaded: ej. with combined artists)

        # TODO: (Playlists songs should be checked individually before avoiding the whole playlist)
        #playlists_to_download = [playlist.name for playlist in my_playlists]
        #playlists_to_download = set(playlists_to_download) - downloaded_files
        #playlists_to_download = list(playlists_to_download)

        #my_playlists = [playlist for playlist in my_playlists if playlist.name in playlists_to_download]

        downloader.download(my_songs, download_path, num_threads=16)
        downloader.download(my_playlists, download_path, num_threads=16)

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
