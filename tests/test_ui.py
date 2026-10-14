import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QThread
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QMessageBox
from ui import uimanager as ui
from model.sync_result import SyncResult

app = QApplication.instance() or QApplication([])
pytestmark = pytest.mark.unit


@pytest.fixture
def environment(monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: errors.append(args) or QMessageBox.Close)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(ui.configutils, 'get_cookies_file', lambda: '')
    downloader = SimpleNamespace(preflight=Mock(return_value=[]), cancel=Mock(), log_callback=None)
    monkeypatch.setattr(ui, 'YoutubeDownloader', lambda **kwargs: downloader)
    return errors, downloader


def pump_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert predicate()


def test_worker_exception_restores_window(environment):
    errors, downloader = environment
    library = SimpleNamespace(sync_songs=Mock(side_effect=OSError('unsafe playlist path')))
    window = ui.SyncWindow(SimpleNamespace(library=library))
    window.show()
    window.sync_songs_button.click()
    pump_until(lambda: bool(errors))
    assert 'unsafe playlist path' in errors[0][2]
    assert all(button.isEnabled() for button in window._buttons)
    assert window.progress_bar.isHidden() and window.cancel_button.isHidden()
    assert window.sync_thread.wait(1000)
    window.close()


def test_go_uses_current_item_data(environment, monkeypatch):
    users = [SimpleNamespace(get_id=lambda: 'id1', get_name=lambda: 'Alice'),
             SimpleNamespace(get_id=lambda: 'id3', get_name=lambda: 'Bob (the Builder)')]
    manager = SimpleNamespace(get_users=lambda: users, selected=None)
    manager.set_session_id = lambda value: setattr(manager, 'selected', next(u for u in users if u.get_id() == value))
    manager.get_selected_user = lambda: manager.selected
    monkeypatch.setattr(ui, 'SessionManager', lambda: manager)
    window = ui.MainWindow()
    opened = []
    monkeypatch.setattr(window, 'open_library_window', lambda: opened.append(manager.selected))
    window.user_selection.setCurrentIndex(1)
    assert opened == []
    assert window.user_selection.currentText() == 'Bob (the Builder) (id3)'
    window.sync_button.click()
    assert opened == [users[1]]
    window.close()


def test_preflight_aborts_before_start(environment):
    errors, downloader = environment
    downloader.preflight.return_value = ['Missing ffmpeg', 'Missing node']
    library = SimpleNamespace(sync_songs=Mock())
    window = ui.SyncWindow(SimpleNamespace(library=library))
    window.sync_songs()
    assert window.sync_thread is None
    library.sync_songs.assert_not_called()
    assert 'Missing ffmpeg\nMissing node' in errors[0][2]
    assert window.sync_songs_button.isEnabled()
    window.close()


def test_close_cancels_and_waits_actual_worker(environment):
    errors, downloader = environment
    entered = threading.Event()
    cancelled = threading.Event()
    downloader.cancel.side_effect = cancelled.set
    def sync(**kwargs):
        entered.set()
        assert cancelled.wait(2)
        return SyncResult()
    window = ui.SyncWindow(SimpleNamespace(library=SimpleNamespace(sync_songs=sync)))
    window.sync_songs()
    assert entered.wait(1)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert not window.sync_thread.isRunning()
    assert cancelled.is_set()
    app.processEvents()
    window.close()


def test_repair_runs_and_cancels(environment):
    entered = threading.Event()
    cancelled = threading.Event()
    def repair(progress_callback, cancel_check, download_path=None):
        progress_callback(0, 1, '')
        entered.set()
        deadline = time.monotonic() + 2
        while not cancel_check() and time.monotonic() < deadline:
            time.sleep(.005)
        if cancel_check():
            cancelled.set()
        result = SyncResult()
        result.cancelled = True
        return result
    window = ui.SyncWindow(SimpleNamespace(library=SimpleNamespace(repair_library=repair)))
    window.repair_button.click()
    assert entered.wait(1)
    assert window.sync_thread.kind == 'repair'
    window.cancel_button.click()
    pump_until(lambda: cancelled.is_set())
    assert window.sync_thread.wait(1000)
    app.processEvents()
    window.close()


def test_eta_starts_at_download_phase_and_log_bounded(environment, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(ui.time, 'monotonic', lambda: clock[0])
    class PausedWorker(ui.SyncWorker):
        def start(self):
            pass
    window = ui.SyncWindow(SimpleNamespace(library=None))
    worker = PausedWorker(window.selected_user, 'songs', environment[1])
    window._start_sync(worker)
    assert window._sync_start is None
    assert window.status_label.text() == 'Fetching library from Spotify...'
    clock[0] = 500
    window.on_progress(0, 10, '')
    clock[0] = 510
    window.on_progress(2, 10, 'Artist - Song')
    assert window.eta_label.text() == 'Elapsed: 10s  |  ETA: 40s'
    assert window.status_label.text() == 'Last completed: Artist - Song'
    for index in range(2100):
        window.append_log(str(index))
    assert window.log_output.document().blockCount() == 2000
    assert window.log_output.toPlainText().splitlines()[0] == '100'
    window.close()


def test_options_clear_values_and_report_save_failure(environment, monkeypatch):
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: 'old')
    monkeypatch.setattr(ui.configutils, 'get_audio_format', lambda: 'mp3', raising=False)
    saved = {}
    monkeypatch.setattr(ui.configutils, 'set_value', lambda section, key, value: saved.update({key: value}))
    window = ui.OptionsWindow()
    window.download_path_entry.clear()
    window.cookies_file_entry.clear()
    window.format_combo.setCurrentText('flac')
    window.save_options()
    assert saved == {'download_path': '', 'cookies_file': '', 'audio_format': 'flac'}
    def fail(*args):
        raise PermissionError('config locked')
    monkeypatch.setattr(ui.configutils, 'set_value', fail)
    window.save_options()
    assert 'config locked' in environment[0][-1][2]
    window.close()


