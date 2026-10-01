"""Immutable browsing state and future mutation-event payloads.

WorkerEvent is a contract only; legacy sync callbacks do not emit it.
"""
from dataclasses import dataclass
import os
from typing import Literal, Optional
from utils.fileutils import track_id_from_filename


@dataclass(frozen=True)
class CollectionKey:
    account_id: str
    collection_id: str


@dataclass(frozen=True)
class TrackSnapshot:
    track_id: str
    name: Optional[str]
    artist: Optional[str]
    album: Optional[str]
    duration_ms: Optional[int]
    presence: str = 'unknown'
    local_path: Optional[str] = None
    elsewhere_path: Optional[str] = None
    transfer: Literal['idle', 'queued', 'downloading', 'cancelling'] = 'idle'
    outcome: Optional[Literal['succeeded', 'failed', 'cancelled']] = None
    playback: Literal['stopped', 'playing', 'paused', 'error'] = 'stopped'


@dataclass(frozen=True)
class CollectionSnapshot:
    key: CollectionKey
    name: str
    destination: str
    metadata: str = 'ready'
    tracks: tuple[TrackSnapshot, ...] = ()
    skipped_count: int = 0
    error: Optional[str] = None
    refreshed_at: Optional[float] = None
    scan_complete: bool = False
    stale: bool = False
    operation: Literal['idle', 'queued', 'syncing', 'downloading', 'cancelling'] = 'idle'
    outcome: Optional[Literal['succeeded', 'failed', 'cancelled']] = None

    def __post_init__(self):
        object.__setattr__(self, 'tracks', tuple(self.tracks))

    @property
    def eligible_count(self):
        return len({track.track_id for track in self.tracks})

    @property
    def downloaded_count(self):
        return len({track.track_id for track in self.tracks if track.presence == 'downloaded'})

    @property
    def missing_count(self):
        return len({track.track_id for track in self.tracks if track.presence in ('missing', 'quarantined')})

    @property
    def coverage(self):
        if self.metadata != 'ready' or not self.scan_complete or self.stale:
            return 'unknown'
        if any(track.presence == 'unknown' for track in self.tracks):
            return 'unknown'
        if self.downloaded_count == self.eligible_count:
            return 'complete'
        return 'partial' if self.downloaded_count else 'missing'

    @property
    def status(self):
        if self.metadata == 'restricted':
            return 'Restricted'
        if self.metadata == 'error' or self.error:
            return 'Error'
        if self.operation != 'idle':
            return self.operation.capitalize()
        if self.outcome == 'failed':
            return 'Failed'
        if self.metadata in ('not_loaded', 'loading'):
            return 'Loading'
        if self.coverage == 'unknown':
            return 'Unknown'
        if not self.eligible_count:
            return 'Empty'
        return {'complete': 'Synced', 'partial': 'Partial', 'missing': 'Not downloaded'}[self.coverage]


@dataclass(frozen=True)
class WorkerEvent:
    operation_id: str
    collection_key: CollectionKey
    phase: Literal['start', 'queued', 'syncing', 'downloading', 'success', 'failure', 'skip', 'cancelling', 'cancelled']
    track_id: Optional[str] = None
    completed: int = 0
    total: int = 0
    final_path: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not self.operation_id:
            raise ValueError('An operation ID is required')
        if self.phase not in ('start', 'queued', 'syncing', 'downloading', 'success', 'failure', 'skip', 'cancelling', 'cancelled'):
            raise ValueError('Invalid worker event phase')
        if self.completed < 0 or self.total < self.completed:
            raise ValueError('Invalid progress counters')
        if self.phase == 'success' and self.track_id is not None:
            if not self.final_path or not os.path.isfile(self.final_path):
                raise ValueError('Track success requires an existing final file')
        if self.phase == 'failure' and not self.error:
            raise ValueError('Failure requires an error')
        if self.phase == 'skip' and not self.reason:
            raise ValueError('Skip requires a reason')

    def belongs_to(self, operation_id, collection_key):
        """Reject late events from obsolete runs or other collection scopes."""
        return self.operation_id == operation_id and self.collection_key == collection_key


class LocalFileIndex:
    """Read-only per-refresh index. Incomplete scans never imply missing files."""
    def __init__(self, root, cancel_check=None):
        self.paths = {}
        self.rejected = {}
        self.complete = True
        self.error = None
        self.root = os.path.abspath(os.path.expanduser(os.fspath(root)))
        self._scan(cancel_check)

    def _scan(self, cancel_check):
        def failed(error):
            self.complete = False
            self.error = str(error)

        try:
            # stat distinguishes an absent root from inaccessible storage.
            try:
                os.stat(self.root)
            except FileNotFoundError:
                return
            if not os.path.isdir(self.root):
                raise NotADirectoryError('Library destination is not a directory')
            for directory, folders, files in os.walk(self.root, onerror=failed, followlinks=False):
                if cancel_check and cancel_check():
                    raise InterruptedError('Library scan cancelled')
                folders[:] = sorted(folder for folder in folders if not os.path.islink(os.path.join(directory, folder)) and folder.casefold() not in ('tmp', 'temp', '_temp') and not folder.startswith('.'))
                quarantined = '_rejected' in os.path.relpath(directory, self.root).split(os.sep)
                for filename in sorted(files):
                    if filename.startswith('.') or '.part' in filename.casefold() or '.tmp' in filename.casefold():
                        continue
                    track_id = track_id_from_filename(filename)
                    path = os.path.join(directory, filename)
                    if track_id and not os.path.islink(path):
                        (self.rejected if quarantined else self.paths).setdefault(track_id, []).append(path)
        except OSError as error:
            failed(error)

    def reconcile(self, songs, destination):
        destination = os.path.normcase(os.path.abspath(destination))
        rows = []
        for song in songs:
            paths = self.paths.get(song.track_id, ())
            local = next((path for path in paths if os.path.normcase(os.path.dirname(path)) == destination), None)
            elsewhere = next((path for path in paths if os.path.normcase(os.path.dirname(path)) != destination), None)
            rejected = any(os.path.normcase(os.path.dirname(os.path.dirname(path))) == destination for path in self.rejected.get(song.track_id, ()))
            presence = ('downloaded' if local else 'quarantined' if rejected else 'missing') if self.complete else 'unknown'
            rows.append(TrackSnapshot(song.track_id, song.name, song.artist, song.album, song.duration_ms, presence, local if self.complete else None, elsewhere if self.complete else None))
        return tuple(rows)
