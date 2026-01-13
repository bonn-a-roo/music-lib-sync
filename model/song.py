from model.downloadable import Downloadable


class Song(Downloadable):
    def __init__(self, name=None, artist=None, url=None, track_id=None):
        self.name = name
        self.artist = artist
        self.url = url
        self.track_id = track_id

    def __str__(self):
        return f"{self.name} - {self.artist}"

    def desc_filename(self):
        return f"{self.artist} - {self.name}.mp3"

    @property
    def spotify_uri(self):
        """Get the Spotify URI (e.g., spotify:track:...) from track_id."""
        if self.track_id:
            return f"spotify:track:{self.track_id}"
        return None
