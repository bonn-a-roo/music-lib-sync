from model.downloadable import Downloadable


class Playlist(Downloadable):
    def __init__(self, name=None, songs=None, url=None, id=None, skipped_reason=None, error=None):
        self.name = name
        self.songs = songs if songs is not None else []
        self.url = url
        self.id = id
        self.skipped_reason = skipped_reason
        self.error = error
