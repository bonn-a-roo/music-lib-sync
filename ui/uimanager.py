from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QMainWindow, QComboBox, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QLabel, \
    QLineEdit, QHBoxLayout

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

        layout = QVBoxLayout()
        layout.addWidget(self.sync_songs_button)
        layout.addWidget(self.sync_playlists_button)
        layout.addWidget(self.options_button)

        self.setLayout(layout)

    def sync_songs(self):
        self.sync_playlists_button.setEnabled(False)
        self.sync_songs_button.setEnabled(False)
        self.options_button.setEnabled(False)

        # Clean up old thread if it exists
        if self.sync_thread is not None:
            self.sync_thread.wait()

        # Start the songs synchronization in a separate thread
        self.sync_thread = SyncSongsWorker(self.selected_user)
        self.sync_thread.result_ready.connect(self.on_sync_finished)
        self.sync_thread.start()

    def sync_playlists(self):
        self.sync_songs_button.setEnabled(False)
        self.sync_playlists_button.setEnabled(False)
        self.options_button.setEnabled(False)

        # Clean up old thread if it exists
        if self.sync_thread is not None:
            self.sync_thread.wait()

        # Start the playlists synchronization in a separate thread
        self.sync_thread = SyncPlaylistsWorker(self.selected_user)
        self.sync_thread.result_ready.connect(self.on_sync_finished)
        self.sync_thread.start()

    def on_sync_finished(self, result: SyncResult):
        # This method is called when the synchronization is completed
        self.sync_songs_button.setEnabled(True)
        self.sync_playlists_button.setEnabled(True)
        self.options_button.setEnabled(True)

        if result.has_failures:
            QMessageBox.warning(self, "Sync Complete (with errors)", result.get_summary())
        else:
            QMessageBox.information(self, "Sync Complete", result.get_summary())

    def open_options_window(self):
        if not self.options_window:
            self.options_window = OptionsWindow()
        self.options_window.show()


class SyncSongsWorker(QThread):
    result_ready = pyqtSignal(object)

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user

    def run(self):
        result = self.selected_user.library.sync_songs()
        self.result_ready.emit(result)


class SyncPlaylistsWorker(QThread):
    result_ready = pyqtSignal(object)

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user

    def run(self):
        result = self.selected_user.library.sync_playlists()
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
