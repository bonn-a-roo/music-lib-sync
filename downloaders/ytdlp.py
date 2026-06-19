import os
import subprocess
import sys
import threading
from pathlib import Path

from model.downloader import Downloader
from model.sync_result import SyncResult
from utils.logutils import get_logger

logger = get_logger(__name__)


class YoutubeDownloader(Downloader):

    def __init__(self, browser: str = 'firefox'):
        self.browser = browser
        self.ffmpeg_path = self._find_ffmpeg()
        self._cancel_event = threading.Event()
        self._current_process = None
        self.log_callback = None  # set by the UI to stream output lines

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
        if self._current_process:
            try:
                self._current_process.kill()
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
            '--output', output_path,
        ]
        if self.ffmpeg_path:
            cmd.extend(['--ffmpeg-location', self.ffmpeg_path])
        cmd.append(query)
        return cmd

    def download_songs_batch(self, songs: list, download_path: str, result: 'SyncResult',
                             batch_size: int = 10, progress_callback=None):
        os.makedirs(download_path, exist_ok=True)
        total = len(songs)

        for i, song in enumerate(songs):
            if self._cancel_event.is_set():
                break

            if progress_callback:
                progress_callback(i, total, str(song))

            query = f'ytsearch1:{song.artist} - {song.name}'
            output_path = os.path.join(download_path, f'{song.artist} - {song.name} [{song.track_id}].%(ext)s')
            cmd = self._ytdlp_cmd(query, output_path)

            self._log(f'--- Downloading ({i + 1}/{total}): {song.artist} - {song.name} ---')
            logger.info(f'Downloading: {song.artist} - {song.name}')

            try:
                self._current_process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace', bufsize=1
                )

                output_lines = []
                for line in self._current_process.stdout:
                    if self._cancel_event.is_set():
                        self._current_process.kill()
                        break
                    stripped = line.rstrip()
                    if stripped:
                        output_lines.append(stripped)
                        self._log(stripped)

                self._current_process.wait()
                returncode = self._current_process.returncode
                self._current_process = None

                if returncode == 0:
                    result.add_success()
                    self._log(f'OK: {song.artist} - {song.name}')
                else:
                    tail = '\n'.join(output_lines[-5:])
                    logger.error(f'Failed {song.artist} - {song.name}: {tail}')
                    result.add_failure(str(song), query, f'yt-dlp exit {returncode}')

            except Exception as e:
                if self._current_process:
                    self._current_process.kill()
                self._current_process = None
                logger.error(f'Exception for {song}: {e}')
                self._log(f'ERROR: {e}')
                result.add_failure(str(song), query, str(e))

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
