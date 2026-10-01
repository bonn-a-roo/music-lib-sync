import threading
import time

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QApplication, QMainWindow, QComboBox, QWidget, QVBoxLayout,
                             QPushButton, QFileDialog, QMessageBox, QLabel, QLineEdit,
                             QProgressBar, QPlainTextEdit, QInputDialog)

from downloaders.ytdlp import YoutubeDownloader
from model.session_manager import SessionManager
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)


def _fmt_duration(seconds):
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    if not minutes:
        return f'{seconds}s'
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02d}m' if hours else f'{minutes}m {seconds:02d}s'


class OptionsWindow(QWidget):
    saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Options')
        layout = QVBoxLayout(self)
        self.download_path_entry = QLineEdit(configutils.get_download_path())
        self.cookies_file_entry = QLineEdit(configutils.get_cookies_file())
        for label, entry, browse in [('Download Path:', self.download_path_entry, self.browse_download_path),
                                     ('Cookies File:', self.cookies_file_entry, self.browse_cookies_file)]:
            layout.addWidget(QLabel(label))
            layout.addWidget(entry)
            button = QPushButton('Browse')
            button.clicked.connect(browse)
            layout.addWidget(button)
        layout.addWidget(QLabel('Audio Format:'))
        self.format_combo = QComboBox()
        self.format_combo.addItems(['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])
        self.format_combo.setCurrentText(configutils.get_audio_format())
        layout.addWidget(self.format_combo)
        self.save_button = QPushButton('Save Options')
        self.save_button.clicked.connect(self.save_options)
        layout.addWidget(self.save_button)
        self.status_label = QLabel('')
        layout.addWidget(self.status_label)

    def browse_download_path(self):
        path = QFileDialog.getExistingDirectory(self, 'Select Download Path')
        if path:
            self.download_path_entry.setText(path)

    def browse_cookies_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select Cookies File')
        if path:
            self.cookies_file_entry.setText(path)

    def save_options(self):
        try:
            configutils.set_value('Settings', 'download_path', self.download_path_entry.text())
            configutils.set_value('Settings', 'cookies_file', self.cookies_file_entry.text())
            configutils.set_value('Settings', 'audio_format', self.format_combo.currentText())
        except Exception as exc:
            logger.exception('Saving options failed')
            QMessageBox.critical(self, 'Could not save options', str(exc))
            return
        self.status_label.setText('Saved.')
        self.saved.emit()
        QTimer.singleShot(2000, lambda: self.status_label.setText(''))


class SyncWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    log_line = pyqtSignal(str)

    def __init__(self, selected_user, kind, downloader=None):
        super().__init__()
        self.selected_user = selected_user
        self.kind = kind
        self._downloader = downloader
        self._cancelled = threading.Event()
        if downloader:
            downloader.log_callback = self.log_line.emit

    def cancel(self):
        self._cancelled.set()
        if self._downloader:
            self._downloader.cancel()

    def run(self):
        try:
            library = self.selected_user.library
            if self.kind == 'repair':
                result = library.repair_library(progress_callback=self.progress.emit,
                                                cancel_check=self._cancelled.is_set)
            elif self.kind in ('songs', 'playlists'):
                result = getattr(library, 'sync_' + self.kind)(
                    downloader=self._downloader, progress_callback=self.progress.emit)
            else:
                raise ValueError(f'Unknown sync kind: {self.kind}')
            self.result_ready.emit(result)
        except BaseException as exc:
            logger.exception('Library operation failed')
            self.failed.emit(str(exc) or type(exc).__name__)


class SyncWindow(QWidget):
    options_saved = pyqtSignal()
    closed = pyqtSignal()
    operation_started = pyqtSignal()
    operation_finished = pyqtSignal()

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user
        self.options_window = None
        self.sync_thread = None
        self.setWindowTitle('Synchronization')
        layout = QVBoxLayout(self)
        self.sync_songs_button = QPushButton('Sync Songs')
        self.sync_playlists_button = QPushButton('Sync Playlists')
        self.repair_button = QPushButton('Repair Library')
        self.options_button = QPushButton('Options')
        self.sync_songs_button.clicked.connect(self.sync_songs)
        self.sync_playlists_button.clicked.connect(self.sync_playlists)
        self.repair_button.clicked.connect(self.repair_library)
        self.options_button.clicked.connect(self.open_options_window)
        self._buttons = (self.sync_songs_button, self.sync_playlists_button, self.repair_button, self.options_button)
        for button in self._buttons:
            layout.addWidget(button)
        self.progress_bar = QProgressBar()
        self.eta_label = QLabel('')
        self.status_label = QLabel('')
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel_sync)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont('Consolas', 8))
        self.log_output.setMaximumBlockCount(2000)
        self.log_output.setMinimumHeight(120)
        self.log_output.setMaximumHeight(200)
        self._run_widgets = (self.progress_bar, self.eta_label, self.status_label, self.cancel_button, self.log_output)
        for widget in self._run_widgets:
            layout.addWidget(widget)
            widget.hide()
        self._sync_start = None
        self._progress_state = (0, 0)
        self._eta_timer = QTimer(self)
        self._eta_timer.setInterval(1000)
        self._eta_timer.timeout.connect(self._update_eta)

    def _begin(self, kind):
        if self.sync_thread and self.sync_thread.isRunning():
            return
        try:
            downloader = None
            if kind != 'repair':
                downloader = YoutubeDownloader(cookies_file=configutils.get_cookies_file() or None)
                problems = downloader.preflight()
                if problems:
                    QMessageBox.critical(self, 'Download prerequisites missing', '\n'.join(problems))
                    return
            self._start_sync(SyncWorker(self.selected_user, kind, downloader))
        except BaseException as exc:
            logger.exception('Preparing library operation failed')
            self.on_sync_failed(str(exc))

    def _start_sync(self, worker):
        if self.sync_thread and self.sync_thread.isRunning():
            return
        for button in self._buttons:
            button.setEnabled(False)
        self.sync_thread = worker
        worker.result_ready.connect(self.on_sync_finished)
        worker.failed.connect(self.on_sync_failed)
        worker.progress.connect(self.on_progress)
        worker.log_line.connect(self.append_log)
        worker.finished.connect(self.operation_finished.emit)
        self.operation_started.emit()
        self._sync_start = None
        self._progress_state = (0, 0)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText('Fetching library from Spotify...')
        self.eta_label.setText('Waiting for library...')
        self.cancel_button.setText('Cancel')
        self.cancel_button.setEnabled(True)
        self.log_output.clear()
        for widget in self._run_widgets:
            widget.show()
        worker.start()

    def sync_songs(self):
        self._begin('songs')

    def sync_playlists(self):
        self._begin('playlists')

    def repair_library(self):
        answer = QMessageBox.question(self, 'Repair Library',
            'Repair flattens nested folders, moves wrong-length files to _rejected, '
            'and writes missing audio metadata tags. Continue?', QMessageBox.Yes | QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._begin('repair')

    def cancel_sync(self):
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText('Cancelling...')
        if self.sync_thread:
            self.sync_thread.cancel()

    def append_log(self, line):
        self.log_output.appendPlainText(line)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_eta(self):
        if self._sync_start is None:
            return
        elapsed = max(0.001, time.monotonic() - self._sync_start)
        current, total = self._progress_state
        text = f'Elapsed: {_fmt_duration(elapsed)}'
        if 0 < current < total:
            text += f'  |  ETA: {_fmt_duration((total - current) * elapsed / current)}'
        self.eta_label.setText(text)

    def on_progress(self, current, total, name):
        if self._sync_start is None and current == 0 and not name:
            self._sync_start = time.monotonic()
            self._eta_timer.start()
            self.status_label.setText('Processing library...')
        self._progress_state = (current, total)
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(current)
        if name:
            self.status_label.setText(f'Last completed: {name}')
        self._update_eta()

    def _restore(self):
        self._eta_timer.stop()
        for button in self._buttons:
            button.setEnabled(True)
        for widget in self._run_widgets:
            widget.hide()
        self.cancel_button.setText('Cancel')
        self.cancel_button.setEnabled(True)

    def on_sync_failed(self, message):
        self._restore()
        QMessageBox.critical(self, 'Library operation failed', message)

    def on_sync_finished(self, result):
        self._restore()
        if result.cancelled:
            QMessageBox.information(self, 'Sync Cancelled', result.get_summary())
        elif result.has_failures:
            QMessageBox.warning(self, 'Sync Complete (with errors)', result.get_summary())
        else:
            QMessageBox.information(self, 'Sync Complete', result.get_summary())

    def closeEvent(self, event):
        if self.sync_thread and self.sync_thread.isRunning():
            self.sync_thread.cancel()
            if not self.sync_thread.wait(5000):
                event.ignore()
                return
        event.accept()
        if self.options_window:
            self.options_window.close()
        self.closed.emit()

    def open_options_window(self):
        if not self.options_window:
            self.options_window = OptionsWindow()
            self.options_window.saved.connect(self.options_saved.emit)
        self.options_window.show()


class ManualUrlProvider(QObject):
    requested = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.requested.connect(self._show_dialog)

    def __call__(self, auth_url):
        request = {'url': auth_url, 'done': threading.Event(), 'answer': None}
        self.requested.emit(request)
        request['done'].wait()
        return request['answer']

    @pyqtSlot(object)
    def _show_dialog(self, request):
        try:
            text, accepted = QInputDialog.getText(self.parent(), 'Spotify Authentication',
                'Authorize in your browser, then paste the FULL redirect URL:')
            if accepted:
                request['answer'] = text
        finally:
            request['done'].set()


class AuthWorker(QThread):
    authenticated = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, manager, provider):
        super().__init__()
        self.manager = manager
        self.provider = provider
        self.cancel_event = threading.Event()

    def run(self):
        try:
            self.authenticated.emit(self.manager.create_user(
                manual_url_provider=self.provider, cancel_event=self.cancel_event))
        except BaseException as exc:
            logger.exception('Spotify authentication failed')
            self.failed.emit(str(exc) or type(exc).__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Music Library Sync')
        self.session_manager = SessionManager()
        self.auth_thread = None
        self.manual_url_provider = ManualUrlProvider(self)
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        self.user_selection = QComboBox()
        layout.addWidget(self.user_selection)
        self.sync_button = QPushButton('Go')
        self.sync_button.clicked.connect(self.handle_user_selection)
        layout.addWidget(self.sync_button)
        self.auth_status = QLabel('')
        layout.addWidget(self.auth_status)
        self._populate_users()
        if not self.users:
            self.sync_button.setEnabled(False)
            QTimer.singleShot(0, self.start_authentication)

    def _populate_users(self, unused=None):
        self.users = self.session_manager.get_users()
        self.user_selection.clear()
        for user in self.users:
            self.user_selection.addItem(f'{user.get_name()} ({user.get_id()})', user.get_id())
        self.sync_button.setEnabled(bool(self.users))
        self.auth_status.setText('')

    def start_authentication(self):
        if self.auth_thread and self.auth_thread.isRunning():
            return
        self.auth_status.setText('Authenticating with Spotify...')
        self.auth_thread = AuthWorker(self.session_manager, self.manual_url_provider)
        self.auth_thread.authenticated.connect(self._populate_users)
        self.auth_thread.failed.connect(self._authentication_failed)
        self.auth_thread.start()

    def _authentication_failed(self, message):
        self.auth_status.setText('Authentication failed.')
        dialog = QMessageBox(QMessageBox.Critical, 'Spotify Authentication', message,
                             QMessageBox.Retry | QMessageBox.Close, self)
        dialog.button(QMessageBox.Close).setText('Quit')
        dialog.setDefaultButton(QMessageBox.Retry)
        answer = dialog.exec_()
        if answer == QMessageBox.Retry:
            # The failed signal can arrive just before QThread finishes.
            QTimer.singleShot(100, self.start_authentication)
        else:
            self.close()

    def handle_user_selection(self, checked=False):
        user_id = self.user_selection.currentData()
        if user_id is None:
            return
        self.session_manager.set_session_id(user_id)
        self.open_library_window()

    def open_library_window(self):
        from ui.library_browser import LibraryBrowser
        selected = self.session_manager.get_selected_user()
        if selected:
            self.setCentralWidget(LibraryBrowser(selected))
            self.resize(1200, 800)

    def closeEvent(self, event):
        widget = self.centralWidget()
        from ui.library_browser import LibraryBrowser
        if isinstance(widget, (SyncWindow, LibraryBrowser)) and not widget.close():
            event.ignore()
            return
        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.cancel_event.set()
            if not self.auth_thread.wait(3000):
                event.ignore()
                return
        event.accept()
