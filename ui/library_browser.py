"""Read-only collection browsing; sync and repair remain explicit separate actions."""
import os
import threading
from dataclasses import replace
from datetime import datetime

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QSplitter, QTableView, QVBoxLayout, QWidget)

from utils import configutils

THEME = """
QWidget { background: #090d12; color: #dce5eb; font-family: 'Segoe UI'; font-size: 13px; }
QListWidget, QPlainTextEdit { background: #0d131a; border: 1px solid #1c2b34; }
QListWidget::item { padding: 12px; }
QListWidget::item:selected { background: #13262d; color: #b9d7dc; border-left: 2px solid #78bdc9; }
QPushButton { border: 1px solid #2b3c45; border-radius: 4px; padding: 8px 12px; background: #0d131a; }
QPushButton:hover { background: #141e27; }
QPushButton:focus, QLineEdit:focus, QTableView:focus, QListWidget:focus { border: 1px solid #78bdc9; }
QPushButton:disabled { color: #647580; }
QPushButton:checked { border: 0; border-bottom: 2px solid #78bdc9; color: #bbdce1; }
QLineEdit { background: #0e151c; border: 1px solid #253840; border-radius: 4px; padding: 9px; }
QTableView { border: 0; gridline-color: #1c2b34; selection-background-color: #13262d; selection-color: #dce5eb; }
QHeaderView::section { background: #0d131a; color: #91a2ae; border: 0; border-bottom: 1px solid #1c2b34; padding: 10px; }
QSplitter::handle { background: #1c2b34; }
QLabel#collectionTitle { font-size: 28px; font-weight: 600; }
QLabel#summary { color: #91a2ae; }
"""


class TrackTableModel(QAbstractTableModel):
    HEADERS = ('#', 'Title', 'Artist', 'Album', 'Duration', 'Status')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks = ()

    def set_tracks(self, tracks):
        self.beginResetModel()
        self.tracks = tuple(tracks)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    @staticmethod
    def status(track):
        if track.transfer != 'idle':
            return track.transfer.title()
        if track.outcome == 'failed':
            return 'Failed · ' + track.presence.title()
        if track.presence == 'missing' and track.elsewhere_path:
            return 'Missing here · available elsewhere'
        return {'downloaded': 'Downloaded', 'missing': 'Missing', 'unknown': 'Unknown',
                'quarantined': 'Quarantined', 'failed': 'Failed'}.get(track.presence, track.presence.title())

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.tracks):
            return None
        track = self.tracks[index.row()]
        if role == Qt.UserRole:
            return track
        if role == Qt.ForegroundRole and index.column() == 5:
            return QColor('#90b6c0' if track.presence == 'downloaded' else '#91a2ae')
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            seconds = max(0, int(track.duration_ms or 0) // 1000)
            values = (str(index.row() + 1), track.name, track.artist, track.album,
                      f'{seconds // 60}:{seconds % 60:02d}', self.status(track))
            if role == Qt.ToolTipRole and index.column() == 5:
                return self.status(track) + ('\n' + str(track.local_path or track.elsewhere_path)
                                              if track.local_path or track.elsewhere_path else '')
            return values[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)


class TrackFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = ''
        self.status_filter = 'All'

    def set_search(self, text):
        self.search = text.casefold().strip()
        self.invalidateFilter()

    def set_status(self, status):
        self.status_filter = status
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        track = self.sourceModel().tracks[row]
        if self.search and self.search not in ' '.join(value or '' for value in (track.name, track.artist, track.album)).casefold():
            return False
        return (self.status_filter == 'All'
                or self.status_filter == 'Failed' and track.outcome == 'failed'
                or self.status_filter != 'Failed' and track.presence == self.status_filter.lower()
                or self.status_filter == 'Missing' and track.presence == 'quarantined')


class BrowseWorker(QThread):
    snapshot_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, selected_user, destination, parent=None, selected_key=None):
        super().__init__(parent)
        self.selected_user = selected_user
        self.destination = destination
        self.cancel_event = threading.Event()
        self.selected_key = selected_key
        self.selection_lock = threading.Lock()

    def prioritize(self, key):
        with self.selection_lock:
            self.selected_key = key

    def selected_collection(self):
        with self.selection_lock:
            return self.selected_key

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            for snapshot in self.selected_user.library.browse_collections(
                    self.destination, cancel_check=self.cancel_event.is_set, selected_key=self.selected_collection):
                if self.cancel_event.is_set():
                    break
                self.snapshot_ready.emit(snapshot)
        except BaseException as exc:
            if not self.cancel_event.is_set():
                self.failed.emit(str(exc) or type(exc).__name__)


