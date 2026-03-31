from model.downloadable import Downloadable


class Song(Downloadable):
    def __init__(
        self,
        name=None,
        artist=None,
        url=None,
        track_id=None,
        album=None,
        album_art_url=None,
        release_date=None,
        duration_ms=None,
        track_number=None,
        disc_number=None,
        isrc=None,
        explicit=None,
        popularity=None,
        all_artists=None,
        genres=None,
        album_id=None,
        album_type=None,
        label=None,
        copyright_text=None
    ):
        self.name = name
        self.artist = artist
        self.url = url
        self.track_id = track_id
        # Extended metadata fields
        self.album = album
        self.album_art_url = album_art_url
        self.release_date = release_date
        self.duration_ms = duration_ms
        self.track_number = track_number
        self.disc_number = disc_number
        self.isrc = isrc
        self.explicit = explicit
        self.popularity = popularity
        self.all_artists = all_artists
        self.genres = genres
        self.album_id = album_id
        self.album_type = album_type
        self.label = label
        self.copyright_text = copyright_text

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

    @classmethod
    def from_spotify_track(cls, track_data: dict) -> 'Song':
        """
        Create a Song instance from Spotify API track response.

        Args:
            track_data: Dictionary from Spotify API's track object

        Returns:
            Song instance with all available metadata populated
        """
        # Basic track info
        track_id = track_data.get('id')
        name = track_data.get('name')
        url = track_data.get('external_urls', {}).get('spotify')

        # Artist info (primary + all artists)
        artists = track_data.get('artists', [])
        artist = artists[0].get('name') if artists else None
        all_artists = [a.get('name') for a in artists] if artists else None

        # Album info
        album = track_data.get('album', {})
        album_name = album.get('name')
        album_id = album.get('id')
        album_type = album.get('album_type')
        release_date = album.get('release_date')

        # Album art - prefer largest image
        images = album.get('images', [])
        album_art_url = None
        if images:
            # Sort by height descending to get the largest
            sorted_images = sorted(images, key=lambda x: x.get('height', 0), reverse=True)
            album_art_url = sorted_images[0].get('url')

        # Label and copyright
        label = album.get('label')
        copyrights = album.get('copyrights', [])
        copyright_text = copyrights[0].get('text') if copyrights else None

        # External IDs (ISRC)
        external_ids = track_data.get('external_ids', {})
        isrc = external_ids.get('isrc')

        return cls(
            name=name,
            artist=artist,
            url=url,
            track_id=track_id,
            album=album_name,
            album_art_url=album_art_url,
            release_date=release_date,
            duration_ms=track_data.get('duration_ms'),
            track_number=track_data.get('track_number'),
            disc_number=track_data.get('disc_number'),
            isrc=isrc,
            explicit=track_data.get('explicit'),
            popularity=track_data.get('popularity'),
            all_artists=all_artists,
            album_id=album_id,
            album_type=album_type,
            label=label,
            copyright_text=copyright_text
        )

    def to_metadata_dict(self) -> dict:
        """
        Convert song to a dictionary suitable for ID3 tag embedding.

        Returns:
            Dictionary with metadata fields for MP3 tagging
        """
        metadata = {
            'title': self.name,
            'artist': self.artist,
            'album': self.album,
            'track_number': self.track_number,
            'disc_number': self.disc_number,
            'date': self.release_date,
            'isrc': self.isrc,
            'artists': self.all_artists if self.all_artists else [],
            'genres': self.genres if self.genres else [],
            'album_art_url': self.album_art_url,
            'label': self.label,
            'copyright': self.copyright_text,
        }
        return metadata

    def duration_formatted(self) -> str | None:
        """
        Return human-readable duration string (e.g., "3:45", "1:02:03").

        Returns:
            Formatted duration string or None if duration_ms is not set
        """
        if self.duration_ms is None:
            return None

        total_seconds = self.duration_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def year(self) -> str | None:
        """
        Extract the year from release_date.

        Returns:
            Year as string (e.g., "1975") or None if no release_date
        """
        if not self.release_date:
            return None
        # release_date can be "YYYY", "YYYY-MM", or "YYYY-MM-DD"
        return self.release_date[:4]