def test_auth_runs_off_main_thread_and_manual_dialog_on_main(environment, monkeypatch):
    seen = []
    def get_text(*args):
        seen.append(QThread.currentThread() == app.thread())
        return 'redirect-url', True
    monkeypatch.setattr(ui.QInputDialog, 'getText', get_text)
    provider = ui.ManualUrlProvider(None)
    def create_user(manual_url_provider, cancel_event):
        seen.append(QThread.currentThread() != app.thread())
        assert manual_url_provider('auth-url') == 'redirect-url'
        return 'user'
    worker = ui.AuthWorker(SimpleNamespace(create_user=create_user), provider)
    results = []
    worker.authenticated.connect(results.append)
    worker.start()
    pump_until(lambda: bool(results))
    assert worker.wait(1000)
    assert seen == [True, True]
    assert results == ['user']


def test_browser_search_presence_filters_and_duplicate_rows(monkeypatch, tmp_path):
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot
    rows = (
        TrackSnapshot('one', 'Same title', 'First artist', 'Album', 61000, 'downloaded'),
        TrackSnapshot('one', 'Same title', 'First artist', 'Album', 61000, 'downloaded'),
        TrackSnapshot('two', 'Same title', 'Second artist', 'Other album', 90000, 'missing'),
        TrackSnapshot('three', 'Recovered', None, None, None, 'quarantined'),
    )
    snapshot = CollectionSnapshot(CollectionKey('account', 'saved'), 'Saved tracks',
                                  str(tmp_path), tracks=rows, scan_complete=True)
    library = SimpleNamespace(browse_collections=lambda *args, **kwargs: iter([snapshot]))
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: window.worker is not None and not window.worker.isRunning())
    assert window.proxy.rowCount() == 4
    assert '1 / 3 downloaded' in window.summary.text()
    window.proxy.set_status('Missing')
    assert window.proxy.rowCount() == 2
    window.search.setText('second artist')
    assert window.proxy.rowCount() == 1
    assert window.proxy.index(0, 2).data() == 'Second artist'
    window.proxy.set_status('Downloaded')
    assert window.proxy.rowCount() == 0
    window.search.clear()
    assert window.proxy.rowCount() == 2
    window.close()


def test_browser_failed_refresh_preserves_rows_without_synced_claim(monkeypatch, tmp_path):
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot
    snapshot = CollectionSnapshot(CollectionKey('account', 'saved'), 'Saved tracks',
                                  str(tmp_path), tracks=(TrackSnapshot('one', 'Song', 'Artist',
                                  'Album', 1000, 'downloaded'),), scan_complete=True, refreshed_at=1)
    def browse(*args, **kwargs):
        if browse.fail:
            raise OSError('Spotify unavailable')
        yield snapshot
    browse.fail = False
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=SimpleNamespace(browse_collections=browse),
                                           get_name=lambda: 'Account'))
    pump_until(lambda: window.worker is not None and not window.worker.isRunning())
    assert 'Synced' in window.summary.text()
    browse.fail = True
    window.refresh()
    assert 'Synced' not in window.summary.text()
    pump_until(lambda: not window.worker.isRunning())
    assert window.model.tracks == snapshot.tracks
    assert window.current_snapshot().stale
    assert window.current_snapshot().coverage == 'unknown'
    assert 'Spotify unavailable' in window.summary.text()
    assert 'Synced' not in window.summary.text()
    window.close()


