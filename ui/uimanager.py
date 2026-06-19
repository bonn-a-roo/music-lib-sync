from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QMainWindow, QComboBox, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QLabel, \
    QLineEdit, QHBoxLayout, QProgressBar

from model.session_manager import SessionManager
from utils import configutils
from model.sync_result import SyncResult


class OptionsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Options")

        self.download_path_label = QLabel("Download Path:", self)
        self.download_path_entry = QLineEdit(self)
        self.browse_path_button = QPushButton("Browse", self)
        self.browse_path_button.clicked.connect(self.browse_download_path)

        self.cookies_file_label = QLabel("Cookies File:", self)
        self.cookies_file_entry = QLineEdit(self)
        self.browse_cookies_button = QPushButton("Browse", self)
        self.browse_cookies_button.clicked.connect(self.browse_cookies_file)

        self.format_label = QLabel("Audio Format:", self)
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(['mp3', 'flac', 'm4a', 'opus', 'ogg', 'wav'])

        self.providers_label = QLabel("Audio Providers:", self)
        self.providers_entry = QLineEdit(self)
        self.providers_entry.setPlaceholderText("e.g. piped youtube")

        self.save_button = QPushButton("Save Options", self)
        self.save_button.clicked.connect(self.save_options)

        layout = QVBoxLayout()
        layout.addWidget(self.download_path_label)
        layout.addWidget(self.download_path_entry)
        layout.addWidget(self.browse_path_button)
        layout.addWidget(self.cookies_file_label)
        layout.addWidget(self.cookies_file_entry)
        layout.addWidget(self.browse_cookies_button)

        format_row = QHBoxLayout()
        format_row.addWidget(self.format_label)
        format_row.addWidget(self.format_combo)
        layout.addLayout(format_row)

        layout.addWidget(self.providers_label)
        layout.addWidget(self.providers_entry)

        layout.addWidget(self.save_button)

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: green;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        # Load and display the saved values
        self.load_saved_values()

    def load_saved_values(self):
        self.download_path_entry.setText(configutils.get_download_path())
        self.cookies_file_entry.setText(configutils.get_cookies_file())
        fmt = configutils.get_audio_format()
        idx = self.format_combo.findText(fmt)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        self.providers_entry.setText(configutils.get_audio_providers())

    def browse_download_path(self):
        download_path = QFileDialog.getExistingDirectory(self, "Select Download Path")
        if download_path:
            self.download_path_entry.setText(download_path)

    def browse_cookies_file(self):
        cookies_file, _ = QFileDialog.getOpenFileName(self, "Select Cookies File")
        if cookies_file:
            self.cookies_file_entry.setText(cookies_file)

    def save_options(self):
        download_path = self.download_path_entry.text()
        cookies_file = self.cookies_file_entry.text()

        if download_path:
            configutils.set_value('Settings', 'download_path', download_path)
        if cookies_file:
            configutils.set_value('Settings', 'cookies_file', cookies_file)
        configutils.set_value('Settings', 'audio_format', self.format_combo.currentText())
        providers = self.providers_entry.text().strip()
        if providers:
            configutils.set_value('Settings', 'audio_providers', providers)

        self.status_label.setText("Saved.")
        QTimer.singleShot(2000, lambda: self.status_label.setText(""))


