from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from spotipy import SpotifyException

from model.library import LibraryFetchError, SpotifyLibrary
from model.sync_result import SyncResult
from utils import repair

pytestmark = pytest.mark.unit


def track(id='abc', **kwargs):
    return {'id': id, 'name': id, 'artists': [{'name': 'Artist'}], 'duration_ms': 180000, **kwargs}


def page(items, **kwargs):
    return {'items': items, 'total': len(items), 'next': None, **kwargs}


def playlist(id, name='Mix', owner='me', collaborative=False):
    return {'id': id, 'name': name, 'owner': {'id': owner}, 'collaborative': collaborative, 'external_urls': {'spotify': f'https://spotify.com/playlist/{id}'}}


class FakeDownloader:
    def __init__(self):
        self.calls = []
        self.cancelled = False

    def is_cancelled(self):
        return self.cancelled

    def download(self, songs, directory, progress_callback=None):
        self.calls.append((songs, directory))
        result = SyncResult()
        if progress_callback:
            progress_callback(0, len(songs), '')
        for done, song in enumerate(songs, 1):
            result.add_success()
            if progress_callback:
                progress_callback(done, len(songs), song.name)
        return result


@pytest.fixture
def auth():
    client = Mock()
    client.current_user.return_value = {'id': 'me'}
    client.current_user_saved_tracks.return_value = page([])
    client.current_user_playlists.return_value = page([])
    client.playlist_items.return_value = page([])
    return client


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr('model.library._sleep', lambda seconds: None)
    monkeypatch.setattr('model.library.configutils.get_download_path', lambda: str(tmp_path))


def test_429_retry_then_success(auth, monkeypatch):
    waits = []
    monkeypatch.setattr('model.library._sleep', waits.append)
    auth.current_user_saved_tracks.side_effect = [SpotifyException(429, -1, 'busy', headers={'Retry-After': '0.2'}), page([{'track': track()}])]
    assert SpotifyLibrary(auth).get_saved_tracks()[0].track_id == 'abc'
    assert auth.current_user_saved_tracks.call_count == 2
    assert sum(waits) == pytest.approx(0.2)


@pytest.mark.parametrize('error', [SpotifyException(503, -1, 'busy'), requests.Timeout('timeout'), SpotifyException(403, -1, 'forbidden')])
def test_fetch_failure_never_returns_partial(auth, error):
    auth.current_user_saved_tracks.side_effect = [page([{'track': track()}], total=2, next='next')] + [error] * 5
    with pytest.raises(LibraryFetchError):
        SpotifyLibrary(auth).get_saved_tracks()


def test_quota_retries_at_most_once(auth):
    auth.current_user_saved_tracks.side_effect = SpotifyException(429, -1, 'quota', reason='QUOTA_EXCEEDED')
    with pytest.raises(LibraryFetchError, match='quota exceeded'):
        SpotifyLibrary(auth).get_saved_tracks()
    assert auth.current_user_saved_tracks.call_count == 2


@pytest.mark.parametrize('later', [False, True])
def test_playlist_failure_recorded_not_empty_success(auth, later):
    auth.current_user_playlists.return_value = page([playlist('one')])
    auth.playlist_items.side_effect = ([page([{'track': track()}], total=2, next='next')] if later else []) + [SpotifyException(503, -1, 'busy')] * 5
    downloader = FakeDownloader()
    result = SpotifyLibrary(auth).sync_playlists(downloader)
    assert result.failure_count == 1
    assert result.errors[0].item_name == 'Mix'
    assert downloader.calls == []


def test_ownership_new_key_and_nullable_tracks(auth):
    auth.current_user_playlists.return_value = page([playlist('owned'), playlist('collab', owner='other', collaborative=True), playlist('followed', 'Public', owner='other')])
    auth.playlist_items.return_value = page([{'item': track('new')}, {'track': track('old')}, {'track': None}, {'track': track('local', is_local=True)}, {'track': {'name': 'missing id'}}])
    library = SpotifyLibrary(auth)
    playlists = library.get_playlists()
    assert [[song.track_id for song in p.songs] for p in playlists] == [['new', 'old'], ['new', 'old'], []]
    assert {call.args[0] for call in auth.playlist_items.call_args_list} == {'owned', 'collab'}
    result = library.sync_playlists(FakeDownloader())
    assert any('Public' in note and 'skipped' in note for note in result.notes)
    assert auth.current_user.call_count == 1


