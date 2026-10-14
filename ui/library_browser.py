"""Read-only library browsing with scoped sync and queued explicit repair actions."""
import os
import threading
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QMessageBox, QProgressBar, QShortcut, QSizePolicy, QSlider, QSplitter, QStyle, QTableView,
                             QVBoxLayout, QWidget)

from model.library_state import CollectionKey, WorkerEvent
from ui.playback import PlaybackController, PlaybackEntry
from utils import configutils

THEME = """
QWidget { background: #090d12; color: #dce5eb; font-family: 'Segoe UI'; font-size: 13px; }
QListWidget, QPlainTextEdit { background: #0d131a; border: 1px solid #1c2b34; }
QListWidget::item { padding: 12px; border-left: 2px solid transparent; }
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
QTableView, QListWidget { outline: 0; }
QWidget#playerBar { border-top: 1px solid #1c2b34; }
QSlider::groove:horizontal { height: 4px; background: #1c2b34; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #78bdc9; border-radius: 2px; }
QSlider::handle:horizontal { background: #bbdce1; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QSlider::handle:horizontal:hover { background: #78bdc9; }
QSlider:focus { border: 1px solid #78bdc9; }
QScrollBar:vertical { background: #0d131a; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #0d131a; height: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2b3c45; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:horizontal { background: #2b3c45; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:hover { background: #3c5560; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class SeekSlider(QSlider):
    """Horizontal slider that seeks on click, drag and keyboard, not just handle drags."""
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.user_seeking = False

    def _value_at(self, x):
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(x), max(1, self.width()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() > 0 and self.isEnabled():
            self.user_seeking = True
            self._seek(self._value_at(event.pos().x()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.user_seeking:
            self._seek(self._value_at(event.pos().x()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.user_seeking:
            self.user_seeking = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def focusOutEvent(self, event):
        self.user_seeking = False
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        before = self.value()
        super().keyPressEvent(event)
        if self.value() != before:
            self.seek_requested.emit(self.value())

    def _seek(self, value):
        self.setValue(value)
        self.seek_requested.emit(value)


@dataclass(frozen=True)
class _MutationRequest:
    operation_id: str
    collection_key: CollectionKey
    track_ids: tuple[str, ...]
    destination_root: str
    label: str
    kind: str = 'collection'
    scope_keys: tuple[CollectionKey, ...] = ()

    @property
    def affected_keys(self):
        return self.scope_keys or (self.collection_key,)


class TrackTableModel(QAbstractTableModel):
    HEADERS = ('#', 'Title', 'Artist', 'Album', 'Duration', 'Status')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks = ()

    def set_tracks(self, tracks):
        self.beginResetModel()
        self.tracks = tuple(tracks)
        self.endResetModel()

    def update_tracks(self, tracks):
        tracks = tuple(tracks)
        if len(tracks) != len(self.tracks):
            self.set_tracks(tracks)
            return
        self.tracks = tracks
        if tracks:
            self.dataChanged.emit(self.index(0, 0), self.index(len(tracks) - 1, len(self.HEADERS) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    @staticmethod
    def status(track):
        if track.transfer != 'idle':
            status = track.transfer.title()
        elif track.outcome == 'failed':
            status = 'Failed · ' + track.presence.title()
        elif track.outcome == 'cancelled':
            status = 'Cancelled · ' + track.presence.title()
        elif track.presence == 'missing' and track.elsewhere_path:
            status = 'Missing here · available elsewhere'
        else:
            status = {'downloaded': 'Downloaded', 'missing': 'Missing', 'unknown': 'Unknown',
                      'quarantined': 'Quarantined', 'failed': 'Failed'}.get(
                          track.presence, track.presence.title())
        if track.playback in ('playing', 'paused', 'error'):
            playback = 'Playback error' if track.playback == 'error' else track.playback.title()
            return f'{status} · {playback}'
        return status

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
        self._mutation_queue = []
        self._active_job = None
        self._active_worker = None
        self._cancel_requested = False
        self._waiting_for_player_release = False
        self._close_when_player_quiesced = False
        self._job_progress = (0, 0)
        self._operation_summaries = {}
        self._operation_logs = {}
        self._playback_error_message = ''
        self._playback_state = 'stopped'
        self._legacy_mutation_active = False
        self.setWindowTitle('Music Library')
        self.setStyleSheet(THEME)
        layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.addWidget(QLabel('Library'))
        self.collections = QListWidget()
        self.collections.setAccessibleName('Saved tracks and playlists')
        self.collections.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.collections.setWordWrap(False)  # elide long names so the status line stays visible
        self.collections.setTextElideMode(Qt.ElideRight)
        self.collections.currentItemChanged.connect(self._selection_changed)
        side.addWidget(self.collections)
        self.refresh_button = QPushButton('Refresh library')
        self.refresh_button.clicked.connect(self.refresh)
        side.addWidget(self.refresh_button)
        self.loading_label = QLabel('')
        self.loading_label.setWordWrap(True)
        # Long messages wrap inside the sidebar instead of widening it.
        self.loading_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        job_actions = QHBoxLayout()
        self.sync_missing_button = QPushButton('Sync missing')
        self.sync_missing_button.clicked.connect(self.sync_missing)
        job_actions.addWidget(self.sync_missing_button)
        self.download_selected_button = QPushButton('Download selected')
        self.download_selected_button.clicked.connect(self.download_selected)
        job_actions.addWidget(self.download_selected_button)
        self.retry_failed_button = QPushButton('Retry failed')
        self.retry_failed_button.clicked.connect(self.retry_failed)
        job_actions.addWidget(self.retry_failed_button)
        self.sync_all_button = QPushButton('Sync all')
        self.sync_all_button.clicked.connect(self.sync_all)
        job_actions.addWidget(self.sync_all_button)
        self.repair_library_button = QPushButton('Repair Library')
        self.repair_library_button.clicked.connect(self.repair_library)
        job_actions.addWidget(self.repair_library_button)
        self.cancel_jobs_button = QPushButton('Cancel jobs')
        self.cancel_jobs_button.clicked.connect(self.cancel_jobs)
        job_actions.addWidget(self.cancel_jobs_button)
        content.addLayout(job_actions)
        self.activity_label = QLabel('')
        self.activity_label.setObjectName('summary')
        self.activity_label.hide()
        content.addWidget(self.activity_label)
        self.activity_progress = QProgressBar()
        self.activity_progress.setAccessibleName('Library sync progress')
        self.activity_progress.setFormat('%v / %m tracks')
        self.activity_progress.hide()
        content.addWidget(self.activity_progress)
        actions = QHBoxLayout()
        self.sync_button = QPushButton('Sync / repair')
        self.sync_button.setToolTip('Open the retained batch sync and repair controls.')
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
                button.setToolTip('Tracks whose latest transfer attempt failed, independent of local file presence.')
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
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_controls())
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 70)
        # Status text such as "Downloaded · Playback error" must never be clipped.
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalScrollBar().setEnabled(True)
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
        self.table.doubleClicked.connect(self._play_table_index)
        for key in (Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(key), self.table, context=Qt.WidgetShortcut,
                      activated=lambda: self._play_table_index(self.table.currentIndex()))
        QShortcut(QKeySequence(Qt.Key_Space), self.table, context=Qt.WidgetShortcut,
                  activated=self.toggle_playback)

        self.playback = PlaybackController(self)
        self.playback.current_changed.connect(self._playback_track_changed)
        self.playback.state_changed.connect(self._playback_state_changed)
        self.playback.track_state_changed.connect(self._playback_track_state_changed)
        self.playback.position_changed.connect(self._playback_position_changed)
        self.playback.duration_changed.connect(self._playback_duration_changed)
        self.playback.error_occurred.connect(self._playback_error)
        player_bar = QWidget(self)
        player_bar.setObjectName('playerBar')
        player_layout = QHBoxLayout(player_bar)
        player_layout.setContentsMargins(6, 3, 6, 3)
        self.player_track_label = QLabel('Nothing playing')
        self.player_track_label.setObjectName('summary')
        self.player_track_label.setMinimumWidth(180)
        player_layout.addWidget(self.player_track_label)
        self.previous_button = QPushButton('Previous')
        self.previous_button.clicked.connect(self.playback.previous)
        player_layout.addWidget(self.previous_button)
        self.play_button = QPushButton('Play')
        self.play_button.clicked.connect(self.toggle_playback)
        player_layout.addWidget(self.play_button)
        self.next_button = QPushButton('Next')
        self.next_button.clicked.connect(self.playback.next)
        player_layout.addWidget(self.next_button)
        self.position_slider = SeekSlider()
        self.position_slider.setAccessibleName('Playback position')
        self.position_slider.setRange(0, 0)
        self.position_slider.seek_requested.connect(self.playback.seek)
        player_layout.addWidget(self.position_slider, 1)
        self.playback_time_label = QLabel('0:00 / 0:00')
        player_layout.addWidget(self.playback_time_label)
        player_layout.addWidget(QLabel('Volume'))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setAccessibleName('Playback volume')
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(120)
        self.volume_slider.valueChanged.connect(self.playback.set_volume)
        player_layout.addWidget(self.volume_slider)
        layout.addWidget(player_bar)
        self.playback.set_volume(self.volume_slider.value())
        self._update_controls()
        QTimer.singleShot(0, self.refresh)

    def current_snapshot(self):
        item = self.collections.currentItem()
        return self.snapshots.get(item.data(Qt.UserRole)) if item else None

    @staticmethod
    def _can_mutate_snapshot(snapshot):
        return bool(snapshot and snapshot.metadata == 'ready' and snapshot.scan_complete
                    and not snapshot.stale and not snapshot.error and snapshot.coverage != 'unknown')

    def _selected_track_ids(self):
        if not hasattr(self, 'table') or not self.table.selectionModel():
            return ()
        ids = []
        for proxy_index in self.table.selectionModel().selectedRows():
            source_index = self.proxy.mapToSource(proxy_index)
            if source_index.isValid():
                ids.append(self.model.tracks[source_index.row()].track_id)
        return tuple(dict.fromkeys(track_id for track_id in ids if track_id))

    def _batch_worker_running(self):
        return bool(self._legacy_mutation_active or
                    self.sync_window and self.sync_window.sync_thread
                    and self.sync_window.sync_thread.isRunning())

    def _can_start_batch_operation(self):
        available = bool(not self._closing and self._active_job is None and not self._mutation_queue
                         and not (self.worker and self.worker.isRunning()))
        if not available:
            return False
        if not self.playback.is_quiesced:
            self.playback.quiesce()
            self.loading_label.setText('Stopping local playback; retry the batch operation when the player is stopped.')
            return False
        return True

    def _update_controls(self):
        busy = self._active_job is not None or bool(self._mutation_queue)
        refreshing = bool(self.worker and self.worker.isRunning())
        snapshot = self.current_snapshot() if hasattr(self, 'collections') else None
        can_mutate = self._can_mutate_snapshot(snapshot)
        legacy_busy = self._batch_worker_running()
        missing = bool(can_mutate and any(track.presence in ('missing', 'quarantined')
                                          for track in snapshot.tracks))
        failed = bool(can_mutate and any(track.outcome == 'failed'
                                         and track.presence in ('missing', 'quarantined')
                                         for track in snapshot.tracks))
        scoped_allowed = not refreshing and not legacy_busy and not self._closing
        self.refresh_button.setEnabled(not busy and not refreshing and not legacy_busy and not self._closing)
        self.sync_missing_button.setEnabled(scoped_allowed and missing)
        self.download_selected_button.setEnabled(scoped_allowed and can_mutate and bool(self._selected_track_ids()))
        self.retry_failed_button.setEnabled(scoped_allowed and failed)
        sync_all_available = any(
            self._can_mutate_snapshot(item) and any(track.presence in ('missing', 'quarantined')
                                                    for track in item.tracks)
            for item in self.snapshots.values())
        self.sync_all_button.setEnabled(scoped_allowed and sync_all_available)
        repair_queued = bool((self._active_job and self._active_job.kind == 'repair')
                             or any(job.kind == 'repair' for job in self._mutation_queue))
        self.repair_library_button.setEnabled(scoped_allowed and bool(self.snapshots) and not repair_queued)
        self.cancel_jobs_button.setEnabled(busy and not self._closing)
        self.sync_button.setEnabled(not busy and not refreshing and not self._closing)

    def refresh(self):
        if self._closing or self.worker and self.worker.isRunning():
            return
        if self._active_job or self._mutation_queue or self._legacy_mutation_active:
            self.loading_label.setText('Finish or cancel active sync / repair before refreshing.')
            self._update_controls()
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
        self._update_controls()

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
        elif previous and snapshot.metadata == 'ready' and snapshot.scan_complete:
            previous_tracks = {track.track_id: track for track in previous.tracks}
            previous_playback = {}
            occurrences = {}
            for old in previous.tracks:
                ordinal = occurrences.get(old.track_id, 0)
                previous_playback[(old.track_id, ordinal)] = old.playback
                occurrences[old.track_id] = ordinal + 1
            merged_tracks = []
            occurrences = {}
            for track in snapshot.tracks:
                old = previous_tracks.get(track.track_id)
                if (old and old.outcome in ('failed', 'cancelled')
                        and track.presence in ('missing', 'quarantined')):
                    track = replace(track, outcome=old.outcome)
                ordinal = occurrences.get(track.track_id, 0)
                playback = previous_playback.get((track.track_id, ordinal), 'stopped')
                if playback != 'stopped' and (track.local_path or track.elsewhere_path):
                    track = replace(track, playback=playback)
                occurrences[track.track_id] = ordinal + 1
                merged_tracks.append(track)
            outcome = previous.outcome
            if snapshot.missing_count == 0 and outcome in ('failed', 'cancelled'):
                outcome = None
            snapshot = replace(snapshot, tracks=tuple(merged_tracks), outcome=outcome)
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
        self._update_controls()

    def _selection_changed(self, current, previous):
        if self.worker and current:
            self.worker.prioritize(current.data(Qt.UserRole))
        self._render()

    def _render(self, reset_model=True):
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
        if reset_model:
            self.model.set_tracks(snapshot.tracks)
        else:
            self.model.update_tracks(snapshot.tracks)
            self.proxy.invalidateFilter()
        self.folder_button.setEnabled(os.path.isdir(snapshot.destination))
        self.folder_button.setToolTip(str(snapshot.destination))
        detail = f'Destination: {snapshot.destination}\nMetadata: {snapshot.metadata}\nCoverage: {snapshot.coverage}'
        if snapshot.error:
            detail += '\n' + snapshot.error
        if self._refresh_error:
            detail += '\nRefresh failed: ' + self._refresh_error
        if self._playback_error_message:
            detail += '\nPlayback error: ' + self._playback_error_message
        detail += '\nDownloaded means a supported file with a matching Spotify ID, not verified recording identity.'
        detail += '\nScoped sync and transfer outcomes are shown by track ID; batch sync / repair remains available separately.'
        if snapshot.key in self._operation_summaries:
            detail += '\n\nLast operation:\n' + self._operation_summaries[snapshot.key]
        logs = self._operation_logs.get(snapshot.key)
        if logs:
            detail += '\n\nActivity details:\n' + '\n'.join(logs)
        self.details.setPlainText(detail)
        self._update_controls()

    def _play_table_index(self, proxy_index):
        if not proxy_index.isValid():
            return
        if self._closing or self.playback.is_quiescing or self._batch_worker_running():
            self.loading_label.setText('Playback is stopping for a library mutation; try again when it finishes.')
            return
        snapshot = self.current_snapshot()
        source_index = self.proxy.mapToSource(proxy_index)
        if snapshot is None or not source_index.isValid():
            return
        selected = self.model.tracks[source_index.row()]
        entries = []
        start_index = None
        for view_row in range(self.proxy.rowCount()):
            mapped = self.proxy.mapToSource(self.proxy.index(view_row, 0))
            if not mapped.isValid():
                continue
            track = self.model.tracks[mapped.row()]
            path = track.local_path or track.elsewhere_path
            if path and os.path.isfile(path):
                if mapped.row() == source_index.row():
                    start_index = len(entries)
                entries.append(PlaybackEntry(snapshot.key, track.track_id, path,
                                             track.name or 'Unknown title', track.artist or 'Unknown artist',
                                             mapped.row()))
        if start_index is None:
            message = 'This track has no available local audio file; playback will not start a download.'
            self._playback_error_message = message
            self.loading_label.setText(message)
            self._playback_track_state_changed(
                PlaybackEntry(snapshot.key, selected.track_id, '', selected.name or '',
                              selected.artist or '', source_index.row()), 'error')
            return
        self._playback_error_message = ''
        if not self.playback.play_queue(entries, start_index):
            self.loading_label.setText('Playback is unavailable while a library mutation is being prepared.')
            return
        self._render(reset_model=False)

    def toggle_playback(self):
        if self.playback.current_entry is None:
            current = self.table.currentIndex()
            if current.isValid():
                self._play_table_index(current)
            return
        if self._playback_state == 'error':
            self.playback.retry_current()
        else:
            self.playback.toggle()

    @staticmethod
    def _format_time(milliseconds):
        seconds = max(0, int(milliseconds or 0) // 1000)
        minutes, seconds = divmod(seconds, 60)
        return f'{minutes}:{seconds:02d}'

    def _playback_track_changed(self, entry):
        self._playback_error_message = ''
        if entry is None:
            self.player_track_label.setText('Nothing playing')
            self.play_button.setText('Play')
            self.playback_time_label.setText('0:00 / 0:00')
            self.position_slider.setRange(0, 0)
        else:
            self.player_track_label.setText(f'{entry.title} — {entry.artist}')
            self.player_track_label.setToolTip(entry.path)
        snapshot = self.current_snapshot()
        if snapshot is not None:
            self._render(reset_model=False)

    def _playback_state_changed(self, state):
        self._playback_state = state
        self.play_button.setText({'playing': 'Pause', 'loading': 'Loading…',
                                  'decoding': 'Preparing…'}.get(state, 'Play'))
        enabled = bool(self.playback.queue)
        self.previous_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)
        if state == 'playing':
            self._playback_error_message = ''

    def _playback_track_state_changed(self, entry, state):
        if state not in ('stopped', 'playing', 'paused', 'error'):
            return
        snapshot = self.snapshots.get(entry.collection_key)
        if snapshot is None:
            return
        row = entry.row_index
        if not 0 <= row < len(snapshot.tracks) or snapshot.tracks[row].track_id != entry.track_id:
            return
        track = snapshot.tracks[row]
        if track.playback == state:
            return
        tracks = list(snapshot.tracks)
        tracks[row] = replace(track, playback=state)
        snapshot = replace(snapshot, tracks=tuple(tracks))
        self.snapshots[entry.collection_key] = snapshot
        self._update_item(snapshot)
        if self.current_snapshot() and self.current_snapshot().key == entry.collection_key:
            self._render(reset_model=False)

    def _playback_position_changed(self, position):
        if not self.position_slider.user_seeking:
            self.position_slider.setValue(position)
        self.playback_time_label.setText(
            f'{self._format_time(position)} / {self._format_time(self.playback.duration)}')

    def _playback_duration_changed(self, duration):
        self.position_slider.setRange(0, max(0, duration))
        self.playback_time_label.setText(
            f'{self._format_time(self.playback.position)} / {self._format_time(duration)}')

    def _playback_error(self, message):
        self._playback_error_message = message
        self.loading_label.setText('Playback error: ' + message)
        if self.current_snapshot() is not None:
            self._render(reset_model=False)

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
        self._update_controls()
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
            self.loading_label.setText('Library ready · sync actions available')
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
        if self._active_job or self._mutation_queue:
            self.loading_label.setText('Finish or cancel queued library jobs before opening batch sync / repair.')
            return
        if self.sync_window is None:
            self.sync_window = SyncWindow(
                self.selected_user, operation_guard=self._can_start_batch_operation)
            self.sync_window.options_saved.connect(self._options_saved)
            self.sync_window.closed.connect(lambda: QTimer.singleShot(0, self.refresh))
            self.sync_window.operation_started.connect(self._legacy_operation_started)
            self.sync_window.operation_finished.connect(self._legacy_operation_finished)
        self.sync_window.show()
        self.sync_window.raise_()
        self.sync_window.activateWindow()

    def repair_library(self):
        if self._closing or self._batch_worker_running() or self.worker and self.worker.isRunning():
            self.loading_label.setText('Finish the current refresh or batch operation before queuing Repair Library.')
            return
        if not self.snapshots:
            self.loading_label.setText('Load the library before starting Repair Library.')
            return
        if ((self._active_job and self._active_job.kind == 'repair')
                or any(job.kind == 'repair' for job in self._mutation_queue)):
            self.loading_label.setText('Repair Library is already active or queued.')
            return
        answer = QMessageBox.question(
            self, 'Repair Library',
            'Repair the whole library? This may flatten nested track folders, move unreadable or '
            'wrong-length audio into _rejected, and add missing metadata tags. Originals are preserved.',
            QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        # The modal confirmation runs a nested event loop: refresh or a batch job
        # may have started while it was open, so recheck before queueing mutation.
        if self._closing or self._batch_worker_running() or self.worker and self.worker.isRunning():
            self.loading_label.setText('Library state changed during confirmation; finish the refresh or batch operation and try again.')
            return
        if ((self._active_job and self._active_job.kind == 'repair')
                or any(job.kind == 'repair' for job in self._mutation_queue)):
            self.loading_label.setText('Repair Library is already active or queued.')
            return
        scope_keys = tuple(self.snapshots)
        root = os.path.abspath(os.path.expanduser(os.fspath(configutils.get_download_path())))
        request = _MutationRequest(uuid4().hex, scope_keys[0], (), root, 'Repair Library',
                                   kind='repair', scope_keys=scope_keys)
        self._mutation_queue.append(request)
        self.loading_label.setText('Queued Repair Library for the current destination.')
        self._update_activity_view()
        self._update_controls()
        if self._active_job is None:
            self._start_next_mutation()

    def sync_all(self):
        if self._closing or self._batch_worker_running() or self.worker and self.worker.isRunning():
            self.loading_label.setText('Finish the current refresh or batch operation before queueing Sync all.')
            return
        snapshots = tuple(self.snapshots.values())
        excluded = {'restricted': 0, 'error': 0, 'incomplete': 0, 'empty': 0, 'complete': 0}
        targets = []
        for snapshot in snapshots:
            if snapshot.metadata == 'restricted':
                excluded['restricted'] += 1
                continue
            if snapshot.metadata == 'error' or snapshot.error:
                excluded['error'] += 1
                continue
            if (snapshot.metadata != 'ready' or not snapshot.scan_complete or snapshot.stale
                    or snapshot.coverage == 'unknown'):
                excluded['incomplete'] += 1
                continue
            if snapshot.eligible_count == 0:
                excluded['empty'] += 1
                continue
            track_ids = tuple(dict.fromkeys(
                track.track_id for track in snapshot.tracks
                if track.presence in ('missing', 'quarantined') and track.track_id))
            if track_ids:
                targets.append((snapshot, track_ids))
            else:
                excluded['complete'] += 1
        if not targets:
            reasons = ', '.join(f'{count} {name}' for name, count in excluded.items() if count)
            self.loading_label.setText(
                'Sync all found no missing tracks' + (f' ({reasons}).' if reasons else '.'))
            return

        # One destination snapshot applies to the entire request, even if Options
        # changes while the queued jobs are being promoted.
        root = os.path.abspath(os.path.expanduser(os.fspath(configutils.get_download_path())))
        queued_collections = 0
        queued_tracks = 0
        already_covered_collections = 0
        already_covered_tracks = 0
        for snapshot, track_ids in targets:
            request = self._enqueue_mutation(snapshot.key, track_ids, 'Sync all',
                                             destination_root=root, start=False)
            if request is None:
                already_covered_collections += 1
                already_covered_tracks += len(track_ids)
            else:
                queued_collections += 1
                queued_tracks += len(request.track_ids)
                already_covered_tracks += len(track_ids) - len(request.track_ids)
        report = [f'Sync all queued {queued_collections} collections ({queued_tracks} track IDs)']
        report.extend(f'{count} {name}' for name, count in excluded.items() if count)
        if already_covered_tracks:
            report.append(f'{already_covered_tracks} track IDs already active or queued')
        self.loading_label.setText('; '.join(report) + '.')
        if self._active_job is None and self._mutation_queue:
            self._start_next_mutation()

    def sync_missing(self):
        snapshot = self.current_snapshot()
        if not self._can_mutate_snapshot(snapshot):
            self.loading_label.setText('Refresh this collection successfully before syncing.')
            return
        track_ids = tuple(dict.fromkeys(
            track.track_id for track in snapshot.tracks
            if track.presence in ('missing', 'quarantined') and track.track_id))
        if not track_ids:
            self.loading_label.setText('This collection has no missing tracks.')
            return
        self._enqueue_mutation(snapshot.key, track_ids, 'Sync missing')

    def download_selected(self):
        snapshot = self.current_snapshot()
        if not self._can_mutate_snapshot(snapshot):
            self.loading_label.setText('Refresh this collection successfully before downloading selected tracks.')
            return
        track_ids = self._selected_track_ids()
        if not track_ids:
            self.loading_label.setText('Select one or more tracks first.')
            return
        self._enqueue_mutation(snapshot.key, track_ids, 'Download selected')

    def retry_failed(self):
        snapshot = self.current_snapshot()
        if not self._can_mutate_snapshot(snapshot):
            self.loading_label.setText('Refresh this collection successfully before retrying.')
            return
        track_ids = tuple(dict.fromkeys(
            track.track_id for track in snapshot.tracks
            if track.outcome == 'failed' and track.presence in ('missing', 'quarantined')
            and track.track_id))
        if not track_ids:
            self.loading_label.setText('There are no failed, still-missing tracks to retry.')
            return
        self._enqueue_mutation(snapshot.key, track_ids, 'Retry failed')

    def _enqueue_mutation(self, collection_key, track_ids, label, destination_root=None, start=True):
        if self._closing or self._batch_worker_running() or self.worker and self.worker.isRunning():
            self.loading_label.setText('Finish the current refresh or batch operation before queueing a sync.')
            return
        snapshot = self.snapshots.get(collection_key)
        if not self._can_mutate_snapshot(snapshot):
            self.loading_label.setText('The collection snapshot is stale or incomplete; refresh before syncing.')
            return
        requested = tuple(dict.fromkeys(track_id for track_id in track_ids if track_id))
        covered = set()
        for job in ([self._active_job] if self._active_job else []) + self._mutation_queue:
            if job.collection_key == collection_key:
                covered.update(job.track_ids)
        requested = tuple(track_id for track_id in requested if track_id not in covered)
        if not requested:
            self.loading_label.setText('Those tracks are already active or queued for this collection.')
            return None
        root = configutils.get_download_path() if destination_root is None else destination_root
        root = os.path.abspath(os.path.expanduser(os.fspath(root)))
        request = _MutationRequest(uuid4().hex, collection_key, requested, root, label)
        self._mutation_queue.append(request)
        for track_id in requested:
            self._apply_mutation_event(
                WorkerEvent(request.operation_id, collection_key, 'queued', track_id=track_id,
                            total=len(requested)), request=request)
        self._apply_mutation_event(
            WorkerEvent(request.operation_id, collection_key, 'queued', total=len(requested)),
            request=request)
        self.loading_label.setText(f'Queued {label.lower()} for {snapshot.name}.')
        self._update_activity_view()
        self._update_controls()
        if self._active_job is None and start:
            self._start_next_mutation()
        return request

    def _find_event_request(self, event):
        if self._active_job and self._active_job.operation_id == event.operation_id:
            return self._active_job
        return next((job for job in self._mutation_queue
                     if job.operation_id == event.operation_id), None)

    def _apply_mutation_event(self, event, request=None, worker_event=False):
        if not isinstance(event, WorkerEvent):
            return False
        request = request or (self._active_job if worker_event else self._find_event_request(event))
        if (request is None or worker_event and request is not self._active_job
                or not event.belongs_to(request.operation_id, request.collection_key)):
            return False
        snapshot = self.snapshots.get(request.collection_key)
        if snapshot is None:
            return False
        is_active = request is self._active_job
        target_ids = set(request.track_ids)
        tracks = []
        stale = snapshot.stale
        scan_complete = snapshot.scan_complete
        current_root = os.path.abspath(os.path.expanduser(os.fspath(configutils.get_download_path())))
        same_root = os.path.normcase(current_root) == os.path.normcase(request.destination_root)

        for track in snapshot.tracks:
            if event.track_id is not None and track.track_id != event.track_id:
                tracks.append(track)
                continue
            if event.track_id is None and event.phase in ('success', 'failure', 'cancelled'):
                if track.track_id in target_ids and track.transfer != 'idle':
                    track = replace(track, transfer='idle',
                                    outcome='cancelled' if event.phase == 'cancelled' else track.outcome)
                tracks.append(track)
                continue
            if event.track_id is None:
                tracks.append(track)
                continue

            if event.phase == 'queued':
                track = replace(track, transfer='queued')
            elif event.phase in ('downloading', 'cancelling'):
                track = replace(track, transfer=event.phase)
            elif event.phase == 'success':
                local_destination = (same_root and event.final_path and
                                     os.path.normcase(os.path.dirname(os.path.abspath(event.final_path))) ==
                                     os.path.normcase(os.path.abspath(snapshot.destination)))
                if local_destination:
                    track = replace(track, presence='downloaded', local_path=event.final_path,
                                    elsewhere_path=None, transfer='idle', outcome='succeeded')
                else:
                    track = replace(track, presence='unknown', local_path=None,
                                    elsewhere_path=event.final_path, transfer='idle', outcome='succeeded')
                    stale, scan_complete = True, False
            elif event.phase == 'failure':
                track = replace(track, transfer='idle', outcome='failed')
            elif event.phase == 'skip':
                if event.final_path and os.path.isfile(event.final_path):
                    local_destination = (same_root and
                                         os.path.normcase(os.path.dirname(os.path.abspath(event.final_path))) ==
                                         os.path.normcase(os.path.abspath(snapshot.destination)))
                    if local_destination:
                        track = replace(track, presence='downloaded', local_path=event.final_path,
                                        elsewhere_path=None, transfer='idle', outcome=None)
                    else:
                        track = replace(track, presence='unknown', local_path=None,
                                        elsewhere_path=event.final_path, transfer='idle', outcome=None)
                        stale, scan_complete = True, False
                else:
                    track = replace(track, transfer='idle', outcome=None)
            elif event.phase == 'cancelled':
                track = replace(track, transfer='idle', outcome='cancelled')
            tracks.append(track)

        operation = snapshot.operation
        outcome = snapshot.outcome
        terminal = event.phase in ('success', 'failure', 'cancelled') and event.track_id is None
        active_same_collection = bool(self._active_job and
                                      self._active_job.collection_key == request.collection_key and not is_active)
        queued_same_collection = any(job.collection_key == request.collection_key
                                     for job in self._mutation_queue)
        if event.phase == 'queued':
            if is_active or not active_same_collection:
                operation = 'queued'
        elif event.phase in ('start', 'syncing', 'downloading', 'cancelling'):
            if is_active:
                operation = 'syncing' if event.phase == 'start' else event.phase
        elif terminal:
            if is_active or not active_same_collection:
                operation = 'queued' if queued_same_collection else 'idle'
                outcome = {'success': 'succeeded', 'failure': 'failed',
                           'cancelled': 'cancelled'}[event.phase]

        if is_active and event.total and event.track_id is None:
            self._job_progress = (event.completed, event.total)
        updated = replace(snapshot, tracks=tuple(tracks), operation=operation, outcome=outcome,
                          stale=stale, scan_complete=scan_complete)
        self.snapshots[request.collection_key] = updated
        self._update_item(updated)
        if self.current_snapshot() and self.current_snapshot().key == request.collection_key:
            self._render(reset_model=False)
        self._update_activity_view()
        self._update_controls()
        return True

    def _start_next_mutation(self):
        if self._closing or self._active_job is not None or not self._mutation_queue:
            self._update_activity_view()
            self._update_controls()
            return
        request = self._mutation_queue.pop(0)
        self._active_job = request
        self._cancel_requested = False
        self._job_progress = (0, len(request.track_ids))
        for key in request.affected_keys:
            self._operation_logs.setdefault(key, deque(maxlen=2000))
        self._update_activity_view()
        self._update_controls()
        try:
            from ui.uimanager import SyncWorker, YoutubeDownloader
            if request.kind == 'repair':
                if not self.playback.is_quiesced:
                    self._waiting_for_player_release = True
                    self.playback.quiesced.connect(self._repair_after_playback_release)
                    self.playback.quiesce()
                    self._update_activity_view()
                    return
                self.playback.quiesce()
                self._start_repair_worker(request, SyncWorker)
                return
            downloader = YoutubeDownloader(cookies_file=configutils.get_cookies_file() or None)
            problems = downloader.preflight()
            if problems:
                self._fail_to_start(request, 'Download prerequisites missing:\n' + '\n'.join(problems))
                return
            worker = SyncWorker(self.selected_user, 'collection', downloader,
                                collection_key=request.collection_key, track_ids=request.track_ids,
                                operation_id=request.operation_id, download_path=request.destination_root)
            self._start_mutation_worker(worker)
        except Exception as error:
            self._fail_to_start(request, str(error) or type(error).__name__)

    def _repair_after_playback_release(self):
        try:
            self.playback.quiesced.disconnect(self._repair_after_playback_release)
        except (TypeError, RuntimeError):
            pass
        if not self._waiting_for_player_release:
            return
        self._waiting_for_player_release = False
        request = self._active_job
        if self._closing or request is None or request.kind != 'repair':
            if not self._closing:
                self.playback.resume()
            return
        try:
            from ui.uimanager import SyncWorker
            self._start_repair_worker(request, SyncWorker)
        except Exception as error:
            self._fail_to_start(request, str(error) or type(error).__name__)

    def _start_repair_worker(self, request, worker_type):
        worker = worker_type(self.selected_user, 'repair', operation_id=request.operation_id,
                             download_path=request.destination_root)
        self._invalidate_snapshots()
        self._start_mutation_worker(worker)

    def _start_mutation_worker(self, worker):
        worker.setParent(self)
        worker.event_ready.connect(self._mutation_event_ready)
        worker.result_ready.connect(self._mutation_result_ready)
        worker.failed.connect(self._mutation_failed)
        worker.progress.connect(self._mutation_progress)
        worker.log_line.connect(self._mutation_log_line)
        worker.finished.connect(self._mutation_finished)
        self._active_worker = worker
        worker.start()
        self._update_activity_view()

    def _fail_to_start(self, request, message):
        if request.kind == 'repair':
            self._waiting_for_player_release = False
            try:
                self.playback.quiesced.disconnect(self._repair_after_playback_release)
            except (TypeError, RuntimeError):
                pass
            self.playback.resume()
        for key in request.affected_keys:
            self._operation_summaries[key] = message
        if request.kind == 'repair':
            self._render(reset_model=False)
        else:
            self._apply_mutation_event(
                WorkerEvent(request.operation_id, request.collection_key, 'failure', error=message),
                request=request)
        self._active_job = None
        self._active_worker = None
        self._cancel_requested = False
        self.loading_label.setText('Operation not started: ' + message)
        self._update_activity_view()
        self._update_controls()
        if self._mutation_queue:
            QTimer.singleShot(0, self._start_next_mutation)
        elif not self._closing:
            # A failed final queued job is still the queue-drain boundary. It may
            # follow earlier successful jobs or an Options change that invalidated coverage.
            self._pending_refresh = False
            QTimer.singleShot(0, self.refresh)

    def _mutation_event_ready(self, event):
        self._apply_mutation_event(event, worker_event=True)

    def _mutation_progress(self, current, total, _name):
        if self._active_job is None or total <= 0:
            return
        self._job_progress = (current, total)
        self._update_activity_view()

    def _mutation_result_ready(self, result):
        request = self._active_job
        if request is None:
            return
        summary = result.get_summary() if hasattr(result, 'get_summary') else str(result)
        for key in request.affected_keys:
            self._operation_summaries[key] = summary
        if self.current_snapshot() and self.current_snapshot().key in request.affected_keys:
            self._render(reset_model=False)

    def _mutation_failed(self, message):
        request = self._active_job
        if request is None:
            return
        message = message or f'{request.label} failed'
        for key in request.affected_keys:
            self._operation_summaries[key] = message
        if request.kind == 'repair':
            if self.current_snapshot() and self.current_snapshot().key in request.affected_keys:
                self._render(reset_model=False)
        else:
            self._apply_mutation_event(
                WorkerEvent(request.operation_id, request.collection_key, 'failure', error=message),
                request=request, worker_event=True)
        self.loading_label.setText('Repair failed: ' + message if request.kind == 'repair'
                                   else 'Sync failed: ' + message)

    def _mutation_log_line(self, line):
        request = self._active_job
        if request is None:
            return
        self._operation_logs.setdefault(request.collection_key, deque(maxlen=2000)).append(line)
        if self.current_snapshot() and self.current_snapshot().key == request.collection_key:
            self._render(reset_model=False)

    def _mutation_finished(self):
        worker = self.sender()
        if worker is not self._active_worker:
            return
        request = self._active_job
        self._active_job = None
        self._active_worker = None
        self._cancel_requested = False
        if request and request.kind == 'repair':
            self.playback.resume()
        worker.deleteLater()
        self._update_activity_view()
        self._update_controls()
        if self._closing:
            return
        if self._mutation_queue:
            QTimer.singleShot(0, self._start_next_mutation)
            return
        self._pending_refresh = False
        QTimer.singleShot(0, self.refresh)

    def _update_activity_view(self):
        request = self._active_job
        if request is None:
            self.activity_label.hide()
            self.activity_progress.hide()
            self.cancel_jobs_button.setText('Cancel jobs')
            return
        snapshot = self.snapshots.get(request.collection_key)
        if request.kind == 'repair':
            operation = ('Cancelling' if self._cancel_requested else
                         'Waiting for playback' if self._waiting_for_player_release else
                         'Repairing' if self._active_worker else 'Queued')
            scope_name = 'whole library'
        else:
            operation = snapshot.operation.title() if snapshot else 'Syncing'
            scope_name = snapshot.name if snapshot else request.collection_key.collection_id
        current, total = self._job_progress
        text = f'{request.label}: {scope_name} · {operation}'
        if total:
            text += f' · {current}/{total}'
            self.activity_progress.setRange(0, total)
            self.activity_progress.setValue(min(current, total))
        else:
            self.activity_progress.setRange(0, 0)
        self.activity_label.setText(text)
        self.activity_label.show()
        self.activity_progress.show()
        queued = len(self._mutation_queue)
        self.cancel_jobs_button.setText(f'Cancel jobs ({queued} queued)' if queued else 'Cancel job')

    def cancel_jobs(self):
        queued = list(self._mutation_queue)
        self._mutation_queue.clear()
        for request in queued:
            message = 'Cancelled before starting; removed from the queue.'
            for key in request.affected_keys:
                self._operation_summaries[key] = message
            if request.kind == 'collection':
                for track_id in request.track_ids:
                    self._apply_mutation_event(
                        WorkerEvent(request.operation_id, request.collection_key, 'cancelled',
                                    track_id=track_id), request=request)
                self._apply_mutation_event(
                    WorkerEvent(request.operation_id, request.collection_key, 'cancelled'), request=request)
        request = self._active_job
        if request is not None:
            if (request.kind == 'repair' and self._waiting_for_player_release
                    and self._active_worker is None):
                self._waiting_for_player_release = False
                try:
                    self.playback.quiesced.disconnect(self._repair_after_playback_release)
                except (TypeError, RuntimeError):
                    pass
                self.playback.resume()
                for key in request.affected_keys:
                    self._operation_summaries[key] = 'Cancelled before repair started.'
                self._active_job = None
                self._cancel_requested = False
                self.loading_label.setText('Cancelled repair while waiting for playback to release its file.')
                self._update_activity_view()
                self._update_controls()
                if self._mutation_queue and not self._closing:
                    QTimer.singleShot(0, self._start_next_mutation)
                elif self._pending_refresh and not self._closing:
                    self._pending_refresh = False
                    QTimer.singleShot(0, self.refresh)
                return
            self._cancel_requested = True
            if request.kind == 'collection':
                snapshot = self.snapshots.get(request.collection_key)
                if snapshot:
                    for track in snapshot.tracks:
                        if track.track_id in request.track_ids and track.transfer != 'idle':
                            self._apply_mutation_event(
                                WorkerEvent(request.operation_id, request.collection_key, 'cancelling',
                                            track_id=track.track_id), request=request)
                self._apply_mutation_event(
                    WorkerEvent(request.operation_id, request.collection_key, 'cancelling'), request=request)
            if self._active_worker:
                self._active_worker.cancel()
        active_label = 'repair' if request and request.kind == 'repair' else 'download'
        self.loading_label.setText(
            f'Cancelled queued jobs; stopping the active {active_label}…' if request
            else 'Cancelled queued jobs before they started.')
        self._update_activity_view()
        self._update_controls()

    def _legacy_operation_started(self):
        self._legacy_mutation_active = True
        self.playback.quiesce()
        self._invalidate_snapshots()
        self._update_controls()

    def _legacy_operation_finished(self):
        self._legacy_mutation_active = False
        self.playback.resume()
        self._options_saved()

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
        self._update_controls()

    def _options_saved(self):
        self._invalidate_snapshots()
        if self._active_job or self._mutation_queue or self._legacy_mutation_active:
            self._pending_refresh = True
            return
        if self.worker and self.worker.isRunning():
            self._pending_refresh = True
            self.worker.cancel()
        else:
            self.refresh()

    def _finish_close_after_player_quiesced(self):
        if not self._close_when_player_quiesced:
            return
        self._close_when_player_quiesced = False
        try:
            self.playback.quiesced.disconnect(self._finish_close_after_player_quiesced)
        except (TypeError, RuntimeError):
            pass
        # When embedded as MainWindow's central widget, closing only this widget
        # would leave an empty top-level window and the process running.
        QTimer.singleShot(0, self.window().close)

    def closeEvent(self, event):
        if self.sync_window and not self.sync_window.close():
            event.ignore()
            return
        self._closing = True
        if self._active_job is not None or self._mutation_queue:
            self.cancel_jobs()
            if self._active_worker and self._active_worker.isRunning() and not self._active_worker.wait(5000):
                self.loading_label.setText('Cancelling sync / repair… close again when it stops.')
                event.ignore()
                return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                self.loading_label.setText('Cancelling library refresh… close again when it stops.')
                event.ignore()
                return
        if not self.playback.is_quiesced:
            self._close_when_player_quiesced = True
            self.playback.quiesced.connect(self._finish_close_after_player_quiesced)
            self.playback.quiesce()
            self.loading_label.setText('Stopping local playback before closing…')
            event.ignore()
            return
        self.playback.close()
        if self.options_window:
            self.options_window.close()
        event.accept()
