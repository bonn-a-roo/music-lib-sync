"""
Tests for song metadata functionality.

These tests cover:
1. Extended Song model with full metadata fields
2. Native metadata embedding and reading across supported audio formats
3. Duration, art caching, and metadata sidecar export
"""
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from mutagen.id3 import ID3, TIT2, TRCK, TPOS
from model.song import Song
from utils import metadatautils
import pytest


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
# TESTS FOR METADATA EMBEDDING IN MP3 FILES
# =============================================================================



@pytest.fixture
def minimal_mp3(tmp_path):
    path = tmp_path / 'silent.mp3'
    # Ten complete MPEG-1 Layer III frames: 128 kbps, 44.1 kHz.
    path.write_bytes((b'\xff\xfb\x90\x64' + bytes(413)) * 10)
    return path


@pytest.mark.unit
def test_real_mp3_roundtrip_year_and_duration(minimal_mp3):
    song = Song(name='中文 Zażółć', artist='Москва', album='Album',
                release_date='2023-06-15', track_number=5, disc_number=2,
                isrc='USTEST123456')
    assert not metadatautils.has_basic_tags(str(minimal_mp3))
    assert metadatautils.read_duration(str(minimal_mp3)) == pytest.approx(4170 * 8 / 128000)
    assert metadatautils.embed_metadata(str(minimal_mp3), song)
    assert ID3(minimal_mp3).version == (2, 3, 0)
    metadata = metadatautils.read_metadata(str(minimal_mp3))
    assert metadata['title'] == song.name
    assert metadata['artist'] == song.artist
    assert metadata['date'].startswith('2023')
    assert metadata['track_number'] == 5 and metadata['disc_number'] == 2
    assert metadatautils.has_basic_tags(str(minimal_mp3))
    assert metadatautils.verify_metadata(str(minimal_mp3), song) == (True, [])


@pytest.mark.unit
def test_bad_numeric_frames_do_not_discard_other_metadata(minimal_mp3):
    song = Song(name='Kept', artist='Artist', album='Album', release_date='1999')
    assert metadatautils.embed_metadata(str(minimal_mp3), song)
    tags = ID3(minimal_mp3)
    tags.add(TRCK(encoding=3, text='not a number'))
    tags.add(TPOS(encoding=3, text='unknown'))
    tags.save(minimal_mp3)
    metadata = metadatautils.read_metadata(str(minimal_mp3))
    assert metadata['title'] == 'Kept'
    assert metadata['date'] == '1999'
    assert 'track_number' not in metadata and 'disc_number' not in metadata


@pytest.mark.unit
@pytest.mark.parametrize('data,mime', [
    (b'\x89PNG\r\n\x1a\nimage', 'image/png'),
    (b'\xff\xd8\xffimage', 'image/jpeg'),
])
def test_album_art_cached_across_threads_and_mime_sniffed(tmp_path, monkeypatch, data, mime):
    metadatautils._art_cache.clear()
    calls = []
    def fetch(url, timeout):
        calls.append((url, timeout))
        return SimpleNamespace(content=data, headers={'Content-Type': 'image/jpeg'},
                               raise_for_status=lambda: None)
    monkeypatch.setattr(metadatautils.requests, 'get', fetch)
    paths = [tmp_path / f'{index}.mp3' for index in range(8)]
    for path in paths:
        path.write_bytes((b'\xff\xfb\x90\x64' + bytes(413)) * 10)
    song = Song(name='Album song', artist='Artist', album_art_url='https://art.invalid/album')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda path: metadatautils.embed_metadata(str(path), song, True), paths))
    assert results == [True] * 8
    assert calls == [('https://art.invalid/album', 10)]
    for path in paths:
        art = ID3(path).getall('APIC')[0]
        assert art.mime == mime and art.data == data


@pytest.mark.unit
def test_album_art_failure_does_not_fail_tags(minimal_mp3, monkeypatch):
    def fail(*args, **kwargs):
        raise metadatautils.requests.Timeout('offline')
    monkeypatch.setattr(metadatautils.requests, 'get', fail)
    song = Song(name='Kept', artist='Artist', album_art_url='https://art.invalid/failure')
    assert metadatautils.embed_metadata(str(minimal_mp3), song, True)
    assert metadatautils.read_metadata(str(minimal_mp3))['title'] == 'Kept'


@pytest.mark.unit
def test_art_cache_is_bounded(monkeypatch):
    metadatautils._art_cache.clear()
    monkeypatch.setattr(metadatautils.requests, 'get', lambda *args, **kwargs: SimpleNamespace(
        content=b'\xff\xd8\xffimage', headers={}, raise_for_status=lambda: None))
    for index in range(70):
        metadatautils._get_album_art(f'https://art.invalid/{index}')
    assert len(metadatautils._art_cache) == 64
    assert 'https://art.invalid/0' not in metadatautils._art_cache
    assert 'https://art.invalid/69' in metadatautils._art_cache