class SyncWindow(QWidget):
    def __init__(self, selected_user):
        super().__init__()
        self.options_window = None
        self.sync_thread = None
        self.setWindowTitle("Synchronization")

        self.selected_user = selected_user
        self.sync_songs_button = QPushButton("Sync Songs", self)
        self.sync_songs_button.clicked.connect(self.sync_songs)

        self.sync_playlists_button = QPushButton("Sync Playlists", self)
        self.sync_playlists_button.clicked.connect(self.sync_playlists)

        self.options_button = QPushButton("Options", self)
        self.options_button.clicked.connect(self.open_options_window)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)

        self.status_label = QLabel("", self)
        self.status_label.setVisible(False)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_sync)

        layout = QVBoxLayout()
        layout.addWidget(self.sync_songs_button)
        layout.addWidget(self.sync_playlists_button)
        layout.addWidget(self.options_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)

    def _start_sync(self, worker):
        self.sync_songs_button.setEnabled(False)
        self.sync_playlists_button.setEnabled(False)
        self.options_button.setEnabled(False)

        if self.sync_thread is not None:
            self.sync_thread.wait()

        self.sync_thread = worker
        self.sync_thread.result_ready.connect(self.on_sync_finished)
        self.sync_thread.progress.connect(self.on_progress)

        self.progress_bar.setMaximum(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("")
        self.status_label.setVisible(True)
        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)

        self.sync_thread.start()

    def sync_songs(self):
        self._start_sync(SyncSongsWorker(self.selected_user))

    def sync_playlists(self):
        self._start_sync(SyncPlaylistsWorker(self.selected_user))

    def cancel_sync(self):
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling...")
        if self.sync_thread:
            self.sync_thread.cancel()

    def on_progress(self, current: int, total: int, name: str):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        if name:
            self.status_label.setText(f"Downloading: {name}")

    def on_sync_finished(self, result: SyncResult):
        self.sync_songs_button.setEnabled(True)
        self.sync_playlists_button.setEnabled(True)
        self.options_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(True)

        if result.cancelled:
            msg = result.get_summary() + "\n\nRun sync again to continue where you left off."
            QMessageBox.information(self, "Sync Cancelled", msg)
        elif result.has_failures:
            QMessageBox.warning(self, "Sync Complete (with errors)", result.get_summary())
        else:
            QMessageBox.information(self, "Sync Complete", result.get_summary())

    def open_options_window(self):
        if not self.options_window:
            self.options_window = OptionsWindow()
        self.options_window.show()


class SyncSongsWorker(QThread):
    result_ready = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user
        self._downloader = None

    def cancel(self):
        if self._downloader:
            self._downloader.cancel()

    def run(self):
        from utils import configutils
        from downloaders.spotifydl import SpotifyDownloader
        self._downloader = SpotifyDownloader(
            cookies=configutils.get_cookies_file() or None,
            client_id=configutils.get_spotify_client_id(),
            client_secret=configutils.get_spotify_client_secret(),
        )
        def _progress(current, total, name):
            self.progress.emit(current, total, name)
        result = self.selected_user.library.sync_songs(
            downloader=self._downloader,
            progress_callback=_progress,
        )
        self.result_ready.emit(result)


class SyncPlaylistsWorker(QThread):
    result_ready = pyqtSignal(object)
    progress = pyqtSignal(int, int, str)

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user
        self._downloader = None

    def cancel(self):
        if self._downloader:
            self._downloader.cancel()

    def run(self):
        from utils import configutils
        from downloaders.spotifydl import SpotifyDownloader
        self._downloader = SpotifyDownloader(
            cookies=configutils.get_cookies_file() or None,
            client_id=configutils.get_spotify_client_id(),
            client_secret=configutils.get_spotify_client_secret(),
        )
        def _progress(current, total, name):
            self.progress.emit(current, total, name)
        result = self.selected_user.library.sync_playlists(
            downloader=self._downloader,
            progress_callback=_progress,
        )
        self.result_ready.emit(result)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Library Sync")
        self.session_manager = SessionManager()
        self.users = self.session_manager.get_users()

        self.user_selection = QComboBox(self)
        for user in self.users:
            self.user_selection.addItem(f"{user.get_name()} ({user.get_id()})")
        self.user_selection.currentIndexChanged.connect(self.handle_user_selection)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        layout = QVBoxLayout(self.central_widget)
        layout.addWidget(self.user_selection)

        self.sync_button = QPushButton("Go", self)
        self.sync_button.clicked.connect(self.handle_user_selection)
        layout.addWidget(self.sync_button)

    def handle_user_selection(self, index=None):
        if index is None:
            index = self.user_selection.currentIndex()
        id_part = self.user_selection.itemText(index).split("(")[1].rstrip(")")  # Remove name, "(" and ")"
        user_id = id_part.strip()
        self.session_manager.set_session_id(user_id)
        self.open_sync_window()

    def open_sync_window(self):
        selected_user = self.session_manager.get_selected_user()
        sync_window = SyncWindow(selected_user)
        self.setCentralWidget(sync_window)
