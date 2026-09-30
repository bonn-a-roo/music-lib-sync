import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from model.downloader import Downloader
from model.sync_result import SyncResult
from utils import configutils, metadatautils
from utils.durationcheck import duration_bounds, within_tolerance
from utils.fileutils import song_filename, track_id_from_filename
from utils.logutils import get_logger

logger = get_logger(__name__)
ATTEMPT_TIMEOUT = 600
_CONCURRENT_FRAGMENTS = 5
_HLS_FORMAT = 'bestaudio[protocol=m3u8_native]/bestaudio[protocol=m3u8]/91/best[protocol^=m3u8]'
_STRATEGIES = [
    ('YouTube', lambda s: f'ytsearch5:{s.artist} - {s.name}', True),
    ('YouTube (alt)', lambda s: f'ytsearch5:{s.name} {s.artist} official audio', True),
    ('SoundCloud', lambda s: f'scsearch5:{s.artist} - {s.name}', False),
]
_LEFTOVER = re.compile(r'\.(?:part(?:-Frag\d+)?|ytdl|(?:mp4|webm|m4a|opus|mkv)|temp\..+)$', re.I)
_ID_TOKEN = re.compile(r'\[([A-Za-z0-9]+)\]')


@dataclass
class _CommandResult:
    reason: str = ''
    entries: list[dict] = field(default_factory=list)


