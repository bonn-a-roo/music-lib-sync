import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

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
    monkeypatch.setattr(window, 'open_sync_window', lambda: opened.append(manager.selected))
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
    def repair(progress_callback, cancel_check):
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
