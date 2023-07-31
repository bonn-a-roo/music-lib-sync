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

        # Your save_options() implementation here

        QMessageBox.information(self, "Options Saved", "Options saved successfully.")


class SyncWindow(QWidget):
    def __init__(self, selected_user):
        super().__init__()
        self.sync_thread = None
        self.setWindowTitle("Synchronization")

        self.selected_user = selected_user
        self.sync_button = QPushButton("Sync Music Library", self)
        self.sync_button.clicked.connect(self.sync_music_library)

        self.options_button = QPushButton("Options", self)
        self.options_button.clicked.connect(self.open_options_window)

        layout = QVBoxLayout()
        layout.addWidget(self.sync_button)
        layout.addWidget(self.options_button)

        self.setLayout(layout)

    def sync_music_library(self):
        self.sync_button.setEnabled(False)
        self.options_button.setEnabled(False)

        # Start the synchronization in a separate thread
        self.sync_thread = SyncWorker(self.selected_user)
        self.sync_thread.finished.connect(self.on_sync_finished)
        self.sync_thread.start()

    def on_sync_finished(self):
        # This method is called when the synchronization is completed
        self.sync_button.setEnabled(True)
        self.options_button.setEnabled(True)
        QMessageBox.information(self, "Sync Complete", "Music library synchronized successfully.")

    def open_options_window(self):
        options_window = OptionsWindow()
        options_window.show()


class SyncWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user

    def run(self):
        self.selected_user.library.synchronize()
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