def test_saved_unavailable_single_note_and_metadata(auth):
    metadata = track(album={'name': 'Album', 'images': [{'height': 640, 'url': 'cover'}]}, external_ids={'isrc': 'ISRC'})
    auth.current_user_saved_tracks.return_value = page([{'track': metadata}, {'track': None}, {'track': track('local', is_local=True)}, {'track': {'name': 'no id'}}])
    library = SpotifyLibrary(auth)
    song = library.get_saved_tracks()[0]
    assert (song.album, song.album_art_url, song.isrc, song.duration_ms) == ('Album', 'cover', 'ISRC', 180000)
    result = library.sync_songs(FakeDownloader())
    assert len(result.notes) == 1
    assert '3' in result.notes[0]
    assert result.success_count == 1


def test_safe_colliding_directories_progress_and_skips(auth, tmp_path):
    auth.current_user_playlists.return_value = page([playlist('abcdef1', 'Rock/Metal'), playlist('ghijkl2', 'rock\\metal'), playlist('what', 'What? (best of)')])
    auth.playlist_items.return_value = page([{'track': track('old')}, {'track': track('new')}])
    existing = tmp_path / 'playlists' / 'Rock_Metal [abcdef]'
    existing.mkdir(parents=True)
    (existing / 'Artist - old [old].mp3').write_bytes(b'existing')
    downloader = FakeDownloader()
    events = []
    result = SpotifyLibrary(auth).sync_playlists(downloader, lambda *args: events.append(args))
    assert [Path(directory).name for _, directory in downloader.calls] == ['Rock_Metal [abcdef]', 'rock_metal [ghijkl]', 'What_ (best of)']
    assert result.skipped_count == 1
    assert result.success_count == 5
    assert events[0] == (0, 5, '')
    assert sum(event[0] == 0 for event in events) == 1
    assert [event[0] for event in events] == [0, 1, 2, 3, 4, 5]
    assert all(event[1] == 5 for event in events)


def test_nested_download_flattened_not_requeued(auth, tmp_path):
    directory = tmp_path / 'my_songs'
    nested = directory / 'Artist - Title 20'
    nested.mkdir(parents=True)
    (nested / '20 [abc].mp3').write_bytes(b'audio')
    auth.current_user_saved_tracks.return_value = page([{'track': track()}])
    downloader = FakeDownloader()
    result = SpotifyLibrary(auth).sync_songs(downloader)
    assert result.skipped_count == 1
    assert downloader.calls == []
    assert (directory / 'Artist - Title 20_20 [abc].mp3').read_bytes() == b'audio'
    assert repair.flatten_nested_tracks(directory) == 0
    assert not nested.exists()


def test_flatten_preserves_duplicates_rejected_and_other_files(tmp_path):
    (tmp_path / 'top [abc].mp3').write_bytes(b'top')
    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'duplicate [abc].mp3').write_bytes(b'duplicate')
    (nested / 'new [new].flac').write_bytes(b'new')
    (nested / 'keep.txt').write_text('keep')
    rejected = tmp_path / '_rejected'
    rejected.mkdir()
    (rejected / 'bad [bad].mp3').write_bytes(b'bad')
    assert repair.flatten_nested_tracks(tmp_path) == 1
    assert (nested / 'duplicate [abc].mp3').read_bytes() == b'duplicate'
    assert (nested / 'keep.txt').exists()
    assert (rejected / 'bad [bad].mp3').exists()
    assert (tmp_path / 'nested_new [new].flac').exists()


def test_playlist_mkdir_failure_continues(auth, monkeypatch):
    auth.current_user_playlists.return_value = page([playlist('bad', 'Bad'), playlist('good', 'Good')])
    auth.playlist_items.return_value = page([{'track': track()}])
    import os
    original = os.makedirs
    def mkdir(path, **kwargs):
        if Path(path).name == 'Bad':
            raise OSError('denied')
        return original(path, **kwargs)
    monkeypatch.setattr('model.library.os.makedirs', mkdir)
    result = SpotifyLibrary(auth).sync_playlists(FakeDownloader())
    assert result.failure_count == 1
    assert result.success_count == 1