def test_browser_scoped_sync_retries_only_failed_tracks_and_updates_duplicate_rows(
        environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent
    from utils.fileutils import song_filename

    key = CollectionKey('account', 'saved')
    destination = tmp_path / 'my_songs'
    initial = CollectionSnapshot(key, 'Saved tracks', str(destination), tracks=(
        TrackSnapshot('same123', 'Duplicate', 'Artist', 'Album', 1000, 'missing'),
        TrackSnapshot('same123', 'Duplicate', 'Artist', 'Album', 1000, 'missing'),
        TrackSnapshot('failed123', 'Will fail once', 'Artist', 'Album', 2000, 'missing'),
        TrackSnapshot('good123', 'Good', 'Artist', 'Album', 3000, 'missing'),
    ), scan_complete=True)
    browse_calls = []
    jobs = []
    failure_attempts = [0]

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        rows = []
        for track in initial.tracks:
            path = destination / song_filename(track.artist, track.name, track.track_id)
            rows.append(replace(track, presence='downloaded' if path.is_file() else 'missing',
                                local_path=str(path) if path.is_file() else None))
        yield replace(initial, tracks=tuple(rows), refreshed_at=time.time())

    def sync_collection(collection_key, downloader, download_path, track_ids,
                        operation_id, event_callback, progress_callback):
        ids = tuple(track_ids)
        jobs.append((collection_key, ids))
        attempt = failure_attempts[0]
        event_callback(WorkerEvent(operation_id, collection_key, 'syncing'))
        result = SyncResult()
        for done, track_id in enumerate(ids, 1):
            event_callback(WorkerEvent(operation_id, collection_key, 'downloading', track_id=track_id,
                                       completed=done - 1, total=len(ids)))
            if track_id == 'failed123' and attempt == 0:
                result.add_failure(track_id, None, 'offline')
                event_callback(WorkerEvent(operation_id, collection_key, 'failure',
                                           track_id=track_id, error='offline'))
            else:
                track = next(row for row in initial.tracks if row.track_id == track_id)
                path = destination / song_filename(track.artist, track.name, track.track_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'verified temporary test audio')
                result.add_success()
                event_callback(WorkerEvent(operation_id, collection_key, 'success',
                                           track_id=track_id, final_path=str(path)))
            progress_callback(done, len(ids), 'must not be used as identity')
        failure_attempts[0] += 1
        if result.has_failures:
            event_callback(WorkerEvent(operation_id, collection_key, 'failure', error='offline'))
        else:
            event_callback(WorkerEvent(operation_id, collection_key, 'success'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    assert window.sync_missing_button.isEnabled(), window.loading_label.text()
    window.sync_missing_button.click()
    pump_until(lambda: len(jobs) == 1)
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())

    assert jobs[0] == (key, ('same123', 'failed123', 'good123'))
    rows = window.current_snapshot().tracks
    assert [row.presence for row in rows[:2]] == ['downloaded', 'downloaded']
    assert rows[2].outcome == 'failed' and rows[2].presence == 'missing'
    window.proxy.set_status('Failed')
    assert window.proxy.rowCount() == 1
    late = WorkerEvent('obsolete-operation', key, 'failure', track_id='good123', error='late')
    assert not window._apply_mutation_event(late, worker_event=True)
    assert next(row for row in window.current_snapshot().tracks if row.track_id == 'good123').outcome != 'failed'

    window.retry_failed_button.click()
    pump_until(lambda: len(jobs) == 2)
    pump_until(lambda: len(browse_calls) >= 3 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    assert jobs[1] == (key, ('failed123',))
    assert next(row for row in window.current_snapshot().tracks if row.track_id == 'failed123').presence == 'downloaded'
    assert window.current_snapshot().coverage == 'complete'
    window.close()


def test_browser_sync_all_queues_complete_accessible_collections_only(
        environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent
    from utils.fileutils import song_filename

    saved_key = CollectionKey('account', 'saved')
    playlist_key = CollectionKey('account', 'playlist')
    restricted_key = CollectionKey('account', 'restricted')
    error_key = CollectionKey('account', 'error')
    empty_key = CollectionKey('account', 'empty')
    complete_key = CollectionKey('account', 'complete')
    incomplete_key = CollectionKey('account', 'incomplete')
    saved = CollectionSnapshot(saved_key, 'Saved tracks', str(tmp_path / 'my_songs'), tracks=(
        TrackSnapshot('same123', 'Shared', 'Artist', None, 1000, 'missing'),
    ), scan_complete=True)
    playlist = CollectionSnapshot(playlist_key, 'Mix', str(tmp_path / 'playlists' / 'Mix'), tracks=(
        TrackSnapshot('same123', 'Shared', 'Artist', None, 1000, 'missing'),
        TrackSnapshot('same123', 'Shared', 'Artist', None, 1000, 'missing'),
        TrackSnapshot('other123', 'Other', 'Artist', None, 1000, 'missing'),
    ), scan_complete=True)
    restricted = CollectionSnapshot(restricted_key, 'Restricted', str(tmp_path / 'playlists' / 'Restricted'),
                                    metadata='restricted', error='not accessible')
    failed = CollectionSnapshot(error_key, 'Unavailable', str(tmp_path / 'playlists' / 'Unavailable'),
                                metadata='error', error='listing failed')
    empty = CollectionSnapshot(empty_key, 'Empty', str(tmp_path / 'playlists' / 'Empty'),
                               scan_complete=True)
    complete_destination = tmp_path / 'playlists' / 'Complete'
    complete_track = TrackSnapshot('complete123', 'Complete', 'Artist', None, 1000, 'downloaded')
    complete_path = complete_destination / song_filename(complete_track.artist, complete_track.name,
                                                         complete_track.track_id)
    complete_path.parent.mkdir(parents=True, exist_ok=True)
    complete_path.write_bytes(b'existing test audio')
    complete = CollectionSnapshot(complete_key, 'Complete', str(complete_destination),
                                  tracks=(complete_track,), scan_complete=True)
    incomplete = CollectionSnapshot(incomplete_key, 'Incomplete', str(tmp_path / 'playlists' / 'Incomplete'),
                                    tracks=(TrackSnapshot('unknown123', 'Unknown', 'Artist', None,
                                                          1000, 'missing'),), scan_complete=False)
    base_snapshots = (saved, playlist, restricted, failed, empty, complete, incomplete)
    browse_calls = []
    jobs = []

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        for base in base_snapshots:
            rows = []
            for track in base.tracks:
                path = Path(base.destination) / song_filename(track.artist, track.name, track.track_id)
                present = path.is_file()
                rows.append(replace(track, presence='downloaded' if present else 'missing',
                                    local_path=str(path) if present else None))
            yield replace(base, tracks=tuple(rows), refreshed_at=time.time())

    def sync_collection(collection_key, downloader, download_path, track_ids,
                        operation_id, event_callback, progress_callback):
        ids = tuple(track_ids)
        jobs.append((collection_key, ids, download_path))
        snapshot = next(item for item in base_snapshots if item.key == collection_key)
        event_callback(WorkerEvent(operation_id, collection_key, 'syncing'))
        result = SyncResult()
        for track_id in ids:
            track = next(row for row in snapshot.tracks if row.track_id == track_id)
            if collection_key == saved_key:
                result.add_failure(track_id, None, 'provider unavailable')
                event_callback(WorkerEvent(operation_id, collection_key, 'failure',
                                           track_id=track_id, error='provider unavailable'))
            else:
                path = Path(snapshot.destination) / song_filename(track.artist, track.name, track.track_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'temporary test audio')
                result.add_success()
                event_callback(WorkerEvent(operation_id, collection_key, 'success',
                                           track_id=track_id, final_path=str(path)))
        if result.has_failures:
            event_callback(WorkerEvent(operation_id, collection_key, 'failure', error='provider unavailable'))
        else:
            event_callback(WorkerEvent(operation_id, collection_key, 'success'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    assert window.sync_all_button.isEnabled()
    window.sync_all_button.click()
    assert '1 restricted' in window.loading_label.text()
    assert '1 error' in window.loading_label.text()
    assert '1 empty' in window.loading_label.text()
    assert '1 complete' in window.loading_label.text()
    assert '1 incomplete' in window.loading_label.text()
    pump_until(lambda: len(jobs) == 2 and len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    assert [(key, ids) for key, ids, _ in jobs] == [
        (saved_key, ('same123',)), (playlist_key, ('same123', 'other123'))]
    assert all(root == str(tmp_path) for _, _, root in jobs)
    assert window.snapshots[restricted_key].metadata == 'restricted'
    assert window.snapshots[error_key].metadata == 'error'
    assert window.snapshots[empty_key].status == 'Empty'
    assert window.snapshots[complete_key].status == 'Synced'
    assert window.snapshots[incomplete_key].coverage == 'unknown'
    assert window.snapshots[saved_key].coverage == 'missing'
    assert window.snapshots[saved_key].status == 'Failed'
    assert window.snapshots[playlist_key].coverage == 'complete'
    window.close()


def test_browser_sync_all_captures_one_root_and_never_claims_other_root_success(
        environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from pathlib import Path
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent
    from utils.fileutils import song_filename

    root_a, root_b = tmp_path / 'root-a', tmp_path / 'root-b'
    saved_key = CollectionKey('account', 'saved')
    playlist_key = CollectionKey('account', 'playlist')
    definitions = (
        (saved_key, 'Saved tracks', 'saved123', 'Saved', 'my_songs'),
        (playlist_key, 'Mix', 'mix123', 'Mix track', 'playlists/Mix'),
    )
    path_calls = [0]
    browse_calls = []
    requests = []
    ready_for_success = threading.Event()
    allow_first_return = threading.Event()

    def get_path():
        path_calls[0] += 1
        return str(root_a if path_calls[0] <= 2 else root_b)

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        root = Path(download_path)
        for key, name, track_id, title, relative in definitions:
            destination = root.joinpath(*relative.split('/'))
            track = TrackSnapshot(track_id, title, 'Artist', None, 1000, 'missing')
            local = destination / song_filename(track.artist, track.name, track.track_id)
            elsewhere = (root_a.joinpath(*relative.split('/')) /
                         song_filename(track.artist, track.name, track.track_id))
            if local.is_file():
                track = replace(track, presence='downloaded', local_path=str(local))
            elif download_path == str(root_b) and elsewhere.is_file():
                track = replace(track, presence='missing', elsewhere_path=str(elsewhere))
            yield CollectionSnapshot(key, name, str(destination), tracks=(track,),
                                     refreshed_at=time.time(), scan_complete=True)

    def sync_collection(collection_key, downloader, download_path, track_ids,
                        operation_id, event_callback, progress_callback):
        ids = tuple(track_ids)
        requests.append((collection_key, ids, download_path))
        definition = next(item for item in definitions if item[0] == collection_key)
        _, _, track_id, title, relative = definition
        destination = Path(download_path).joinpath(*relative.split('/'))
        event_callback(WorkerEvent(operation_id, collection_key, 'syncing'))
        path = destination / song_filename('Artist', title, track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'temporary verified output')
        result = SyncResult(success_count=1)
        if collection_key == saved_key:
            ready_for_success.set()
            allow_first_return.wait(2)
        event_callback(WorkerEvent(operation_id, collection_key, 'success',
                                   track_id=track_id, final_path=str(path)))
        event_callback(WorkerEvent(operation_id, collection_key, 'success'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection)
    monkeypatch.setattr(ui.configutils, 'get_download_path', get_path)
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    assert window.sync_all_button.isEnabled()
    window.sync_all_button.click()
    pump_until(ready_for_success.is_set)
    window.collections.setCurrentItem(window.items[playlist_key])
    assert window.current_snapshot().key == playlist_key
    queued_before_repeat = len(window._mutation_queue)
    window.sync_all_button.click()
    assert len(requests) == 1 and len(window._mutation_queue) == queued_before_repeat
    assert 'already active or queued' in window.loading_label.text()
    allow_first_return.set()
    pump_until(lambda: window.snapshots[saved_key].stale
               and window.snapshots[saved_key].tracks[0].presence == 'unknown')
    assert requests[0][2] == str(root_a)
    assert window.snapshots[saved_key].tracks[0].presence != 'downloaded'
    pump_until(lambda: len(requests) == 2 and len(browse_calls) >= 2
               and window._active_worker is None and window.worker is not None
               and not window.worker.isRunning())
    assert [request[2] for request in requests] == [str(root_a), str(root_a)]
    for key, _, _, _, _ in definitions:
        row = window.snapshots[key].tracks[0]
        assert row.presence == 'missing' and row.elsewhere_path
    assert len(browse_calls) == 2
    window.close()


def test_browser_playback_queue_survives_navigation_and_repair_stops_player(
        environment, monkeypatch, tmp_path):
    import wave
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    saved_key = CollectionKey('account', 'saved')
    playlist_key = CollectionKey('account', 'playlist')
    saved_dir = tmp_path / 'my_songs'
    playlist_dir = tmp_path / 'playlists' / 'Mix'
    saved_dir.mkdir(parents=True)
    playlist_dir.mkdir(parents=True)
    first_path = saved_dir / 'First [first123].wav'
    second_path = saved_dir / 'Second [second123].wav'
    playlist_path = playlist_dir / 'Other [other123].wav'
    for path in (first_path, second_path, playlist_path):
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(bytes(8000 * 2 * 10))
    saved = CollectionSnapshot(saved_key, 'Saved tracks', str(saved_dir), tracks=(
        TrackSnapshot('first123', 'First', 'Artist', None, 10000, 'downloaded', str(first_path)),
        TrackSnapshot('second123', 'Second', 'Artist', None, 10000, 'downloaded', str(second_path)),
    ), scan_complete=True)
    playlist = CollectionSnapshot(playlist_key, 'Mix', str(playlist_dir), tracks=(
        TrackSnapshot('other123', 'Other', 'Artist', None, 10000, 'downloaded', str(playlist_path)),
    ), scan_complete=True)
    browse_calls = []
    repair_entered = threading.Event()
    repair_release = threading.Event()

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        yield saved
        yield playlist

    def repair_library(progress_callback, cancel_check, download_path=None):
        progress_callback(0, 1, '')
        repair_entered.set()
        repair_release.wait(2)
        return SyncResult(success_count=1)

    library = SimpleNamespace(browse_collections=browse, repair_library=repair_library)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window._play_table_index(window.proxy.index(1, 0))
    assert window.playback.current_entry.track_id == 'second123'
    assert [entry.track_id for entry in window.playback.queue] == ['first123', 'second123']
    window.collections.setCurrentItem(window.items[playlist_key])
    assert window.current_snapshot().key == playlist_key
    assert [entry.collection_key for entry in window.playback.queue] == [saved_key, saved_key]
    assert window.playback.current_entry.track_id == 'second123'
    window.repair_library_button.click()
    pump_until(lambda: repair_entered.is_set())
    assert window.playback.current_entry is None
    repair_release.set()
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    window.close()


def test_table_is_playable_and_pausable_from_the_keyboard(environment, monkeypatch, tmp_path):
    import wave
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    path = tmp_path / 'Song [one123].wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * 10))
    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path), tracks=(
        TrackSnapshot('one123', 'Song', 'Artist', None, 10000, 'downloaded', str(path)),
    ), scan_complete=True)
    library = SimpleNamespace(browse_collections=lambda *a, **k: iter([snapshot]))
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    window.show()
    pump_until(lambda: window.worker is not None and not window.worker.isRunning())
    window.table.setFocus()
    window.table.selectRow(0)
    window.table.setCurrentIndex(window.proxy.index(0, 0))
    QTest.keyClick(window.table, Qt.Key_Return)
    pump_until(lambda: window.playback.current_entry is not None)
    pump_until(lambda: window._playback_state == 'playing')
    QTest.keyClick(window.table, Qt.Key_Space)
    pump_until(lambda: window._playback_state == 'paused')
    QTest.keyClick(window.table, Qt.Key_Space)
    pump_until(lambda: window._playback_state == 'playing')
    window.close()
    pump_until(lambda: window.playback._closed)


def test_seek_slider_seeks_on_click_drag_and_keyboard():
    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtTest import QTest
    from ui.library_browser import SeekSlider

    slider = SeekSlider()
    slider.resize(400, 24)
    slider.setRange(0, 20000)
    slider.show()
    seeks = []
    slider.seek_requested.connect(seeks.append)
    QTest.mouseClick(slider, Qt.LeftButton, pos=QPoint(200, 12))
    assert seeks and abs(seeks[-1] - 10000) < 1500
    assert slider.value() == seeks[-1]
    QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(100, 12))
    drag = QMouseEvent(QEvent.MouseMove, QPointF(300, 12), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(slider, drag)
    assert slider.user_seeking and seeks[-1] > 10000
    QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(300, 12))
    assert not slider.user_seeking
    count = len(seeks)
    slider.setFocus()
    QTest.keyClick(slider, Qt.Key_Right)
    assert len(seeks) == count + 1
    slider.setValue(5)  # programmatic position updates never request a seek
    assert len(seeks) == count + 1
    slider.close()


def test_browser_close_waits_for_native_playback_release(environment, monkeypatch, tmp_path):
    import wave
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    key = CollectionKey('account', 'saved')
    destination = tmp_path / 'my_songs'
    destination.mkdir()
    path = destination / 'Song [one123].wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * 10))
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(destination), tracks=(
        TrackSnapshot('one123', 'Song', 'Artist', None, 10000, 'downloaded', str(path)),
    ), scan_complete=True)
    library = SimpleNamespace(browse_collections=lambda *args, **kwargs: iter([snapshot]))
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    window.show()
    pump_until(lambda: window.worker is not None and not window.worker.isRunning())
    window._play_table_index(window.proxy.index(0, 0))
    assert window.playback.current_entry is not None
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    pump_until(lambda: window.playback._closed)
    assert not window.isVisible()


def test_embedded_browser_close_after_playback_release_closes_main_window(environment, monkeypatch, tmp_path):
    import wave
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    key = CollectionKey('account', 'saved')
    destination = tmp_path / 'my_songs'
    destination.mkdir()
    path = destination / 'Song [one123].wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * 10))
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(destination), tracks=(
        TrackSnapshot('one123', 'Song', 'Artist', None, 10000, 'downloaded', str(path)),
    ), scan_complete=True)
    library = SimpleNamespace(browse_collections=lambda *args, **kwargs: iter([snapshot]))
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    user = SimpleNamespace(library=library, get_name=lambda: 'Account', get_id=lambda: 'account')
    manager = SimpleNamespace(get_users=lambda: [user], get_selected_user=lambda: user,
                              set_session_id=lambda value: None)
    monkeypatch.setattr(ui, 'SessionManager', lambda: manager)
    main = ui.MainWindow()
    main.show()
    main.open_library_window()
    browser = main.centralWidget()
    assert isinstance(browser, LibraryBrowser)
    pump_until(lambda: browser.worker is not None and not browser.worker.isRunning())
    browser._play_table_index(browser.proxy.index(0, 0))
    assert browser.playback.current_entry is not None
    # Live finding: the deferred close closed only the embedded widget and left an
    # empty top-level window (and the process) alive.
    main.close()
    pump_until(lambda: browser.playback._closed)
    pump_until(lambda: not main.isVisible())


def test_browser_repair_library_is_queued_confirmed_and_uses_captured_root(
        environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot
    from utils.repair import quarantine

    key = CollectionKey('account', 'saved')
    destination = tmp_path / 'my_songs'
    source = destination / 'Artist - Song [one123].mp3'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'original temporary audio')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(destination), tracks=(
        TrackSnapshot('one123', 'Song', 'Artist', None, 1000, 'downloaded', str(source)),
    ), scan_complete=True)
    browse_calls = []
    repairs = []
    entered = threading.Event()
    release = threading.Event()

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        quarantined = destination / '_rejected' / source.name
        row = replace(snapshot.tracks[0],
                      presence='quarantined' if quarantined.is_file() else 'downloaded',
                      local_path=str(source) if source.is_file() else None)
        yield replace(snapshot, tracks=(row,), refreshed_at=time.time())

    def repair_library(progress_callback, cancel_check, download_path=None):
        repairs.append(download_path)
        progress_callback(0, 1, 'name is not row identity')
        entered.set()
        release.wait(2)
        quarantine(source, destination)
        return SyncResult(success_count=1)

    library = SimpleNamespace(browse_collections=browse, repair_library=repair_library)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    assert window.repair_library_button.isEnabled()
    window.repair_library_button.click()
    pump_until(lambda: entered.is_set() and 'Repairing' in window.activity_label.text())
    assert repairs == [str(tmp_path)]
    assert window.current_snapshot().stale
    assert window.activity_label.text().startswith('Repair Library: whole library')
    release.set()
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    assert '1 succeeded' in window._operation_summaries[key]
    assert window.current_snapshot().tracks[0].presence == 'quarantined'
    assert window.current_snapshot().coverage == 'missing'
    assert window.current_snapshot().status != 'Synced'
    assert (destination / '_rejected' / source.name).read_bytes() == b'original temporary audio'
    window.close()


def test_browser_close_cancels_and_waits_for_whole_library_repair(environment, monkeypatch, tmp_path):
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path / 'my_songs'),
                                  tracks=(TrackSnapshot('one123', 'Song', 'Artist', None, 1000,
                                                        'downloaded'),), scan_complete=True)
    browse_calls = []
    entered = threading.Event()
    cancelled = threading.Event()

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        yield snapshot

    def repair_library(progress_callback, cancel_check, download_path=None):
        entered.set()
        while not cancel_check():
            time.sleep(.005)
        cancelled.set()
        return SyncResult(cancelled=True)

    library = SimpleNamespace(browse_collections=browse, repair_library=repair_library)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window.repair_library_button.click()
    assert entered.wait(1)
    worker = window._active_worker
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert cancelled.is_set()
    assert worker is not None and not worker.isRunning()
    app.processEvents()
    window.close()


def test_browser_repair_rechecks_refresh_started_during_confirmation(environment, monkeypatch, tmp_path):
    from PyQt5.QtWidgets import QMessageBox
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path / 'my_songs'), tracks=(
        TrackSnapshot('one123', 'Song', 'Artist', None, 1000, 'downloaded'),
    ), scan_complete=True)
    browse_calls = []
    refresh_entered = threading.Event()
    refresh_release = threading.Event()
    repair_called = Mock()

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        if len(browse_calls) == 2:
            refresh_entered.set()
            refresh_release.wait(2)
        yield snapshot

    library = SimpleNamespace(browse_collections=browse, repair_library=repair_called)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())

    def confirm_after_refresh(*args):
        window.refresh()
        assert refresh_entered.wait(1)
        return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, 'question', confirm_after_refresh)
    window.repair_library_button.click()
    assert window._mutation_queue == [] and window._active_job is None
    assert window.worker.isRunning()
    assert 'state changed during confirmation' in window.loading_label.text().lower()
    repair_called.assert_not_called()
    refresh_release.set()
    pump_until(lambda: not window.worker.isRunning())
    assert not window.current_snapshot().stale
    window.close()