class YoutubeDownloader(Downloader):
    def __init__(self, cookies_file=None, browser='firefox', workers=5, embed_metadata=True,
                 audio_format=None):
        self.cookies_file = cookies_file
        self.browser = browser
        self.workers = workers
        self.embed_metadata = embed_metadata
        self.audio_format = audio_format or configutils.get_audio_format()
        self.ffmpeg_path = self._find_ffmpeg()
        self._cancel_event = threading.Event()
        self._running_processes = set()
        self._process_lock = threading.Lock()
        self._protected_files = set()

    @staticmethod
    def _find_ffmpeg():
        bundled = Path.home() / '.spotdl' / 'ffmpeg.exe'
        return str(bundled) if bundled.is_file() else shutil.which('ffmpeg')

    def preflight(self) -> list[str]:
        problems = []
        self.ffmpeg_path = self._find_ffmpeg()
        if not self.ffmpeg_path:
            problems.append('FFmpeg not found: install ffmpeg on PATH or in ~/.spotdl/ffmpeg.exe.')
        if not shutil.which('node'):
            problems.append('Node.js not found on PATH; install Node.js for YouTube downloads.')
        if self.cookies_file:
            if not os.path.isfile(self.cookies_file):
                problems.append(f'Cookies file not found: {self.cookies_file}')
        elif self.browser == 'firefox':
            if os.name == 'nt':
                profile = Path(os.environ.get('APPDATA', '')) / 'Mozilla' / 'Firefox' / 'Profiles'
            elif sys.platform == 'darwin':
                profile = Path.home() / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'
            else:
                profile = Path.home() / '.mozilla' / 'firefox'
            if not profile.is_dir():
                problems.append('Firefox profile directory not found; open Firefox once or provide a cookies file.')
        return problems

    @staticmethod
    def _kill_tree(proc):
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._process_lock:
            processes = tuple(self._running_processes)
        for proc in processes:
            self._kill_tree(proc)

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _log(self, line):
        logger.debug(line)
        if self.log_callback:
            try:
                self.log_callback(line)
            except Exception:
                logger.exception('Download log callback failed')

    @staticmethod
    def _output_template(final_path):
        return os.path.splitext(final_path)[0].replace('%', '%%') + '.%(ext)s'

    def _base_cmd(self):
        cmd = [sys.executable, '-m', 'yt_dlp', '--remote-components', 'ejs:github',
               '--js-runtimes', 'node', '--newline']
        if self.cookies_file:
            cmd.extend(['--cookies', self.cookies_file])
        else:
            cmd.extend(['--cookies-from-browser', self.browser])
        return cmd

    def _build_cmd(self, url, final_path, use_hls):
        cmd = self._base_cmd() + [
            '--no-playlist', '--max-downloads', '1', '--extract-audio',
            '--audio-format', 'vorbis' if self.audio_format == 'ogg' else self.audio_format, '--audio-quality', '0',
            '--format', _HLS_FORMAT if use_hls else 'bestaudio/best',
            '--concurrent-fragments', str(_CONCURRENT_FRAGMENTS),
            '--output', self._output_template(final_path),
        ]
        if self.ffmpeg_path:
            cmd.extend(['--ffmpeg-location', self.ffmpeg_path])
        return cmd + [url]

    def _run_cmd(self, cmd):
        """Drain output independently so silent processes still time out/cancel."""
        result = _CommandResult()
        if self.is_cancelled():
            return result
        proc = None
        reader = None
        recent = deque(maxlen=20)
        lines = queue.Queue()
        try:
            kwargs = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace', bufsize=1, **kwargs)
            with self._process_lock:
                self._running_processes.add(proc)
            def drain():
                try:
                    for line in proc.stdout:
                        lines.put(line.rstrip())
                finally:
                    lines.put(None)
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            deadline = time.monotonic() + ATTEMPT_TIMEOUT
            while True:
                if self.is_cancelled():
                    self._kill_tree(proc)
                    break
                if time.monotonic() >= deadline:
                    result.reason = f'timed out after {ATTEMPT_TIMEOUT:g}s'
                    self._kill_tree(proc)
                    break
                try:
                    line = lines.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line is None:
                    # Closing stdout is not necessarily process termination.
                    remaining = max(0, deadline - time.monotonic())
                    try:
                        proc.wait(timeout=min(0.05, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        lines.put(None)
                        continue
                if line:
                    recent.append(line)
                    self._log(line)
                    if line.lstrip().startswith('{'):
                        try:
                            entry = json.loads(line)
                            if isinstance(entry, dict):
                                result.entries.append(entry)
                        except ValueError:
                            pass
            proc.wait()
            if not result.reason:
                result.reason = next((line[line.index('ERROR:') + 6:].strip()
                                      for line in reversed(recent) if 'ERROR:' in line), '')
                if not result.reason and proc.returncode not in (0, 101):
                    result.reason = f'yt-dlp exited with code {proc.returncode}'
        except Exception as exc:
            result.reason = str(exc)
            if proc:
                self._kill_tree(proc)
                proc.wait()
        finally:
            if reader:
                reader.join(timeout=5)
            if proc:
                if proc.stdout:
                    proc.stdout.close()
                with self._process_lock:
                    self._running_processes.discard(proc)
        return result

    def _cleanup(self, final_path, remove_final=False):
        final = Path(final_path)
        stem = final.stem
        for path in final.parent.iterdir():
            if (path != final and str(path) not in self._protected_files and path.is_file()
                    and path.name.startswith(stem + '.') and _LEFTOVER.search(path.name)):
                path.unlink(missing_ok=True)
        if remove_final and str(final) not in self._protected_files:
            final.unlink(missing_ok=True)

    @staticmethod
    def _sweep(directory):
        paths = list(Path(directory).iterdir())
        completed = {track_id_from_filename(p.name) for p in paths if p.is_file()}
        for path in paths:
            token = _ID_TOKEN.search(path.name)
            if path.is_file() and token and token.group(1) not in completed and _LEFTOVER.search(path.name):
                path.unlink(missing_ok=True)

    @staticmethod
    def _duration_reason(song):
        bounds = duration_bounds(song.duration_ms)
        return (f'no candidate matched duration {bounds[0]:g}-{bounds[1]:g}s'
                if bounds else 'no downloadable search candidate found')

    def _download_song(self, song, download_path, result):
        final = os.path.join(download_path, song_filename(song.artist, song.name, song.track_id, ext=self.audio_format))
        # Existing library files belong to the user; never overwrite/delete/tag them.
        if os.path.isfile(final):
            if not self.is_cancelled():
                if within_tolerance(metadatautils.read_duration(final), song.duration_ms):
                    result.add_skipped()
                else:
                    result.add_failure(str(song), song.url, 'existing audio has wrong duration; repair required')
            return
        reason = self._duration_reason(song)
        try:
            for label, query, use_hls in _STRATEGIES:
                if self.is_cancelled():
                    break
                self._cleanup(final)
                self._log(f'[{label}] {song.artist} - {song.name}')
                # Flat search entries include durations on supported extractors.
                # Missing durations are resolved explicitly, never accepted blindly.
                listing = self._run_cmd(self._base_cmd() + ['--flat-playlist', '--skip-download', '--dump-json', query(song)])
                if listing.reason:
                    reason = listing.reason
                for candidate in listing.entries:
                    if self.is_cancelled():
                        break
                    url = candidate.get('webpage_url') or candidate.get('url')
                    if not url:
                        continue
                    if candidate.get('ie_key') == 'Youtube' and not url.startswith(('http://', 'https://')):
                        url = 'https://www.youtube.com/watch?v=' + url
                    duration = candidate.get('duration')
                    if duration is None and duration_bounds(song.duration_ms):
                        details = self._run_cmd(self._base_cmd() + ['--no-playlist', '--skip-download', '--dump-json', url])
                        duration = details.entries[0].get('duration') if details.entries else None
                        if details.reason:
                            reason = details.reason
                    if not within_tolerance(duration, song.duration_ms):
                        reason = self._duration_reason(song)
                        continue
                    self._cleanup(final)
                    attempt = self._run_cmd(self._build_cmd(url, final, use_hls))
                    if self.is_cancelled():
                        break
                    if attempt.reason.startswith('timed out after '):
                        self._cleanup(final, remove_final=True)
                        reason = attempt.reason
                        break
                    if os.path.isfile(final):
                        if not within_tolerance(metadatautils.read_duration(final), song.duration_ms):
                            self._cleanup(final, remove_final=True)
                            reason = self._duration_reason(song)
                            break  # Try a different query/provider, not the same bad source.
                        if self.embed_metadata:
                            try:
                                if not metadatautils.embed_metadata(final, song, embed_art=True):
                                    logger.warning('Metadata embedding failed for %s', final)
                            except Exception:
                                logger.warning('Metadata embedding failed for %s', final, exc_info=True)
                        self._cleanup(final)
                        result.add_success()
                        return
                    reason = attempt.reason or f'yt-dlp produced no {self.audio_format.upper()} file'
                    self._cleanup(final)
            if not self.is_cancelled():
                logger.error('Download failed for %s: %s', song, reason)
                self._log(f'ERROR: {song}: {reason}')
                result.add_failure(str(song), song.url, reason)
        except Exception as exc:
            if not self.is_cancelled():
                logger.exception('Download failed for %s', song)
                result.add_failure(str(song), song.url, str(exc))
        finally:
            self._cleanup(final, remove_final=self.is_cancelled())

    def download(self, songs, download_path, progress_callback=None) -> SyncResult:
        result = SyncResult()
        if not songs:
            return result
        os.makedirs(download_path, exist_ok=True)
        self._protected_files = {str(path) for path in Path(download_path).iterdir()
                                 if path.is_file() and track_id_from_filename(path.name)}
        self._sweep(download_path)
        total = len(songs)
        if progress_callback:
            progress_callback(0, total, '')
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._download_song, song, download_path, result): song for song in songs}
            for done, future in enumerate(as_completed(futures), 1):
                future.result()
                song = futures[future]
                if progress_callback:
                    progress_callback(done, total, f'{song.artist} - {song.name}')
        result.cancelled = self.is_cancelled()
        return result
