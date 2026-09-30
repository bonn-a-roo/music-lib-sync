"""Tests for utils.fileutils - safe file names and track-id recognition."""
import os

import pytest

from utils.fileutils import (
    create_directory,
    sanitize_path_component,
    song_filename,
    track_id_from_filename,
)

TRACK_ID = '3ZbQb6icDF34PLQcHOYAkm'


class TestSanitizePathComponent:

    @pytest.mark.unit
    @pytest.mark.parametrize('name', [
        'Rock/Metal', 'What?', 'Night: Drive', 'Mix *2*', 'a\\b', 'x|y', '"quoted"', '<tag>',
    ])
    def test_result_is_a_single_legal_windows_component(self, name):
        result = sanitize_path_component(name)
        assert not any(c in result for c in '<>:"/\\|?*')
        assert result and result == result.strip(' .')

    @pytest.mark.unit
    def test_slash_in_title_does_not_create_subdirectory(self, tmp_path):
        target = tmp_path / sanitize_path_component('Tombo in 7/4')
        target.mkdir()
        assert [p.name for p in tmp_path.iterdir()] == [target.name]

    @pytest.mark.unit
    def test_unicode_is_preserved(self):
        assert sanitize_path_component('Motörhead - Łona 宇多田') == 'Motörhead - Łona 宇多田'

    @pytest.mark.unit
    @pytest.mark.parametrize('name', ['CON', 'nul', 'COM1', 'lpt9', 'aux.txt'])
    def test_reserved_device_names_are_prefixed(self, name):
        assert sanitize_path_component(name).startswith('_')

    @pytest.mark.unit
    @pytest.mark.parametrize('name', ['', None, '   ', '...', '?'])
    def test_never_returns_empty(self, name):
        assert sanitize_path_component(name)

    @pytest.mark.unit
    def test_trailing_dots_and_spaces_removed(self):
        assert sanitize_path_component('Best of 2020. ') == 'Best of 2020'

    @pytest.mark.unit
    def test_truncates_to_max_len(self):
        assert len(sanitize_path_component('a' * 500, max_len=50)) <= 50


class TestSongFilename:

    @pytest.mark.unit
    @pytest.mark.parametrize('artist,name', [
        ('Elliott Smith', 'Kiwi Maddog 20/20 (Version 2)'),
        ('AC/DC', 'Back In Black'),
        ('Martha Scanlan', "I'll Think About It / I Could've Loved You"),
        ('Motörhead', 'Iron Horse / Born to Lose'),
        ('Artist', 'Song %(title)s'),
    ])
    def test_flat_file_that_dedupe_recognises(self, artist, name):
        filename = song_filename(artist, name, TRACK_ID)
        assert os.path.basename(filename) == filename
        assert track_id_from_filename(filename) == TRACK_ID

    @pytest.mark.unit
    def test_long_titles_keep_the_track_id_suffix(self):
        filename = song_filename('Grateful Dead', 'Loser - Live at Barton Hall ' * 20, TRACK_ID)
        assert len(filename) <= 200
        assert filename.endswith(f' [{TRACK_ID}].mp3')

    @pytest.mark.unit
    def test_missing_artist_or_title_still_produces_valid_name(self):
        filename = song_filename(None, None, TRACK_ID)
        assert track_id_from_filename(filename) == TRACK_ID
        assert 'None' not in filename


class TestTrackIdFromFilename:

    @pytest.mark.unit
    @pytest.mark.parametrize('ext', ['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])
    def test_extracts_id_across_supported_formats(self, ext):
        assert track_id_from_filename(f'Artist - Song [{TRACK_ID}].{ext}') == TRACK_ID

    @pytest.mark.unit
    def test_extension_is_case_insensitive(self):
        assert track_id_from_filename(f'Artist - Song [{TRACK_ID}].MP3') == TRACK_ID

    @pytest.mark.unit
    @pytest.mark.parametrize('filename', [
        f'Artist - Song [{TRACK_ID}].mp4.part',
        f'Artist - Song [{TRACK_ID}].temp.mp3.ytdl',
        'Artist - Song.mp3',
        f'Artist - Song [{TRACK_ID}].mp4',
    ])
    def test_partial_or_other_files_are_not_tracks(self, filename):
        assert track_id_from_filename(filename) is None


class TestCreateDirectory:

    @pytest.mark.unit
    def test_creates_nested_and_tolerates_existing(self, tmp_path):
        target = tmp_path / 'a' / 'b'
        create_directory(str(target))
        create_directory(str(target))
        assert target.is_dir()