def test_cancel_during_retry_stops_promptly(auth, monkeypatch):
    downloader = FakeDownloader()
    auth.current_user_saved_tracks.side_effect = requests.ConnectionError('offline')
    monkeypatch.setattr('model.library._sleep', lambda seconds: setattr(downloader, 'cancelled', True))
    result = SpotifyLibrary(auth).sync_songs(downloader)
    assert result.cancelled
    assert result.failure_count == 0
    assert auth.current_user_saved_tracks.call_count == 1


def test_cancel_between_playlist_downloads(auth):
    auth.current_user_playlists.return_value = page([playlist('a', 'A'), playlist('b', 'B')])
    auth.playlist_items.return_value = page([{'track': track()}])
    downloader = FakeDownloader()
    result = SpotifyLibrary(auth).sync_playlists(downloader, lambda done, total, name: setattr(downloader, 'cancelled', done > 0))
    assert result.cancelled
    assert len(downloader.calls) == 1


def test_repair_quarantines_tags_and_preserves_unknown(auth, tmp_path, monkeypatch):
    ids = ['preview', 'fine', 'untagged', 'unreadable']
    auth.current_user_saved_tracks.return_value = page([{'track': track(id)} for id in ids])
    directory = tmp_path / 'my_songs'
    directory.mkdir()
    for id in ids + ['unknown']:
        (directory / f'{id} [{id}].mp3').write_bytes(id.encode())
    monkeypatch.setattr('model.library.metadatautils.read_duration', lambda path: None if 'unreadable' in path else 30 if 'preview' in path else 180)
    monkeypatch.setattr('model.library.metadatautils.has_basic_tags', lambda path: 'untagged' not in path)
    tagged = []
    def embed(path, song, embed_art=False):
        tagged.append((song.track_id, embed_art))
        return True
    monkeypatch.setattr('model.library.metadatautils.embed_metadata', embed)
    events = []
    result = SpotifyLibrary(auth).repair_library(lambda *args: events.append(args))
    assert result.success_count == 3
    assert result.skipped_count == 1
    assert result.failure_count == 0
    assert tagged == [('untagged', True)]
    assert (directory / '_rejected' / 'preview [preview].mp3').read_bytes() == b'preview'
    assert (directory / '_rejected' / 'unreadable [unreadable].mp3').exists()
    assert (directory / 'fine [fine].mp3').exists()
    assert (directory / 'unknown [unknown].mp3').read_bytes() == b'unknown'
    assert events[-1][0:2] == (4, 4)
    assert any('preview' in note for note in result.notes)


def test_quarantine_never_overwrites(tmp_path):
    source = tmp_path / 'x [abc].mp3'
    source.write_bytes(b'first')
    first = repair.quarantine(source, tmp_path)
    source.write_bytes(b'second')
    second = repair.quarantine(source, tmp_path)
    assert first != second
    assert Path(first).read_bytes() == b'first'
    assert Path(second).read_bytes() == b'second'


def test_repair_single_file_error_continues(auth, tmp_path, monkeypatch):
    auth.current_user_saved_tracks.return_value = page([{'track': track('bad')}, {'track': track('good')}])
    directory = tmp_path / 'my_songs'
    directory.mkdir()
    for id in ('bad', 'good'):
        (directory / f'{id} [{id}].wav').write_bytes(b'original')
    monkeypatch.setattr('model.library.metadatautils.read_duration', lambda path: 180)
    monkeypatch.setattr('model.library.metadatautils.has_basic_tags', lambda path: False)
    monkeypatch.setattr('model.library.metadatautils.embed_metadata', lambda path, song, embed_art=False: song.track_id == 'good')
    result = SpotifyLibrary(auth).repair_library()
    assert result.failure_count == 1
    assert result.success_count == 1
    assert result.errors[0].item_name == 'bad [bad].wav'


def test_repair_cancel_between_files(auth, tmp_path, monkeypatch):
    auth.current_user_saved_tracks.return_value = page([{'track': track('a')}, {'track': track('b')}])
    directory = tmp_path / 'my_songs'
    directory.mkdir()
    for id in ('a', 'b'):
        (directory / f'{id} [{id}].m4a').write_bytes(b'original')
    monkeypatch.setattr('model.library.metadatautils.read_duration', lambda path: 180)
    monkeypatch.setattr('model.library.metadatautils.has_basic_tags', lambda path: True)
    cancelled = [False]
    def progress(done, total, name):
        cancelled[0] = done > 0
    result = SpotifyLibrary(auth).repair_library(progress, lambda: cancelled[0])
    assert result.cancelled
    assert result.skipped_count == 1
    assert (directory / 'b [b].m4a').read_bytes() == b'original'


