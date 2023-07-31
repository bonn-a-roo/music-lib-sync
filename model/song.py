from model.downloadable import Downloadable


class Song(Downloadable):
    def __init__(self, name=None, artist=None, url=None):
        self.name = name
        self.artist = artist
        self.url = url

    def __str__(self):
        return f"{self.name} - {self.artist}"

    def __iter__(self):
        self.song_index = 0
        return self

    def __next__(self):
        if self.song_index >= len(self.name):
            raise StopIteration
        else:
            song_name = self.name[self.song_index]
            self.song_index += 1
            return self.song_index - 1, song_name

    def desc_filename(self):
        return self.artist + " - " + self.name + ".mp3"
