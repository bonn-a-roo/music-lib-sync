from model.downloadable import Downloadable


class Playlist(Downloadable):
    def __init__(self, name=None, songs=None, url=None):
        self.name = name
        self.songs = songs if songs is not None else []
        self.url = url