def test_downloaded_ids_only_top_level_regular_audio_files(tmp_path, auth):
    for name in ('a [abc].MP3', 'b [flac].flac', 'c [opus].opus', 'd [ogg].ogg', 'e [wav].wav', 'f [m4a].m4a', 'partial [partial].mp3.part'):
        (tmp_path / name).write_bytes(b'x')
    (tmp_path / 'directory [dir].mp3').mkdir()
    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'nested [nested].mp3').write_bytes(b'x')
    assert SpotifyLibrary(auth)._get_downloaded_track_ids(tmp_path) == {'abc', 'flac', 'opus', 'ogg', 'wav', 'm4a'}


def test_saved_pagination_uses_next_and_total(auth):
    auth.current_user_saved_tracks.side_effect = [page([{'track': track('first')}], total=2, next='next'), page([{'track': track('second')}], total=2)]
    songs = SpotifyLibrary(auth).get_saved_tracks()
    assert [song.track_id for song in songs] == ['first', 'second']
    assert [call.kwargs['offset'] for call in auth.current_user_saved_tracks.call_args_list] == [0, 1]


def test_cancel_before_next_spotify_page(auth):
    downloader = FakeDownloader()
    def first_page(**kwargs):
        downloader.cancelled = True
        return page([{'track': track()}], total=2, next='next')
    auth.current_user_saved_tracks.side_effect = first_page
    result = SpotifyLibrary(auth).sync_songs(downloader)
    assert result.cancelled
    assert result.failure_count == 0
    assert auth.current_user_saved_tracks.call_count == 1


def test_browser_sidebar_precedes_tracks_and_uses_full_collision_set(auth, tmp_path):
    from model.library_state import CollectionKey
    auth.current_user_playlists.return_value = page([playlist('first1'), playlist('second2')])
    browser = SpotifyLibrary(auth).browse_collections(tmp_path, selected_key=CollectionKey('me', 'second2'))
    sidebar = [next(browser) for _ in range(3)]
    assert [entry.metadata for entry in sidebar] == ['not_loaded'] * 3
    auth.current_user_saved_tracks.assert_not_called()
    auth.playlist_items.assert_not_called()
    assert [Path(entry.destination).name for entry in sidebar[1:]] == ['Mix [first1]', 'Mix [second]']
    loaded = list(browser)
    assert [entry.key.collection_id for entry in loaded] == ['saved', 'second2', 'first1']
    assert not tmp_path.joinpath('my_songs').exists()


def test_browser_unique_counts_and_unavailable_rows(auth, tmp_path):
    auth.current_user_saved_tracks.return_value = page([{'track': track('one')}, {'track': track('one')}, {'track': track('two')}, {'track': None}])
    destination = tmp_path / 'my_songs'
    destination.mkdir()
    (destination / 'one [one].flac').write_bytes(b'audio')
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    snapshot = list(SpotifyLibrary(auth).browse_collections(tmp_path))[-1]
    assert [row.track_id for row in snapshot.tracks] == ['one', 'one', 'two']
    assert (snapshot.eligible_count, snapshot.downloaded_count, snapshot.missing_count, snapshot.skipped_count) == (2, 1, 1, 1)
    assert snapshot.coverage == 'partial'
    assert before == {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}


def test_browser_removed_quarantined_elsewhere_and_temporary(auth, tmp_path):
    auth.current_user_saved_tracks.return_value = page([{'track': track(id)} for id in ('removed', 'bad', 'else', 'temp', 'unsupported')])
    rejected = tmp_path / 'my_songs' / '_rejected'
    rejected.mkdir(parents=True)
    (rejected / 'bad [bad].mp3').write_bytes(b'bad')
    elsewhere = tmp_path / 'playlists' / 'Old name'
    elsewhere.mkdir(parents=True)
    (elsewhere / 'else [else].opus').write_bytes(b'audio')
    (rejected.parent / 'temp [temp].mp3.part').write_bytes(b'partial')
    (rejected.parent / 'unsupported [unsupported].aac').write_bytes(b'audio')
    removed = rejected.parent / 'removed [removed].mp3'
    removed.write_bytes(b'audio')
    library = SpotifyLibrary(auth)
    assert list(library.browse_collections(tmp_path))[-1].downloaded_count == 1
    removed.unlink()
    snapshot = list(library.browse_collections(tmp_path))[-1]
    assert [row.presence for row in snapshot.tracks] == ['missing', 'quarantined', 'missing', 'missing', 'missing']
    assert snapshot.tracks[2].elsewhere_path == str(elsewhere / 'else [else].opus')
    assert snapshot.downloaded_count == 0
    assert (rejected / 'bad [bad].mp3').exists()