def test_last_queued_preflight_failure_still_reconciles_deferred_options_change(
        environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent
    from utils.fileutils import song_filename

    environment[1].preflight.side_effect = [[], ['Invalid cookies file']]
    saved_key = CollectionKey('account', 'saved')
    playlist_key = CollectionKey('account', 'playlist')
    base = (
        CollectionSnapshot(saved_key, 'Saved tracks', str(tmp_path / 'my_songs'), tracks=(
            TrackSnapshot('saved123', 'Saved', 'Artist', None, 1000, 'missing'),), scan_complete=True),
        CollectionSnapshot(playlist_key, 'Mix', str(tmp_path / 'playlists' / 'Mix'), tracks=(
            TrackSnapshot('mix123', 'Mix track', 'Artist', None, 1000, 'missing'),), scan_complete=True),
    )
    browse_calls = []
    entered = threading.Event()
    release = threading.Event()
    jobs = []

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        for snapshot in base:
            rows = []
            for track in snapshot.tracks:
                path = Path(snapshot.destination) / song_filename(track.artist, track.name, track.track_id)
                rows.append(replace(track, presence='downloaded' if path.is_file() else 'missing',
                                    local_path=str(path) if path.is_file() else None))
            yield replace(snapshot, tracks=tuple(rows), refreshed_at=time.time())

    def sync_collection(collection_key, downloader, download_path, track_ids,
                        operation_id, event_callback, progress_callback):
        jobs.append(collection_key)
        entered.set()
        release.wait(2)
        snapshot = next(item for item in base if item.key == collection_key)
        track = snapshot.tracks[0]
        path = Path(snapshot.destination) / song_filename(track.artist, track.name, track.track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'temporary verified output')
        result = SyncResult(success_count=1)
        event_callback(WorkerEvent(operation_id, collection_key, 'success',
                                   track_id=track.track_id, final_path=str(path)))
        event_callback(WorkerEvent(operation_id, collection_key, 'success'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window.sync_all_button.click()
    pump_until(entered.is_set)
    assert len(window._mutation_queue) == 1
    window._options_saved()
    assert window._pending_refresh
    release.set()
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    assert jobs == [saved_key]
    assert not window._pending_refresh
    assert window.snapshots[saved_key].tracks[0].presence == 'downloaded'
    assert 'Invalid cookies file' in window._operation_summaries[playlist_key]
    window.close()


def test_browser_queue_is_serial_and_cancel_drops_pending_jobs(environment, monkeypatch, tmp_path):
    from dataclasses import replace
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent

    saved_key = CollectionKey('account', 'saved')
    playlist_key = CollectionKey('account', 'playlist')
    saved = CollectionSnapshot(saved_key, 'Saved tracks', str(tmp_path / 'my_songs'),
                               tracks=(TrackSnapshot('saved123', 'Saved', 'A', None, 1000, 'missing'),),
                               scan_complete=True)
    playlist = CollectionSnapshot(playlist_key, 'Playlist', str(tmp_path / 'playlists' / 'Playlist'),
                                 tracks=(TrackSnapshot('playlist123', 'Playlist track', 'A', None,
                                                       1000, 'missing'),), scan_complete=True)
    browse_calls = []
    starts = []
    entered = threading.Event()
    release = threading.Event()
    repair_called = Mock()
    environment[1].cancel.side_effect = release.set

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        yield saved
        yield playlist

    def sync_collection(collection_key, downloader, operation_id, event_callback, **kwargs):
        starts.append(collection_key)
        entered.set()
        release.wait(2)
        result = SyncResult()
        result.cancelled = True
        event_callback(WorkerEvent(operation_id, collection_key, 'cancelled'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection,
                              repair_library=repair_called)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window.sync_missing_button.click()
    pump_until(entered.is_set)
    window.collections.setCurrentItem(window.items[playlist_key])
    assert window.sync_missing_button.isEnabled()
    window.sync_missing_button.click()
    window.repair_library_button.click()
    assert len(window._mutation_queue) == 2
    assert starts == [saved_key]
    window.cancel_jobs_button.click()
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    assert starts == [saved_key]
    assert window._mutation_queue == []
    repair_called.assert_not_called()
    assert window._operation_summaries[playlist_key] == 'Cancelled before starting; removed from the queue.'
    assert window.snapshots[saved_key].outcome == 'cancelled'
    assert window.snapshots[playlist_key].outcome == 'cancelled'
    environment[1].cancel.assert_called_once()
    window.close()


def test_declining_browser_repair_does_not_queue_or_invalidate(environment, monkeypatch, tmp_path):
    from PyQt5.QtWidgets import QMessageBox
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot

    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path / 'my_songs'),
                                  tracks=(TrackSnapshot('one123', 'Song', 'Artist', None, 1000,
                                                        'downloaded'),), scan_complete=True)
    repair_called = Mock()
    library = SimpleNamespace(browse_collections=lambda *args, **kwargs: iter([snapshot]),
                              repair_library=repair_called)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.No)
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: window.worker is not None and not window.worker.isRunning())
    window.repair_library_button.click()
    repair_called.assert_not_called()
    assert window._mutation_queue == [] and window._active_job is None
    assert not window.current_snapshot().stale
    window.close()


