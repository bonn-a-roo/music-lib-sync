"""
Tests for model classes - Song, Playlist, and Downloadable.
"""
import pytest

from model.song import Song
from model.playlist import Playlist
from model.downloadable import Downloadable


class TestDownloadable:
    """Tests for the Downloadable base class."""

    @pytest.mark.unit
    def test_is_downloadable_returns_true(self):
        """Test that is_downloadable returns True by default."""
        downloadable = Downloadable()
        assert downloadable.is_downloadable() is True


class TestSong:
    """Tests for the Song model."""

    @pytest.mark.unit
    def test_song_initialization_with_all_params(self):
        """Test creating a song with all parameters."""
        song = Song(
            name="Test Song",
            artist="Test Artist",
            url="https://example.com/song",
            track_id="abc123"
        )

        assert song.name == "Test Song"
        assert song.artist == "Test Artist"
        assert song.url == "https://example.com/song"
        assert song.track_id == "abc123"

    @pytest.mark.unit
    def test_song_initialization_with_partial_params(self):
        """Test creating a song with only some parameters."""
        song = Song(name="Test Song", artist="Test Artist")

        assert song.name == "Test Song"
        assert song.artist == "Test Artist"
        assert song.url is None
        assert song.track_id is None

    @pytest.mark.unit
    def test_song_initialization_with_no_params(self):
        """Test creating a song with no parameters."""
        song = Song()

        assert song.name is None
        assert song.artist is None
        assert song.url is None
        assert song.track_id is None

    @pytest.mark.unit
    def test_str_representation(self):
        """Test the string representation of a song."""
        song = Song(name="Song Title", artist="Artist Name")
        result = str(song)

        assert result == "Song Title - Artist Name"

    @pytest.mark.unit
    def test_str_representation_with_none_values(self):
        """Test string representation when values are None."""
        song = Song()
        result = str(song)

        assert result == "None - None"

    @pytest.mark.unit
    def test_spotify_uri_with_track_id(self):
        """Test Spotify URI generation with a track ID."""
        song = Song(track_id="4iV5W9uYEdYUVa79Axb7Rh")
        result = song.spotify_uri

        assert result == "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"

    @pytest.mark.unit
    def test_spotify_uri_without_track_id(self):
        """Test Spotify URI generation without a track ID."""
        song = Song()
        result = song.spotify_uri

        assert result is None

    @pytest.mark.unit
    def test_spotify_uri_with_empty_track_id(self):
        """Test Spotify URI generation with empty track ID."""
        # Note: Empty string is falsy, so returns None
        song = Song(track_id="")
        result = song.spotify_uri

        assert result is None

    @pytest.mark.unit
    def test_song_is_downloadable(self):
        """Test that Song inherits is_downloadable from Downloadable."""
        song = Song()
        assert song.is_downloadable() is True


class TestPlaylist:
    """Tests for the Playlist model."""

    @pytest.mark.unit
    def test_playlist_initialization_with_all_params(self):
        """Test creating a playlist with all parameters."""
        songs = [Song(name="Song 1"), Song(name="Song 2")]
        playlist = Playlist(
            name="My Playlist",
            songs=songs,
            url="https://example.com/playlist"
        )

        assert playlist.name == "My Playlist"
        assert playlist.songs == songs
        assert len(playlist.songs) == 2
        assert playlist.url == "https://example.com/playlist"

    @pytest.mark.unit
    def test_playlist_initialization_with_no_params(self):
        """Test creating a playlist with default parameters."""
        playlist = Playlist()

        assert playlist.name is None
        assert playlist.songs == []
        assert playlist.url is None

    @pytest.mark.unit
    def test_playlist_initialization_with_name_only(self):
        """Test creating a playlist with only a name."""
        playlist = Playlist(name="Test Playlist")

        assert playlist.name == "Test Playlist"
        assert playlist.songs == []
        assert playlist.url is None

    @pytest.mark.unit
    def test_playlist_with_songs_list(self):
        """Test that songs list is properly stored."""
        song1 = Song(name="Song 1", artist="Artist 1")
        song2 = Song(name="Song 2", artist="Artist 2")
        songs = [song1, song2]

        playlist = Playlist(name="Mix", songs=songs)

        assert playlist.songs[0].name == "Song 1"
        assert playlist.songs[1].name == "Song 2"

    @pytest.mark.unit
    def test_playlist_is_downloadable(self):
        """Test that Playlist inherits is_downloadable from Downloadable."""
        playlist = Playlist()
        assert playlist.is_downloadable() is True

    @pytest.mark.unit
    def test_default_mutable_argument_not_shared(self):
        """Test that the default songs=[] is not shared between instances."""
        playlist1 = Playlist(name="Playlist 1")
        playlist2 = Playlist(name="Playlist 2")

        playlist1.songs.append(Song(name="Shared Song"))
        assert playlist2.songs == []
        assert playlist1.songs[0].name == "Shared Song"


@pytest.mark.unit
@pytest.mark.parametrize("track", [None, {}])
def test_empty_spotify_track(track):
    assert Song.from_spotify_track(track) is None


@pytest.mark.unit
@pytest.mark.parametrize("album", [None, {}, {"images": [{"height": None, "url": "small"}, {"height": 640, "url": "large"}]}])
def test_nullable_spotify_metadata(album):
    song = Song.from_spotify_track({"id": "abc", "album": album, "artists": [], "external_urls": None, "external_ids": None})
    assert song.track_id == "abc"
    assert song.artist is None
    assert song.url is None
    assert song.album_art_url == ("large" if album and album.get("images") else None)