def test_browser_empty_restricted_and_fetch_error_not_synced(auth, tmp_path):
    auth.current_user_playlists.return_value = page([playlist('restricted', owner='other'), playlist('broken')])
    auth.playlist_items.side_effect = SpotifyException(403, -1, 'forbidden')
    snapshots = list(SpotifyLibrary(auth).browse_collections(tmp_path))
    assert next(entry for entry in snapshots if entry.key.collection_id == 'restricted').status == 'Restricted'
    assert next(entry for entry in snapshots if entry.key.collection_id == 'saved' and entry.metadata == 'ready').status == 'Empty'
    broken = snapshots[-1]
    assert (broken.metadata, broken.coverage, broken.status) == ('error', 'unknown', 'Error')


def test_browser_scan_error_and_stale_snapshot_are_unknown(auth, tmp_path, monkeypatch):
    from dataclasses import replace
    auth.current_user_saved_tracks.return_value = page([{'track': track()}])
    def inaccessible(root, onerror, followlinks):
        onerror(PermissionError('inaccessible'))
        return iter(())
    monkeypatch.setattr('model.library_state.os.walk', inaccessible)
    snapshot = list(SpotifyLibrary(auth).browse_collections(tmp_path))[-1]
    assert snapshot.tracks[0].presence == 'unknown'
    assert snapshot.coverage == 'unknown'
    assert snapshot.status == 'Error'
    assert snapshot.error == 'inaccessible'
    stale = replace(snapshot, scan_complete=True, stale=True)
    assert stale.coverage == 'unknown'


def test_worker_events_require_real_success_and_reject_obsolete_scope(tmp_path):
    from model.library_state import CollectionKey, WorkerEvent
    key = CollectionKey('me', 'saved')
    with pytest.raises(ValueError, match='existing final file'):
        WorkerEvent('new', key, 'success', track_id='abc', final_path=str(tmp_path / 'absent.mp3'))
    final = tmp_path / 'audio.mp3'
    final.write_bytes(b'audio')
    event = WorkerEvent('new', key, 'success', track_id='abc', final_path=str(final))
    assert event.belongs_to('new', key)
    assert not event.belongs_to('old', key)
    assert not event.belongs_to('new', CollectionKey('other', 'saved'))
    with pytest.raises(ValueError, match='Failure requires'):
        WorkerEvent('new', key, 'failure')


def test_browser_playlist_unavailable_count_is_separate_from_coverage(auth, tmp_path):
    auth.current_user_playlists.return_value = page([playlist('owned')])
    auth.playlist_items.return_value = page([{'track': track('one')}, {'track': None}, {'track': track('local', is_local=True)}])
    snapshot = list(SpotifyLibrary(auth).browse_collections(tmp_path))[-1]
    assert (snapshot.eligible_count, snapshot.missing_count, snapshot.skipped_count) == (1, 1, 2)
    assert snapshot.status == 'Not downloaded'


def test_immutable_snapshot_loading_and_stale_cannot_claim_synced():
    from dataclasses import FrozenInstanceError, replace
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot
    row = TrackSnapshot('one', 'One', 'Artist', None, None, 'downloaded', 'file.mp3')
    snapshot = CollectionSnapshot(CollectionKey('me', 'saved'), 'Saved tracks', 'destination', tracks=[row], scan_complete=True)
    assert snapshot.status == 'Synced'
    assert isinstance(snapshot.tracks, tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.stale = True
    assert replace(snapshot, stale=True).status == 'Unknown'
    assert replace(snapshot, metadata='loading').status == 'Loading'
    assert replace(snapshot, metadata='error').coverage == 'unknown'
    assert replace(snapshot, operation='downloading').status == 'Downloading'
    assert replace(snapshot, operation='cancelling').status == 'Cancelling'
    assert replace(snapshot, outcome='failed').status == 'Failed'
    assert replace(snapshot, operation='downloading', metadata='restricted').status == 'Restricted'
    assert replace(snapshot, error='Storage unavailable').status == 'Error'