@pytest.mark.unit
def test_wav_native_id3_roundtrip(tmp_path):
    path = tmp_path / 'silent.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(16000))
    song = Song(name='WAV title', artist='Artist', release_date='2001')
    assert metadatautils.read_duration(str(path)) == pytest.approx(1.0)
    assert not metadatautils.has_basic_tags(str(path))
    assert metadatautils.embed_metadata(str(path), song)
    assert metadatautils.has_basic_tags(str(path))
    assert metadatautils.read_metadata(str(path))['date'] == '2001'


@pytest.mark.unit
def test_missing_and_corrupt_audio_return_safe_results(tmp_path):
    song = Song(name='Title', artist='Artist')
    missing = tmp_path / 'missing.mp3'
    corrupt = tmp_path / 'corrupt.mp3'
    corrupt.write_bytes(b'not audio')
    for path in (missing, corrupt):
        assert metadatautils.read_duration(str(path)) is None
        assert not metadatautils.has_basic_tags(str(path))
        assert not metadatautils.embed_metadata(str(path), song)
        assert metadatautils.read_metadata(str(path)) == {}


@pytest.mark.unit
def test_basic_tags_requires_both_frames(minimal_mp3):
    tags = ID3()
    tags.add(TIT2(encoding=3, text='Title only'))
    tags.save(minimal_mp3)
    assert not metadatautils.has_basic_tags(str(minimal_mp3))


@pytest.mark.unit
def test_json_sidecar_roundtrip_uses_actual_extension(tmp_path):
    song = Song(name='中文', artist='Artist', track_id='track123', album='Album', isrc='ISRC')
    audio_path = tmp_path / 'directory.mp3.MP3'
    assert metadatautils.export_metadata_to_json(song, str(audio_path))
    sidecar = tmp_path / 'directory.mp3.json'
    assert json.loads(sidecar.read_text(encoding='utf-8'))['name'] == '中文'
    restored = metadatautils.import_metadata_from_json(str(sidecar))
    assert restored.name == song.name and restored.track_id == song.track_id
    assert restored.isrc == 'ISRC'


@pytest.mark.unit
def test_playlist_export_sanitizes_reserved_component(tmp_path):
    from model.playlist import Playlist
    playlist = Playlist(name='CON', songs=[Song(name='Title', artist='Artist')], url='playlist')
    assert metadatautils.export_playlist_metadata(playlist, str(tmp_path))
    assert json.loads((tmp_path / '_CON.json').read_text(encoding='utf-8'))['name'] == 'CON'


@pytest.mark.unit
def test_batch_embed_missing_mapping_and_verify_real_files(minimal_mp3):
    song = Song(name='Title', artist='Artist', track_id='track1')
    missing = Song(name='Missing', artist='Artist', track_id='track2')
    path = minimal_mp3.with_name('Title [track1].mp3')
    minimal_mp3.rename(path)
    result = metadatautils.batch_embed_metadata([song, missing], {'track1': str(path)})
    assert result['success'] == 1 and result['failed'] == 1
    verified = metadatautils.batch_verify_metadata([song, missing], str(path.parent))
    assert verified['complete'] == 1 and verified['incomplete'] == 1
    assert verified['missing_fields']['Missing'] == ['File not found']


@pytest.mark.unit
@pytest.mark.parametrize('extension', ['flac', 'm4a', 'opus', 'ogg'])
def test_native_audio_roundtrip_with_art(tmp_path, monkeypatch, extension):
    import shutil
    import subprocess
    import mutagen
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg external runtime requirement not installed')
    path = tmp_path / f'silent.{extension}'
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'anullsrc=r=44100:cl=stereo', '-t', '0.5', str(path)],
                   check=True, capture_output=True, timeout=30)
    image = b'\x89PNG\r\n\x1a\nimage'
    monkeypatch.setattr(metadatautils.requests, 'get', lambda *args, **kwargs: SimpleNamespace(
        content=image, headers={}, raise_for_status=lambda: None))
    song = Song(name='中文', artist='Москва', album='Album', track_number=4, disc_number=2,
                release_date='2001-02-03', isrc='USTEST123456',
                album_art_url=f'https://art.invalid/{extension}')
    assert not metadatautils.has_basic_tags(str(path))
    assert metadatautils.embed_metadata(str(path), song, True)
    assert metadatautils.has_basic_tags(str(path))
    data = metadatautils.read_metadata(str(path))
    assert data['title'] == song.name and data['artist'] == song.artist
    assert data['date'] == '2001-02-03' and data['isrc'] == song.isrc
    assert data['track_number'] == 4 and data['disc_number'] == 2
    assert 0.45 < metadatautils.read_duration(str(path)) < 0.7
    audio = mutagen.File(path)
    if extension == 'flac':
        assert audio.pictures[0].mime == 'image/png' and audio.pictures[0].data == image
    elif extension == 'm4a':
        assert bytes(audio.tags['covr'][0]) == image
        assert audio.tags['covr'][0].imageformat == metadatautils.MP4Cover.FORMAT_PNG
    else:
        picture = metadatautils.Picture(metadatautils.base64.b64decode(
            audio.tags['metadata_block_picture'][0]))
        assert picture.mime == 'image/png' and picture.data == image
