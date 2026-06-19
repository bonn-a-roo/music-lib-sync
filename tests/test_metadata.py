"""
Tests for song metadata functionality.

These tests cover:
1. Extended Song model with full metadata fields
2. Metadata extraction from Spotify API responses
3. Metadata embedding into MP3 files
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import os


# =============================================================================
# TESTS FOR EXPANDED SONG MODEL WITH METADATA
# =============================================================================

class TestSongMetadata:
    """Tests for the Song model with extended metadata fields."""

    @pytest.mark.unit
    def test_song_initialization_with_full_metadata(self):
        """Test creating a song with all metadata fields."""
        from model.song import Song

        song = Song(
            name="Bohemian Rhapsody",
            artist="Queen",
            url="https://open.spotify.com/track/4u7EnebtmKWzUH433cf5Qv",
            track_id="4u7EnebtmKWzUH433cf5Qv",
            # Extended metadata
            album="A Night at the Opera",
            album_art_url="https://i.scdn.co/image/abc123",
            release_date="1975-10-31",
            duration_ms=354320,
            track_number=11,
            disc_number=1,
            isrc="GBUM71029604",
            explicit=False,
            popularity=85,
            all_artists=["Queen"],
            genres=["rock", "classic rock"],
            album_id="1GbtB4zTqAsyfZEsm1RZfx",
            album_type="album",
            label="Hollywood Records",
            copyright_text="© 1975 Queen Productions Ltd."
        )

        assert song.name == "Bohemian Rhapsody"
        assert song.artist == "Queen"
        assert song.album == "A Night at the Opera"
        assert song.album_art_url == "https://i.scdn.co/image/abc123"
        assert song.release_date == "1975-10-31"
        assert song.duration_ms == 354320
        assert song.track_number == 11
        assert song.disc_number == 1
        assert song.isrc == "GBUM71029604"
        assert song.explicit is False
        assert song.popularity == 85
        assert song.all_artists == ["Queen"]
        assert song.genres == ["rock", "classic rock"]
        assert song.album_id == "1GbtB4zTqAsyfZEsm1RZfx"
        assert song.album_type == "album"
        assert song.label == "Hollywood Records"
        assert song.copyright_text == "© 1975 Queen Productions Ltd."

    @pytest.mark.unit
    def test_song_metadata_defaults_to_none(self):
        """Test that new metadata fields default to None when not provided."""
        from model.song import Song

        song = Song(name="Test", artist="Artist")

        assert song.album is None
        assert song.album_art_url is None
        assert song.release_date is None
        assert song.duration_ms is None
        assert song.track_number is None
        assert song.disc_number is None
        assert song.isrc is None
        assert song.explicit is None
        assert song.popularity is None
        assert song.all_artists is None
        assert song.genres is None
        assert song.album_id is None
        assert song.album_type is None
        assert song.label is None
        assert song.copyright_text is None

    @pytest.mark.unit
    def test_song_with_multiple_artists(self):
        """Test song with multiple artists."""
        from model.song import Song

        song = Song(
            name="Under Pressure",
            artist="Queen",  # Primary artist
            all_artists=["Queen", "David Bowie"]
        )

        assert song.artist == "Queen"
        assert song.all_artists == ["Queen", "David Bowie"]
        assert len(song.all_artists) == 2

    @pytest.mark.unit
    def test_song_to_metadata_dict(self):
        """Test converting song to a metadata dictionary for embedding."""
        from model.song import Song

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=5,
            disc_number=1,
            release_date="2023-01-15",
            all_artists=["Test Artist", "Featured Artist"],
            genres=["pop", "electronic"],
            isrc="USRC12345678"
        )

        metadata = song.to_metadata_dict()

        assert metadata['title'] == "Test Song"
        assert metadata['artist'] == "Test Artist"
        assert metadata['album'] == "Test Album"
        assert metadata['track_number'] == 5
        assert metadata['disc_number'] == 1
        assert metadata['date'] == "2023-01-15"
        assert "Test Artist" in metadata['artists']
        assert "Featured Artist" in metadata['artists']
        assert metadata['isrc'] == "USRC12345678"

    @pytest.mark.unit
    def test_song_from_spotify_track_dict(self):
        """Test creating a Song from a Spotify API track response."""
        from model.song import Song

        # Simulated Spotify API track response
        spotify_track = {
            'id': '4u7EnebtmKWzUH433cf5Qv',
            'name': 'Bohemian Rhapsody',
            'artists': [
                {'name': 'Queen', 'id': '1dfeR4HaWDbWqFHLkxsg1d'}
            ],
            'album': {
                'id': '1GbtB4zTqAsyfZEsm1RZfx',
                'name': 'A Night at the Opera',
                'album_type': 'album',
                'release_date': '1975-10-31',
                'images': [
                    {'url': 'https://i.scdn.co/image/large', 'height': 640},
                    {'url': 'https://i.scdn.co/image/medium', 'height': 300},
                    {'url': 'https://i.scdn.co/image/small', 'height': 64}
                ],
                'label': 'Hollywood Records',
                'copyrights': [
                    {'text': '© 1975 Queen Productions Ltd.', 'type': 'C'}
                ]
            },
            'external_urls': {
                'spotify': 'https://open.spotify.com/track/4u7EnebtmKWzUH433cf5Qv'
            },
            'external_ids': {
                'isrc': 'GBUM71029604'
            },
            'duration_ms': 354320,
            'track_number': 11,
            'disc_number': 1,
            'explicit': False,
            'popularity': 85
        }

        song = Song.from_spotify_track(spotify_track)

        assert song.track_id == '4u7EnebtmKWzUH433cf5Qv'
        assert song.name == 'Bohemian Rhapsody'
        assert song.artist == 'Queen'
        assert song.album == 'A Night at the Opera'
        assert song.album_id == '1GbtB4zTqAsyfZEsm1RZfx'
        assert song.album_type == 'album'
        assert song.release_date == '1975-10-31'
        assert song.album_art_url == 'https://i.scdn.co/image/large'
        assert song.duration_ms == 354320
        assert song.track_number == 11
        assert song.disc_number == 1
        assert song.isrc == 'GBUM71029604'
        assert song.explicit is False
        assert song.popularity == 85
        assert song.label == 'Hollywood Records'

    @pytest.mark.unit
    def test_song_from_spotify_track_with_multiple_artists(self):
        """Test creating a Song from Spotify track with multiple artists."""
        from model.song import Song

        spotify_track = {
            'id': 'test123',
            'name': 'Collaboration Song',
            'artists': [
                {'name': 'Artist One', 'id': 'id1'},
                {'name': 'Artist Two', 'id': 'id2'},
                {'name': 'Artist Three', 'id': 'id3'}
            ],
            'album': {
                'id': 'album123',
                'name': 'Collab Album',
                'album_type': 'album',
                'release_date': '2023-06-15',
                'images': []
            },
            'external_urls': {'spotify': 'https://open.spotify.com/track/test123'},
            'external_ids': {},
            'duration_ms': 200000,
            'track_number': 1,
            'disc_number': 1,
            'explicit': False,
            'popularity': 50
        }

        song = Song.from_spotify_track(spotify_track)

        assert song.artist == 'Artist One'
        assert song.all_artists == ['Artist One', 'Artist Two', 'Artist Three']

    @pytest.mark.unit
    def test_song_from_spotify_track_handles_missing_fields(self):
        """Test that from_spotify_track handles missing optional fields gracefully."""
        from model.song import Song

        # Minimal Spotify track response
        spotify_track = {
            'id': 'minimal123',
            'name': 'Minimal Song',
            'artists': [{'name': 'Artist', 'id': 'aid'}],
            'album': {
                'id': 'alb1',
                'name': 'Album',
                'album_type': 'single',
                'release_date': '2023-01-01',
                'images': []
            },
            'external_urls': {'spotify': 'https://open.spotify.com/track/minimal123'},
            'duration_ms': 180000,
            'track_number': 1,
            'disc_number': 1,
            'explicit': False,
            'popularity': 0
            # Missing: external_ids, label, copyrights
        }

        song = Song.from_spotify_track(spotify_track)

        assert song.name == 'Minimal Song'
        assert song.isrc is None
        assert song.label is None
        assert song.copyright_text is None
        assert song.album_art_url is None

    @pytest.mark.unit
    def test_song_duration_formatted(self):
        """Test getting formatted duration string from duration_ms."""
        from model.song import Song

        song = Song(name="Test", artist="Artist", duration_ms=354320)  # 5:54.320

        formatted = song.duration_formatted()

        assert formatted == "5:54"

    @pytest.mark.unit
    def test_song_duration_formatted_with_hours(self):
        """Test formatted duration for songs longer than an hour."""
        from model.song import Song

        song = Song(name="Long Song", artist="Artist", duration_ms=3723000)  # 1:02:03

        formatted = song.duration_formatted()

        assert formatted == "1:02:03"

    @pytest.mark.unit
    def test_song_duration_formatted_returns_none_when_no_duration(self):
        """Test that duration_formatted returns None when duration_ms is not set."""
        from model.song import Song

        song = Song(name="Test", artist="Artist")

        assert song.duration_formatted() is None

    @pytest.mark.unit
    def test_song_year_property(self):
        """Test extracting year from release_date."""
        from model.song import Song

        song = Song(name="Test", artist="Artist", release_date="1975-10-31")

        assert song.year == "1975"

    @pytest.mark.unit
    def test_song_year_property_with_year_only_date(self):
        """Test year property when release_date only contains year."""
        from model.song import Song

        song = Song(name="Test", artist="Artist", release_date="1975")

        assert song.year == "1975"

    @pytest.mark.unit
    def test_song_year_returns_none_when_no_date(self):
        """Test year property returns None when no release_date."""
        from model.song import Song

        song = Song(name="Test", artist="Artist")

        assert song.year is None


# =============================================================================
# TESTS FOR METADATA EXTRACTION FROM SPOTIFY API
# =============================================================================

class TestSpotifyMetadataExtraction:
    """Tests for extracting full metadata from Spotify API responses."""

    @pytest.mark.unit
    def test_get_saved_tracks_extracts_full_metadata(self):
        """Test that get_saved_tracks extracts all available metadata."""
        from model.library import SpotifyLibrary

        mock_auth = MagicMock()
        # Use side_effect to simulate Spotify API pagination (first page has items, second is empty)
        mock_auth.current_user_saved_tracks.side_effect = [
            {
                'items': [{
                    'track': {
                        'id': 'track123',
                        'name': 'Test Track',
                        'artists': [
                            {'name': 'Main Artist', 'id': 'artist1'},
                            {'name': 'Featured', 'id': 'artist2'}
                        ],
                        'album': {
                            'id': 'album123',
                            'name': 'Test Album',
                            'album_type': 'album',
                            'release_date': '2023-05-20',
                            'images': [{'url': 'https://image.url', 'height': 640}],
                            'label': 'Test Label',
                            'copyrights': [{'text': '© 2023 Test', 'type': 'C'}]
                        },
                        'external_urls': {'spotify': 'https://open.spotify.com/track/track123'},
                        'external_ids': {'isrc': 'USTEST123456'},
                        'duration_ms': 240000,
                        'track_number': 3,
                        'disc_number': 1,
                        'explicit': True,
                        'popularity': 72
                    }
                }]
            },
            {'items': []}  # Simulate end of pagination
        ]

        library = SpotifyLibrary(mock_auth)
        songs = library.get_saved_tracks()

        assert len(songs) == 1
        song = songs[0]

        # Verify all metadata was extracted
        assert song.track_id == 'track123'
        assert song.name == 'Test Track'
        assert song.artist == 'Main Artist'
        assert song.all_artists == ['Main Artist', 'Featured']
        assert song.album == 'Test Album'
        assert song.album_id == 'album123'
        assert song.album_type == 'album'
        assert song.release_date == '2023-05-20'
        assert song.album_art_url == 'https://image.url'
        assert song.duration_ms == 240000
        assert song.track_number == 3
        assert song.disc_number == 1
        assert song.isrc == 'USTEST123456'
        assert song.explicit is True
        assert song.popularity == 72
        assert song.label == 'Test Label'

    @pytest.mark.unit
    def test_get_playlist_songs_extracts_full_metadata(self):
        """Test that _get_playlist_songs extracts all available metadata."""
        from model.library import SpotifyLibrary

        mock_auth = MagicMock()
        # Use side_effect to simulate Spotify API pagination (first page has items, second is empty)
        mock_auth.playlist_items.side_effect = [
            {
                'items': [{
                    'track': {
                        'id': 'playlisttrack1',
                        'name': 'Playlist Song',
                        'artists': [{'name': 'Playlist Artist', 'id': 'pa1'}],
                        'album': {
                            'id': 'palbum1',
                            'name': 'Playlist Album',
                            'album_type': 'single',
                            'release_date': '2024-01-10',
                            'images': [{'url': 'https://playlist.image', 'height': 640}]
                        },
                        'external_urls': {'spotify': 'https://open.spotify.com/track/playlisttrack1'},
                        'external_ids': {'isrc': 'USPLAY123456'},
                        'duration_ms': 195000,
                        'track_number': 1,
                        'disc_number': 1,
                        'explicit': False,
                        'popularity': 88
                    }
                }]
            },
            {'items': []}  # Simulate end of pagination
        ]

        library = SpotifyLibrary(mock_auth)
        songs = library._get_playlist_songs('playlist123')

        assert len(songs) == 1
        song = songs[0]
        assert song.album == 'Playlist Album'
        assert song.isrc == 'USPLAY123456'
        assert song.duration_ms == 195000

    @pytest.mark.unit
    def test_metadata_extraction_handles_none_track(self):
        """Test that metadata extraction handles None/unavailable tracks."""
        from model.library import SpotifyLibrary

        mock_auth = MagicMock()
        # Use side_effect to simulate pagination ending
        mock_auth.playlist_items.side_effect = [
            {
                'items': [
                    {'track': None},  # Unavailable track
                    {
                        'track': {
                            'id': 'valid1',
                            'name': 'Valid Song',
                            'artists': [{'name': 'Artist', 'id': 'a1'}],
                            'album': {
                                'id': 'al1',
                                'name': 'Album',
                                'album_type': 'album',
                                'release_date': '2023-01-01',
                                'images': []
                            },
                            'external_urls': {'spotify': 'https://spotify.com/track/valid1'},
                            'duration_ms': 180000,
                            'track_number': 1,
                            'disc_number': 1,
                            'explicit': False,
                            'popularity': 50
                        }
                    }
                ]
            },
            {'items': []}  # End pagination
        ]

        library = SpotifyLibrary(mock_auth)
        songs = library._get_playlist_songs('test_playlist')

        assert len(songs) == 1
        assert songs[0].name == 'Valid Song'


# =============================================================================
# TESTS FOR METADATA EMBEDDING IN MP3 FILES
# =============================================================================

class TestMetadataEmbedding:
    """Tests for embedding metadata into downloaded MP3 files."""

    @pytest.mark.unit
    @patch('utils.metadatautils.TIT2')
    @patch('utils.metadatautils.TPE1')
    @patch('utils.metadatautils.TALB')
    @patch('utils.metadatautils.TRCK')
    @patch('utils.metadatautils.TDRC')
    @patch('utils.metadatautils.mutagen')
    def test_embed_metadata_basic_tags(self, mock_mutagen, mock_tdrc, mock_trck, mock_talb, mock_tpe1, mock_tit2):
        """Test embedding basic metadata tags into an MP3 file."""
        from utils.metadatautils import embed_metadata
        from model.song import Song

        mock_mp3 = MagicMock()
        mock_mutagen.mp3.MP3.return_value = mock_mp3
        mock_mutagen.id3.ID3.return_value = MagicMock()

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=5,
            release_date="2023-06-15"
        )

        result = embed_metadata("/path/to/song.mp3", song)

        assert result is True
        mock_mutagen.mp3.MP3.assert_called_once_with("/path/to/song.mp3")

    @pytest.mark.unit
    @patch('utils.metadatautils.APIC')
    @patch('utils.metadatautils.TIT2')
    @patch('utils.metadatautils.TPE1')
    @patch('utils.metadatautils.mutagen')
    def test_embed_metadata_with_album_art(self, mock_mutagen, mock_tpe1, mock_tit2, mock_apic):
        """Test embedding album art into an MP3 file."""
        from utils.metadatautils import embed_metadata
        from model.song import Song

        mock_mp3 = MagicMock()
        mock_mutagen.mp3.MP3.return_value = mock_mp3

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album_art_url="https://i.scdn.co/image/test"
        )

        with patch('utils.metadatautils.requests.get') as mock_get:
            mock_get.return_value.content = b'fake_image_data'
            mock_get.return_value.status_code = 200

            result = embed_metadata("/path/to/song.mp3", song, embed_art=True)

            assert result is True

    @pytest.mark.unit
    @patch('utils.metadatautils.mutagen')
    def test_embed_metadata_handles_missing_file(self, mock_mutagen):
        """Test that embed_metadata handles missing file gracefully."""
        from utils.metadatautils import embed_metadata
        from model.song import Song

        mock_mutagen.mp3.MP3.side_effect = FileNotFoundError("File not found")

        song = Song(name="Test", artist="Artist")

        result = embed_metadata("/nonexistent/path.mp3", song)

        assert result is False

    @pytest.mark.unit
    @patch('utils.metadatautils.mutagen')
    def test_embed_metadata_handles_corrupt_file(self, mock_mutagen):
        """Test that embed_metadata handles corrupt MP3 files."""
        from utils.metadatautils import embed_metadata
        from model.song import Song

        mock_mutagen.mp3.MP3.side_effect = Exception("Invalid MP3 file")

        song = Song(name="Test", artist="Artist")

        result = embed_metadata("/corrupt/file.mp3", song)

        assert result is False

    @pytest.mark.unit
    @patch('utils.metadatautils.mutagen')
    def test_read_metadata_from_mp3(self, mock_mutagen):
        """Test reading existing metadata from an MP3 file."""
        from utils.metadatautils import read_metadata

        # Create a mock MP3 instance with tags
        mock_mp3_instance = MagicMock()
        mock_tags = {
            'TIT2': MagicMock(text=['Song Title']),
            'TPE1': MagicMock(text=['Artist Name']),
            'TALB': MagicMock(text=['Album Name']),
            'TRCK': MagicMock(text=['5/12']),
            'TDRC': MagicMock(text=['2023'])
        }
        mock_mp3_instance.tags = mock_tags
        mock_mutagen.mp3.MP3.return_value = mock_mp3_instance

        metadata = read_metadata("/path/to/song.mp3")

        assert metadata['title'] == 'Song Title'
        assert metadata['artist'] == 'Artist Name'
        assert metadata['album'] == 'Album Name'

    @pytest.mark.unit
    def test_verify_metadata_completeness(self):
        """Test verifying that all expected metadata is present in a file."""
        from utils.metadatautils import verify_metadata
        from model.song import Song

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=5,
            isrc="USTEST123456"
        )

        with patch('utils.metadatautils.read_metadata') as mock_read:
            mock_read.return_value = {
                'title': 'Test Song',
                'artist': 'Test Artist',
                'album': 'Test Album',
                'track_number': 5,
                'isrc': 'USTEST123456'
            }

            is_complete, missing = verify_metadata("/path/to/song.mp3", song)

            assert is_complete is True
            assert len(missing) == 0

    @pytest.mark.unit
    def test_verify_metadata_reports_missing_fields(self):
        """Test that verify_metadata reports missing fields."""
        from utils.metadatautils import verify_metadata
        from model.song import Song

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            isrc="USTEST123456"
        )

        with patch('utils.metadatautils.read_metadata') as mock_read:
            mock_read.return_value = {
                'title': 'Test Song',
                'artist': 'Test Artist'
                # Missing: album, isrc
            }

            is_complete, missing = verify_metadata("/path/to/song.mp3", song)

            assert is_complete is False
            assert 'album' in missing
            assert 'isrc' in missing


# =============================================================================
# TESTS FOR METADATA JSON EXPORT
# =============================================================================

class TestMetadataExport:
    """Tests for exporting metadata to JSON files."""

    @pytest.mark.unit
    def test_export_song_metadata_to_json(self):
        """Test exporting song metadata to a JSON sidecar file."""
        from utils.metadatautils import export_metadata_to_json
        from model.song import Song
        import json

        song = Song(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_id="track123",
            isrc="USTEST123456",
            duration_ms=240000
        )

        with patch('builtins.open', mock_open()) as mock_file:
            result = export_metadata_to_json(song, "/path/to/song.mp3")

            assert result is True
            mock_file.assert_called_once_with("/path/to/song.json", 'w', encoding='utf-8')

    @pytest.mark.unit
    def test_export_playlist_metadata_to_json(self):
        """Test exporting entire playlist metadata to JSON."""
        from utils.metadatautils import export_playlist_metadata
        from model.song import Song
        from model.playlist import Playlist

        songs = [
            Song(name="Song 1", artist="Artist 1", track_id="t1"),
            Song(name="Song 2", artist="Artist 2", track_id="t2")
        ]
        playlist = Playlist(name="Test Playlist", songs=songs, url="https://spotify.com/playlist/test")

        with patch('builtins.open', mock_open()) as mock_file:
            result = export_playlist_metadata(playlist, "/download/path")

            assert result is True

    @pytest.mark.unit
    def test_import_metadata_from_json(self):
        """Test importing song metadata from a JSON file."""
        from utils.metadatautils import import_metadata_from_json
        import json

        json_content = json.dumps({
            'name': 'Test Song',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'track_id': 'track123',
            'isrc': 'USTEST123456'
        })

        with patch('builtins.open', mock_open(read_data=json_content)):
            with patch('os.path.exists', return_value=True):
                song = import_metadata_from_json("/path/to/song.json")

                assert song.name == 'Test Song'
                assert song.artist == 'Test Artist'
                assert song.track_id == 'track123'


# =============================================================================
# TESTS FOR BATCH METADATA OPERATIONS
# =============================================================================

class TestBatchMetadataOperations:
    """Tests for batch metadata processing operations."""

    @pytest.mark.unit
    def test_batch_embed_metadata(self):
        """Test embedding metadata for multiple files."""
        from utils.metadatautils import batch_embed_metadata
        from model.song import Song

        songs = [
            Song(name="Song 1", artist="Artist 1", track_id="t1"),
            Song(name="Song 2", artist="Artist 2", track_id="t2"),
            Song(name="Song 3", artist="Artist 3", track_id="t3")
        ]

        file_mappings = {
            "t1": "/path/to/song1.mp3",
            "t2": "/path/to/song2.mp3",
            "t3": "/path/to/song3.mp3"
        }

        with patch('utils.metadatautils.embed_metadata') as mock_embed:
            mock_embed.return_value = True

            results = batch_embed_metadata(songs, file_mappings)

            assert results['success'] == 3
            assert results['failed'] == 0
            assert mock_embed.call_count == 3

    @pytest.mark.unit
    @patch('utils.metadatautils.os.path.exists')
    @patch('utils.metadatautils.os.listdir')
    @patch('utils.metadatautils.verify_metadata')
    def test_batch_verify_metadata(self, mock_verify, mock_listdir, mock_exists):
        """Test verifying metadata for multiple files."""
        from utils.metadatautils import batch_verify_metadata
        from model.song import Song

        # Mock directory exists and return fake files that match track_ids
        mock_exists.return_value = True
        mock_listdir.return_value = ['track1.mp3', 'track2.mp3']

        # Create songs with track_ids that match the fake files
        songs = [
            Song(name="Song 1", artist="Artist 1", track_id="track1"),
            Song(name="Song 2", artist="Artist 2", track_id="track2")
        ]

        # Mock verify_metadata to return different results
        mock_verify.side_effect = [
            (True, []),
            (False, ['album', 'isrc'])
        ]

        results = batch_verify_metadata(songs, "/path/to/files")

        assert results['complete'] == 1
        assert results['incomplete'] == 1
        assert 'Song 2' in str(results['missing_fields'])
