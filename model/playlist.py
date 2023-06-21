from model.downloadable import Downloadable


class Playlist(Downloadable):
    def __init__(self, name=None, songs=[], url=None):
        self.name = name
        self.songs = songs
        self.url = url