class LibraryBrowser(QWidget):
    def __init__(self, selected_user):
        super().__init__()
        self.selected_user = selected_user
        self.worker = None
        self.snapshots = {}
        self.items = {}
        self.sync_window = None
        self.options_window = None
        self._closing = False
        self._seen = set()
        self._refresh_error = None
        self._pending_refresh = False
        self.setWindowTitle('Music Library')
        self.setStyleSheet(THEME)
        layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.addWidget(QLabel('Library'))
        self.collections = QListWidget()
        self.collections.setAccessibleName('Saved tracks and playlists')
        self.collections.currentItemChanged.connect(self._selection_changed)
        side.addWidget(self.collections)
        self.refresh_button = QPushButton('Refresh library')
        self.refresh_button.clicked.connect(self.refresh)
        side.addWidget(self.refresh_button)
        self.loading_label = QLabel('')
        self.loading_label.setWordWrap(True)
        side.addWidget(self.loading_label)
        self.splitter.addWidget(sidebar)
        main = QWidget()
        content = QVBoxLayout(main)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search current collection')
        self.search.setAccessibleName('Search current collection')
        top.addWidget(self.search, 1)
        top.addWidget(QLabel(selected_user.get_name()))
        options = QPushButton('Options')
        options.clicked.connect(self.open_options)
        top.addWidget(options)
        content.addLayout(top)
        self.title = QLabel('Your library')
        self.title.setObjectName('collectionTitle')
        self.title.setWordWrap(True)
        content.addWidget(self.title)
        self.summary = QLabel('Select Saved tracks or a playlist.')
        self.summary.setObjectName('summary')
        self.summary.setWordWrap(True)
        content.addWidget(self.summary)
        actions = QHBoxLayout()
        self.sync_button = QPushButton('Sync / repair')
        self.sync_button.setToolTip('Open existing batch sync and repair controls; browsing does not download audio.')
        self.sync_button.clicked.connect(self.open_sync)
        actions.addWidget(self.sync_button)
        self.folder_button = QPushButton('Open folder')
        self.folder_button.clicked.connect(self.open_folder)
        self.folder_button.setEnabled(False)
        actions.addWidget(self.folder_button)
        actions.addStretch()
        self.details_button = QPushButton('Details')
        self.details_button.setCheckable(True)
        actions.addWidget(self.details_button)
        content.addLayout(actions)
        filters = QHBoxLayout()
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for label in ('All', 'Downloaded', 'Missing', 'Failed'):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(label == 'All')
            button.clicked.connect(lambda checked, status=label: self.proxy.set_status(status))
            if label == 'Failed':
                button.setToolTip('No transfer failures are recorded by read-only browsing; sync results remain in Sync / repair.')
            self.filter_group.addButton(button)
            filters.addWidget(button)
        filters.addStretch()
        content.addLayout(filters)
        self.model = TrackTableModel(self)
        self.proxy = TrackFilterModel(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.set_search)
        self.table = QTableView()
        self.table.setAccessibleName('Collection tracks')
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 230)
        content.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setAccessibleName('Collection error and reconciliation details')
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(2000)
        self.details.setMaximumHeight(160)
        self.details.hide()
        self.details_button.toggled.connect(self.details.setVisible)
        content.addWidget(self.details)
        self.splitter.addWidget(main)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 900])
        QTimer.singleShot(0, self.refresh)

    def current_snapshot(self):
        item = self.collections.currentItem()
        return self.snapshots.get(item.data(Qt.UserRole)) if item else None

    def refresh(self):
        if self._closing or self.worker and self.worker.isRunning():
            return
        if self.sync_window and self.sync_window.sync_thread and self.sync_window.sync_thread.isRunning():
            self.loading_label.setText('Finish or cancel sync / repair before refreshing.')
            return
        self._seen = set()
        self._refresh_error = None
        for key, snapshot in tuple(self.snapshots.items()):
            self.snapshots[key] = replace(snapshot, stale=True, scan_complete=False)
            self._update_item(self.snapshots[key])
        self._render()
        self.refresh_button.setEnabled(False)
        self.sync_button.setEnabled(False)
        self.loading_label.setText('Loading Spotify metadata and checking existing files…')
        current = self.current_snapshot()
        self.worker = BrowseWorker(self.selected_user, configutils.get_download_path(), self,
                                   selected_key=current.key if current else None)
        self.worker.snapshot_ready.connect(self._apply_snapshot)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _update_item(self, snapshot):
        item = self.items.get(snapshot.key)
        if item is None:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, snapshot.key)
            self.items[snapshot.key] = item
            self.collections.addItem(item)
        item.setText(f'{snapshot.name}\n{snapshot.status}')
        item.setToolTip(snapshot.name + '\n' + (snapshot.error or snapshot.status))

    def _apply_snapshot(self, snapshot):
        if self._closing or self._pending_refresh:
            return
        self._seen.add(snapshot.key)
        previous = self.snapshots.get(snapshot.key)
        if previous and snapshot.metadata in ('not_loaded', 'loading', 'error'):
            snapshot = replace(snapshot, tracks=previous.tracks, stale=True, scan_complete=False,
                               refreshed_at=previous.refreshed_at)
        self.snapshots[snapshot.key] = snapshot
        self._update_item(snapshot)
        if self.collections.currentItem() is None:
            self.collections.setCurrentItem(self.items[snapshot.key])
        if self.current_snapshot() and self.current_snapshot().key == snapshot.key:
            self._render()
        if snapshot.error and not snapshot.stale:
            self.snapshots[snapshot.key] = replace(snapshot, stale=True, scan_complete=False)
            self._update_item(self.snapshots[snapshot.key])
            self._render()

    def _selection_changed(self, current, previous):
        if self.worker and current:
            self.worker.prioritize(current.data(Qt.UserRole))
        self._render()

    def _render(self):
        snapshot = self.current_snapshot()
        if snapshot is None:
            return
        self.title.setText(snapshot.name)
        timestamp = datetime.fromtimestamp(snapshot.refreshed_at).strftime('%Y-%m-%d %H:%M:%S') if snapshot.refreshed_at else 'Never'
        summary = (f'{snapshot.downloaded_count} / {snapshot.eligible_count} downloaded · '
                   f'{snapshot.missing_count} missing · {snapshot.status}\nLast refreshed: {timestamp}')
        if snapshot.stale:
            summary += ' · Stale — coverage unknown until refreshed'
        if snapshot.error:
            summary += '\n' + snapshot.error
        if snapshot.skipped_count:
            summary += f'\n{snapshot.skipped_count} unavailable / unsupported entries skipped'
        self.summary.setText(summary)
        self.model.set_tracks(snapshot.tracks)
        self.folder_button.setEnabled(os.path.isdir(snapshot.destination))
        self.folder_button.setToolTip(str(snapshot.destination))
        detail = f'Destination: {snapshot.destination}\nMetadata: {snapshot.metadata}\nCoverage: {snapshot.coverage}'
        if snapshot.error:
            detail += '\n' + snapshot.error
        if self._refresh_error:
            detail += '\nRefresh failed: ' + self._refresh_error
        detail += '\nDownloaded means a supported file with a matching Spotify ID, not verified recording identity.'
        detail += '\nRead-only browser: no transfer outcomes are recorded. Use Sync / repair for batch results.'
        self.details.setPlainText(detail)

    def _failed(self, message):
        if self._closing:
            return
        self._refresh_error = message
        for key, snapshot in tuple(self.snapshots.items()):
            self.snapshots[key] = replace(snapshot, metadata='error', stale=True, scan_complete=False, error=message)
            self._update_item(self.snapshots[key])
        self.loading_label.setText('Refresh failed: ' + message)
        self._render()
        if not self.snapshots:
            self.summary.setText('Could not load library: ' + message)
            self.details.setPlainText(message)

    def _finished(self):
        if self._closing:
            return
        self.refresh_button.setEnabled(True)
        self.sync_button.setEnabled(True)
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()
            return
        if not self._refresh_error:
            for key in tuple(self.items):
                if key not in self._seen:
                    item = self.items.pop(key)
                    self.snapshots.pop(key, None)
                    self.collections.takeItem(self.collections.row(item))
            self.loading_label.setText('Read-only library · no downloads started')
            self._render()

    def open_folder(self):
        snapshot = self.current_snapshot()
        if snapshot and os.path.isdir(snapshot.destination):
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(snapshot.destination))):
                self.loading_label.setText('Could not open the existing destination folder.')

    def open_sync(self):
        from ui.uimanager import SyncWindow
        if self.worker and self.worker.isRunning():
            return
        if self.sync_window is None:
            self.sync_window = SyncWindow(self.selected_user)
            self.sync_window.options_saved.connect(self._options_saved)
            self.sync_window.closed.connect(lambda: QTimer.singleShot(0, self.refresh))
            self.sync_window.operation_started.connect(self._invalidate_snapshots)
            self.sync_window.operation_finished.connect(self._options_saved)
        self.sync_window.show()
        self.sync_window.raise_()
        self.sync_window.activateWindow()

    def open_options(self):
        from ui.uimanager import OptionsWindow
        if self.options_window is None:
            self.options_window = OptionsWindow()
            self.options_window.saved.connect(self._options_saved)
        self.options_window.show()
        self.options_window.raise_()

    def _invalidate_snapshots(self):
        for key, snapshot in tuple(self.snapshots.items()):
            tracks = tuple(replace(track, presence='unknown', local_path=None, elsewhere_path=None)
                           for track in snapshot.tracks)
            self.snapshots[key] = replace(snapshot, tracks=tracks, stale=True, scan_complete=False)
            self._update_item(self.snapshots[key])
        self._render()

    def _options_saved(self):
        self._invalidate_snapshots()
        if self.worker and self.worker.isRunning():
            self._pending_refresh = True
            self.worker.cancel()
        else:
            self.refresh()

    def closeEvent(self, event):
        if self.sync_window and not self.sync_window.close():
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                self.loading_label.setText('Cancelling library refresh… close again when it stops.')
                event.ignore()
                return
        self._closing = True
        if self.options_window:
            self.options_window.close()
        event.accept()
