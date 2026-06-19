import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from model.downloader import Downloader
from model.sync_result import SyncResult
from utils.logutils import get_logger

logger = get_logger(__name__)

_CONCURRENT_FRAGMENTS = 5   # HLS fragments downloaded in parallel per song
_DEFAULT_WORKERS = 3        # songs downloaded in parallel


class YoutubeDownloader(Downloader):

    def __init__(self, browser: str = 'firefox', workers: int = _DEFAULT_WORKERS):
        self.browser = browser
        self.workers = workers
        self.ffmpeg_path = self._find_ffmpeg()
        self._cancel_event = threading.Event()
        self._running_processes: set = set()
        self._process_lock = threading.Lock()
        self.log_callback = None

    def _find_ffmpeg(self) -> str:
        spotdl_ffmpeg = Path.home() / '.spotdl' / 'ffmpeg.exe'
        if spotdl_ffmpeg.exists():
            logger.info(f"Using ffmpeg from spotdl: {spotdl_ffmpeg}")
            return str(spotdl_ffmpeg)
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info("Using ffmpeg from PATH")
            return 'ffmpeg'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        logger.warning("FFmpeg not found — downloads may fail")
        return None

    def cancel(self):
        self._cancel_event.set()
        with self._process_lock:
            for proc in self._running_processes:
                try:
                    proc.kill()
                except Exception:
                    pass

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _log(self, line: str):
        if self.log_callback and line:
            self.log_callback(line)

    def _ytdlp_cmd(self, query: str, output_path: str) -> list:
        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '--cookies-from-browser', self.browser,
            '--remote-components', 'ejs:github',
            '--js-runtimes', 'node',
            '--no-playlist',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '--format', 'bestaudio[protocol=m3u8_native]/bestaudio[protocol=m3u8]/91/best[protocol^=m3u8]',
            '--concurrent-fragments', str(_CONCURRENT_FRAGMENTS),
            '--output', output_path,
        ]
        if self.ffmpeg_path:
            cmd.extend(['--ffmpeg-location', self.ffmpeg_path])
        cmd.append(query)
        return cmd

    def _download_one(self, song, download_path: str, result: SyncResult,
                      completed: list, total: int, progress_callback) -> None:
        if self._cancel_event.is_set():
            return

        query = f'ytsearch1:{song.artist} - {song.name}'
        out_tmpl = os.path.join(download_path, f'{song.artist} - {song.name} [{song.track_id}].%(ext)s')
        cmd = self._ytdlp_cmd(query, out_tmpl)

        self._log(f'--- Downloading: {song.artist} - {song.name} ---')
        logger.info(f'Downloading: {song.artist} - {song.name}')

        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', bufsize=1
            )
            with self._process_lock:
                self._running_processes.add(proc)

            output_lines = []
            for line in proc.stdout:
                if self._cancel_event.is_set():
                    proc.kill()
                    break
                stripped = line.rstrip()
                if stripped:
                    output_lines.append(stripped)
                    self._log(stripped)

            proc.wait()
            returncode = proc.returncode

            with self._process_lock:
                self._running_processes.discard(proc)

            if returncode == 0:
                result.add_success()
                self._log(f'OK: {song.artist} - {song.name}')
            else:
                tail = '\n'.join(output_lines[-5:])
                logger.error(f'Failed {song.artist} - {song.name}: {tail}')
                result.add_failure(str(song), query, f'yt-dlp exit {returncode}')

        except Exception as e:
            if proc is not None:
                with self._process_lock:
                    self._running_processes.discard(proc)
                try:
                    proc.kill()
                except Exception:
                    pass
            logger.error(f'Exception for {song}: {e}')
            self._log(f'ERROR: {e}')
            result.add_failure(str(song), query, str(e))

        finally:
            with self._process_lock:
                done = result.success_count + result.failure_count
            if progress_callback:
                progress_callback(done, total, f'{song.artist} - {song.name}')

    def download_songs_batch(self, songs: list, download_path: str, result: 'SyncResult',
                             batch_size: int = 10, progress_callback=None):
        os.makedirs(download_path, exist_ok=True)
        total = len(songs)
        completed = [0]  # mutable counter accessed from threads

        self._log(f'Starting {total} downloads with {self.workers} parallel workers...')

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(self._download_one, song, download_path, result,
                            completed, total, progress_callback): song
                for song in songs
            }
            for future in as_completed(futures):
                if self._cancel_event.is_set():
                    break
                try:
                    future.result()
                except Exception as e:
                    logger.error(f'Unhandled future error: {e}')

        logger.info(f'Batch done: {result.success_count} ok, {result.failure_count} failed')
        self._log(f'=== Done: {result.success_count} downloaded, {result.failure_count} failed ===')
        if progress_callback:
            progress_callback(total, total, '')

    def download_song(self, song, download_path) -> bool:
        result = SyncResult()
        self.download_songs_batch([song], download_path, result)
        return result.success_count > 0

    def download_playlist(self, playlist, download_path) -> bool:
        if self._cancel_event.is_set():
            return False
        os.makedirs(download_path, exist_ok=True)
        result = SyncResult()
        self.download_songs_batch(playlist.songs, download_path, result)
        return result.failure_count == 0

    def download(self, objects, download_path, num_threads=2, progress_callback=None) -> 'SyncResult':
        from model.song import Song as SongModel
        result = SyncResult()
        if not objects:
            return result
        if all(isinstance(item, SongModel) for item in objects):
            self.download_songs_batch(objects, download_path, result, progress_callback=progress_callback)
            return result
        return super().download(objects, download_path, num_threads)