def test_preopened_batch_window_cannot_overlap_browser_mutation(environment, monkeypatch, tmp_path):
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent

    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path / 'my_songs'),
                                  tracks=(TrackSnapshot('one123', 'Song', 'Artist', None, 1000,
                                                        'missing'),), scan_complete=True)
    browse_calls = []
    entered = threading.Event()
    release = threading.Event()
    environment[1].cancel.side_effect = release.set
    batch_sync = Mock()

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        yield snapshot

    def sync_collection(collection_key, downloader, operation_id, event_callback, **kwargs):
        entered.set()
        release.wait(2)
        result = SyncResult(cancelled=True)
        event_callback(WorkerEvent(operation_id, collection_key, 'cancelled'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection,
                              sync_songs=batch_sync)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window.open_sync()  # Open the batch window before starting a browser job.
    window.sync_missing_button.click()
    assert entered.wait(1)
    window.sync_window.sync_songs_button.click()
    assert window.sync_window.sync_thread is None
    batch_sync.assert_not_called()
    window.cancel_jobs_button.click()
    pump_until(lambda: len(browse_calls) >= 2 and window._active_worker is None
               and window.worker is not None and not window.worker.isRunning())
    window.close()


def test_browser_close_cancels_and_waits_for_scoped_worker(environment, monkeypatch, tmp_path):
    from ui.library_browser import LibraryBrowser
    from model.library_state import CollectionKey, CollectionSnapshot, TrackSnapshot, WorkerEvent

    key = CollectionKey('account', 'saved')
    snapshot = CollectionSnapshot(key, 'Saved tracks', str(tmp_path / 'my_songs'),
                                  tracks=(TrackSnapshot('one123', 'Song', 'Artist', None, 1000,
                                                        'missing'),), scan_complete=True)
    browse_calls = []
    entered = threading.Event()
    release = threading.Event()
    environment[1].cancel.side_effect = release.set

    def browse(download_path, cancel_check=None, selected_key=None):
        browse_calls.append(download_path)
        yield snapshot

    def sync_collection(collection_key, downloader, operation_id, event_callback, **kwargs):
        entered.set()
        release.wait(2)
        result = SyncResult()
        result.cancelled = True
        event_callback(WorkerEvent(operation_id, collection_key, 'cancelled'))
        return result

    library = SimpleNamespace(browse_collections=browse, sync_collection=sync_collection)
    monkeypatch.setattr(ui.configutils, 'get_download_path', lambda: str(tmp_path))
    window = LibraryBrowser(SimpleNamespace(library=library, get_name=lambda: 'Account'))
    pump_until(lambda: len(browse_calls) == 1 and window.worker is not None and not window.worker.isRunning())
    window.sync_missing_button.click()
    assert entered.wait(1)
    worker = window._active_worker
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert worker is not None and not worker.isRunning()
    environment[1].cancel.assert_called_once()
    app.processEvents()
    window.close()
