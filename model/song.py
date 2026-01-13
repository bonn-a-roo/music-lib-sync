from model.downloadable import Downloadable


class Song(Downloadable):
    def __init__(self, name=None, artist=None, url=None):
        self.name = name
        self.artist = artist
        self.url = url

    def __str__(self):
        return f"{self.name} - {self.artist}"

    def desc_filename(self):
        return f"{self.artist} - {self.name}.mp3"
