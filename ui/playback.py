"""Local audio playback with FFmpeg decoding fallback for Qt codec gaps."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from PyQt5.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from downloaders.ytdlp import YoutubeDownloader
from model.library_state import CollectionKey
from utils.logutils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PlaybackEntry:
    collection_key: CollectionKey
    track_id: str
    path: str
    title: str
    artist: str
    row_index: int


class PlaybackController(QObject):
    """Own the persistent player and one selected-collection playback queue.

    QtMultimedia is used for output and transport controls. On systems where its
    codec backend cannot read a supported source, FFmpeg converts that source to
    a temporary PCM WAV; the library file is never changed.
    """

    current_changed = pyqtSignal(object)
    state_changed = pyqtSignal(str)
    track_state_changed = pyqtSignal(object, str)
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    quiesced = pyqtSignal()

    _TRANSCODE_FIRST = frozenset({'.flac', '.m4a', '.opus', '.ogg'})
    MAX_TEMP_WAV_BYTES = 1024 ** 3
    TEMP_DISK_RESERVE_BYTES = 64 * 1024 ** 2
    DECODE_TIMEOUT_MS = 10 * 60 * 1000

    def __init__(self, parent=None, ffmpeg_path=None, player=None):
        super().__init__(parent)
        self.player = player or QMediaPlayer(self)
        self.ffmpeg_path = ffmpeg_path if ffmpeg_path is not None else YoutubeDownloader._find_ffmpeg()
        self._queue = ()
        self._index = -1
        self._current_entry = None
        self._generation = 0
        self._decode_process = None
        self._pending_processes = set()
        self._pending_start_generation = None
        self._quiescing = False
        self._quiesced_emitted = False
        self._fallback_attempted = False
        self._fallback_resume_pending = False
        self._fallback_position_ms = 0
        self._resume_after_decode = True
        self._changing_media = False
        self._current_temp = None
        self._temp_files = set()
        self._active_decode_output = None
        self._active_decode_limit = 0
        self._decode_timer = QTimer(self)
        self._decode_timer.setSingleShot(True)
        self._decode_timer.timeout.connect(self._on_decode_timeout)
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix='music-lib-sync-playback-', ignore_cleanup_errors=True)
        self._closed = False
        self.player.stateChanged.connect(self._on_player_state)
        self.player.positionChanged.connect(self.position_changed.emit)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.error.connect(self._on_player_error)

    @property
    def current_entry(self):
        return self._current_entry

    @property
    def queue(self):
        return self._queue

    @property
    def queue_index(self):
        return self._index

    @property
    def position(self):
        return self.player.position()

    @property
    def is_quiesced(self):
        return (self._current_entry is None and self.player.mediaStatus() == QMediaPlayer.NoMedia
                and self._decode_process is None and not self._pending_processes)

    @property
    def is_quiescing(self):
        return self._quiescing

    @property
    def duration(self):
        return self.player.duration()

    def play_queue(self, entries, start_index=0):
        entries = tuple(entries)
        if self._closed or self._quiescing:
            return False
        if not entries:
            self.stop()
            return False
        self._release_current_media()
        self._queue = entries
        self._index = max(0, min(int(start_index), len(entries) - 1))
        self._start_current()
        return True

    def toggle(self):
        if self._decode_process is not None or self._fallback_resume_pending:
            self._resume_after_decode = not self._resume_after_decode
            self.state_changed.emit('decoding' if self._resume_after_decode else 'paused')
            self._resume_fallback_if_ready()
        elif self.player.state() == QMediaPlayer.PlayingState:
            self._resume_after_decode = False
            self.player.pause()
        elif self.player.state() == QMediaPlayer.PausedState:
            self._resume_after_decode = True
            self.player.play()
        elif self._current_entry is not None and self._decode_process is None:
            self._resume_after_decode = True
            self.player.play()

    def next(self):
        if self._index < 0 or self._index + 1 >= len(self._queue):
            self.stop()
            return
        self._release_current_media()
        self._index += 1
        self._start_current()

    def previous(self):
        if self._index < 0:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        if self._index == 0:
            self.player.setPosition(0)
            return
        self._release_current_media()
        self._index -= 1
        self._start_current()

    def retry_current(self):
        if self._index < 0 or self._index >= len(self._queue):
            return
        self._release_current_media()
        self._start_current()

    def seek(self, position_ms):
        position_ms = max(0, int(position_ms))
        if self._decode_process is not None or self._fallback_resume_pending:
            self._fallback_position_ms = position_ms
        else:
            self.player.setPosition(position_ms)

    def set_volume(self, value):
        self.player.setVolume(max(0, min(100, int(value))))

    def stop(self):
        self._quiescing = False
        self._quiesced_emitted = False
        self._release_current_media()
        self._queue = ()
        self._index = -1
        self.current_changed.emit(None)
        self.state_changed.emit('stopped')
        self.position_changed.emit(0)
        self.duration_changed.emit(0)

    def quiesce(self):
        """Stop playback and signal only after Qt and FFmpeg release their files."""
        if self._closed:
            return
        if not self._quiescing:
            self._quiescing = True
            self._quiesced_emitted = False
        self._pending_start_generation = None
        self._release_current_media()
        self._queue = ()
        self._index = -1
        self.current_changed.emit(None)
        self.state_changed.emit('stopped')
        self._check_quiesced()

    def resume(self):
        if self._closed:
            return
        self._quiescing = False
        self._quiesced_emitted = False

    def close(self):
        if self._closed:
            return
        self.quiesce()
        self._closed = True
        for path in tuple(self._temp_files):
            try:
                os.remove(path)
                self._temp_files.discard(path)
            except FileNotFoundError:
                self._temp_files.discard(path)
            except OSError:
                self._schedule_temp_cleanup(path)
        if not self._temp_files:
            self._temp_dir.cleanup()

    def _release_current_media(self):
        old_entry = self._current_entry
        old_temp = self._current_temp
        self._current_entry = None
        self._current_temp = None
        self._fallback_resume_pending = False
        self._generation += 1
        self._pending_start_generation = None
        self._cancel_decode()
        self._changing_media = True
        self.player.stop()
        self.player.setMedia(QMediaContent())
        self._changing_media = False
        if old_entry is not None:
            self.track_state_changed.emit(old_entry, 'stopped')
        self.position_changed.emit(0)
        self.duration_changed.emit(0)
        if old_temp:
            self._schedule_temp_cleanup(old_temp)
        self._check_quiesced()

    def _start_current(self):
        if self._closed or not 0 <= self._index < len(self._queue):
            return
        entry = self._queue[self._index]
        self._current_entry = entry
        self._fallback_attempted = Path(entry.path).suffix.casefold() in self._TRANSCODE_FIRST
        self._fallback_position_ms = 0
        self._resume_after_decode = True
        self.current_changed.emit(entry)
        self.position_changed.emit(0)
        self.duration_changed.emit(0)
        if not os.path.isfile(entry.path):
            self._fail('This audio file is no longer available.')
            return
        if (self._pending_processes or self.player.mediaStatus() != QMediaPlayer.NoMedia):
            self._pending_start_generation = self._generation
            self.state_changed.emit('loading')
            return
        self._load_current_source()

    def _load_current_source(self):
        if self._current_entry is None or self._closed or self._quiescing:
            return
        if self._fallback_attempted:
            self._decode_to_wav(self._current_entry.path, self._generation)
        else:
            self.state_changed.emit('loading')
            self._set_media(self._current_entry.path)

    def _set_media(self, path, autoplay=True):
        if self._closed:
            return
        self._changing_media = True
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(path))))
        self._changing_media = False
        if autoplay:
            self.player.play()

    def _decode_to_wav(self, source, generation):
        if not self.ffmpeg_path:
            self._fail('FFmpeg is required to decode this audio format, but was not found.')
            return
        available = shutil.disk_usage(self._temp_dir.name).free - self.TEMP_DISK_RESERVE_BYTES
        output_limit = min(self.MAX_TEMP_WAV_BYTES, max(0, available))
        if output_limit < 16 * 1024 ** 2:
            self._fail('Not enough free space for temporary audio decoding.')
            return
        target = os.path.join(self._temp_dir.name, f'{generation}-{uuid.uuid4().hex}.wav')
        self._temp_files.add(target)
        self._active_decode_output = target
        self._active_decode_limit = output_limit
        process = QProcess(self)
        process.setProgram(self.ffmpeg_path)
        process.setArguments([
            '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', os.path.abspath(source),
            '-vn', '-map', '0:a:0', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
            '-fs', str(output_limit), target,
        ])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(
            lambda code, status, proc=process, gen=generation, output=target:
                self._decode_finished(proc, gen, output, code, status))
        process.errorOccurred.connect(
            lambda error, proc=process, gen=generation, output=target:
                self._decode_error(proc, gen, output, error))
        self._decode_process = process
        process.start()
        self._decode_timer.start(self.DECODE_TIMEOUT_MS)
        self.state_changed.emit('decoding')

    def _cancel_decode(self):
        process = self._decode_process
        self._decode_process = None
        if process is not None:
            self._decode_timer.stop()
            self._active_decode_output = None
            self._pending_processes.add(process)
            if process.state() != QProcess.NotRunning:
                process.kill()

    def _decode_finished(self, process, generation, output, exit_code, _exit_status):
        error_output = bytes(process.readAll()).decode('utf-8', errors='replace').strip()
        active_process = process is self._decode_process
        known_process = active_process or process in self._pending_processes
        self._pending_processes.discard(process)
        if not known_process:
            process.deleteLater()
            return
        if active_process:
            self._decode_process = None
            self._decode_timer.stop()
            output_limit = self._active_decode_limit
            self._active_decode_output = None
        else:
            output_limit = self._active_decode_limit
        process.deleteLater()
        if generation != self._generation or self._current_entry is None or self._closed:
            self._schedule_temp_cleanup(output)
            self._check_quiesced()
            self._start_pending_current()
            return
        output_size = os.path.getsize(output) if os.path.isfile(output) else 0
        if exit_code != 0 or output_size <= 44 or output_size >= output_limit:
            self._schedule_temp_cleanup(output)
            if output_size >= output_limit:
                message = 'The decoded audio is too large for the temporary-file limit (1 GiB or free disk space).'
            else:
                logger.warning('FFmpeg could not decode %s: %s', self._current_entry.path, error_output)
                message = self._unplayable_message()
            self._fail(message)
            return
        self._current_temp = output
        self._fallback_resume_pending = True
        self.state_changed.emit('loading')
        self._set_media(output, autoplay=False)
        self._resume_fallback_if_ready()

    def _decode_error(self, process, generation, output, error):
        if error != QProcess.FailedToStart:
            return
        active_process = process is self._decode_process
        if not active_process and process not in self._pending_processes:
            return
        self._pending_processes.discard(process)
        if active_process:
            self._decode_process = None
            self._decode_timer.stop()
            self._active_decode_output = None
        process.deleteLater()
        if generation != self._generation or self._closed:
            self._schedule_temp_cleanup(output)
            self._check_quiesced()
            self._start_pending_current()
            return
        self._schedule_temp_cleanup(output)
        self._fail('FFmpeg could not be started to decode this audio file.')
        self._check_quiesced()
        self._start_pending_current()

    def _start_pending_current(self):
        generation = self._pending_start_generation
        if (generation is None or self._pending_processes or self._quiescing or self._closed
                or generation != self._generation
                or self.player.mediaStatus() != QMediaPlayer.NoMedia):
            return
        self._pending_start_generation = None
        self._load_current_source()

    def _check_quiesced(self):
        if self._quiescing and not self._quiesced_emitted and self.is_quiesced:
            self._quiesced_emitted = True
            self.quiesced.emit()

    def _on_decode_timeout(self):
        process = self._decode_process
        output = self._active_decode_output
        self._decode_process = None
        self._active_decode_output = None
        if process is not None:
            self._pending_processes.add(process)
            process.kill()
        if output:
            self._schedule_temp_cleanup(output)
        self._generation += 1
        self._fail('FFmpeg audio preparation exceeded the 10 minute limit.')
        self._check_quiesced()

    def _on_player_error(self, _error):
        if (self._changing_media or self._closed or self._quiescing
                or self._pending_start_generation is not None or self._current_entry is None):
            return
        if self._decode_process is not None:
            return
        if not self._fallback_attempted:
            self._fallback_attempted = True
            self._fallback_position_ms = max(0, self.player.position())
            if self.player.state() == QMediaPlayer.PausedState:
                self._resume_after_decode = False
            elif self.player.state() == QMediaPlayer.PlayingState:
                self._resume_after_decode = True
            self._decode_to_wav(self._current_entry.path, self._generation)
            return
        logger.warning('Qt could not play %s: %s', self._current_entry.path, self.player.errorString())
        self._fail(self._unplayable_message())

    def _on_player_state(self, state):
        if self._changing_media or self._closed or self._pending_start_generation is not None:
            return
        if self._quiescing:
            self._check_quiesced()
            return
        if state == QMediaPlayer.PlayingState:
            self._emit_state('playing')
        elif state == QMediaPlayer.PausedState:
            self._emit_state('paused')
        elif self._decode_process is None and self._current_entry is not None:
            self._emit_state('stopped')

    def _on_media_status(self, status):
        if status == QMediaPlayer.NoMedia:
            self._check_quiesced()
            self._start_pending_current()
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self._resume_fallback_if_ready()
        if (not self._quiescing and self._pending_start_generation is None
                and status == QMediaPlayer.EndOfMedia and self._current_entry is not None):
            self.next()

    def _on_player_duration_changed(self, duration):
        self.duration_changed.emit(duration)
        if duration > 0:
            self._resume_fallback_if_ready()

    def _resume_fallback_if_ready(self):
        if not self._fallback_resume_pending or self._closed or self._quiescing:
            return
        if self.player.duration() <= 0:
            return
        self._fallback_resume_pending = False
        position = min(self._fallback_position_ms, max(0, self.player.duration() - 1))
        if position:
            self.player.setPosition(position)
        if self._resume_after_decode:
            self.player.play()
        elif self._current_entry is not None:
            self._emit_state('paused')

    def _emit_state(self, state):
        self.state_changed.emit(state)
        if self._current_entry is not None:
            self.track_state_changed.emit(self._current_entry, state)

    def _unplayable_message(self):
        name = Path(self._current_entry.path).name if self._current_entry else 'This file'
        return f'Could not play “{name}”: the file may be damaged or its format is unsupported.'

    def _fail(self, message):
        self._emit_state('error')
        self.error_occurred.emit(message)

    def _schedule_temp_cleanup(self, path, attempt=0):
        def cleanup():
            if path not in self._temp_files:
                return
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                if attempt < 12:
                    QTimer.singleShot(250, lambda: self._schedule_temp_cleanup(path, attempt + 1))
                    return
            self._temp_files.discard(path)
            if self._closed and not self._temp_files:
                self._temp_dir.cleanup()
        QTimer.singleShot(250, cleanup)
