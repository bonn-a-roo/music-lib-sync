import configparser
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QComboBox, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QLabel, \
    QLineEdit

from session_manager import SessionManager


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

        self.save_button = QPushButton("Save Options", self)
        self.save_button.clicked.connect(self.save_options)

        layout = QVBoxLayout()
        layout.addWidget(self.download_path_label)
        layout.addWidget(self.download_path_entry)
        layout.addWidget(self.browse_path_button)
        layout.addWidget(self.cookies_file_label)
        layout.addWidget(self.cookies_file_entry)
        layout.addWidget(self.browse_cookies_button)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

        # Load and display the saved values
        self.load_saved_values()

    def load_saved_values(self):
        config = configparser.ConfigParser()
        config.read('config.ini')

        # Get the saved download path from the config file
        download_path = config.get('Settings', 'download_path', fallback='')

        # Get the saved cookies file from the config file
        cookies_file = config.get('Settings', 'cookies_file', fallback='')

        # Populate the corresponding widgets with the saved values
        self.download_path_entry.setText(download_path)
        self.cookies_file_entry.setText(cookies_file)

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

        config = configparser.ConfigParser()

        # Read the existing configuration from the config.ini file
        config.read('config.ini')

        # Update the download path in the configuration
        config.set('Settings', 'download_path', download_path)

        # Add or update the cookies file path in the configuration
        if cookies_file:
            config.set('Settings', 'cookies_file', cookies_file)

        # Write the updated configuration back to the config.ini file
        with open('config.ini', 'w') as config_file:
            config.write(config_file)

        QMessageBox.information(self, "Options Saved", "Options saved successfully.")


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

        # Start the songs synchronization in a separate thread
        self.sync_thread = SyncSongsWorker(self.selected_user)
        self.sync_thread.finished.connect(self.on_sync_finished)
        self.sync_thread.start()

    def sync_playlists(self):
        self.sync_songs_button.setEnabled(False)
        self.sync_playlists_button.setEnabled(False)
        self.options_button.setEnabled(False)

        # Start the playlists synchronization in a separate thread
        self.sync_thread = SyncPlaylistsWorker(self.selected_user)
        self.sync_thread.finished.connect(self.on_sync_finished)
        self.sync_thread.start()

    def on_sync_finished(self):
        # This method is called when the synchronization is completed
        self.sync_songs_button.setEnabled(True)
        self.sync_playlists_button.setEnabled(True)
        self.options_button.setEnabled(True)
        QMessageBox.information(self, "Sync Complete", "Music library synchronized successfully.")

    def open_options_window(self):
        if not self.options_window:
            self.options_window = OptionsWindow()
        self.options_window.show()


class SyncSongsWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user

    def run(self):
        self.selected_user.library.sync_songs()
        self.finished.emit()


class SyncPlaylistsWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user

    def run(self):
        self.selected_user.library.sync_playlists()
        self.finished.emit()


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

    def handle_user_selection(self, index):
        id_part = self.user_selection.itemText(index).split("(")[1].rstrip(")")  # Remove name, "(" and ")"
        user_id = id_part.strip()
        self.session_manager.set_session_id(user_id)
        self.open_sync_window()

    def open_sync_window(self):
        selected_user = self.session_manager.get_selected_user()
        sync_window = SyncWindow(selected_user)
        self.setCentralWidget(sync_window)
