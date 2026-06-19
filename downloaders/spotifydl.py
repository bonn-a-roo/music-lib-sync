import os
import subprocess
import sys
import threading
from pathlib import Path
from model.downloader import Downloader
from model.sync_result import SyncResult
from utils.fileutils import create_directory, sanitize_filename
from utils.logutils import get_logger

logger = get_logger(__name__)


class SpotifyDownloader(Downloader):

    def __init__(self, cookies=None, embed_metadata: bool = False, client_id: str = None, client_secret: str = None):
        """
        Initialize Spotify downloader.

        Args:
            cookies: Path to cookies.txt file for authenticated downloads
            embed_metadata: Whether to embed metadata tags after download
            client_id: Spotify client ID for API access
            client_secret: Spotify client secret for API access
        """
        self.cookies = cookies
        self.embed_metadata = embed_metadata
        self.client_id = client_id
        self.client_secret = client_secret
        self.ffmpeg_path = self._find_ffmpeg()
        self._cancel_event = threading.Event()
        self._current_process = None

    def cancel(self):
        self._cancel_event.set()
        if self._current_process:
            try:
                self._current_process.kill()
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _find_ffmpeg(self) -> str:
        """Find the ffmpeg executable, checking spotdl's download location."""
        # Check spotdl's default download location first
        spotdl_ffmpeg = Path.home() / '.spotdl' / 'ffmpeg.exe'
        if spotdl_ffmpeg.exists():
            logger.info(f"Using ffmpeg from spotdl: {spotdl_ffmpeg}")
            return str(spotdl_ffmpeg)

        # Check if ffmpeg is in PATH
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info("Using ffmpeg from PATH")
            return 'ffmpeg'
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        logger.warning("FFmpeg not found - downloads may fail")
        return None

    def _spotdl_cmd(self, action: str, queries: list, extra_flags: list = None) -> list:
        """Build a complete spotdl command.

        Structure: python -m spotdl <action> <queries> <flags> [--audio ...]
        Queries (URLs) must come before flags because --audio uses nargs='*'
        and greedily consumes anything that follows until the next --flag.
        """
        from utils import configutils
        cmd = [sys.executable, '-m', 'spotdl', action] + queries
        if self.ffmpeg_path:
            cmd.extend(['--ffmpeg', self.ffmpeg_path])
        if self.client_id:
            cmd.extend(['--client-id', self.client_id])
        if self.client_secret:
            cmd.extend(['--client-secret', self.client_secret])
        if self.cookies:
            cmd.extend(['--cookie-file', self.cookies])
        cmd.extend(['--format', configutils.get_audio_format()])
        if extra_flags:
            cmd.extend(extra_flags)
        providers = configutils.get_audio_providers().split()
        if providers:
            cmd.extend(['--audio'] + providers)
        return cmd

    def download_songs_batch(self, songs: list, download_path: str, result: 'SyncResult', batch_size: int = 50, progress_callback=None):
        """
        Download a list of songs in batches, passing multiple URLs to one spotdl call.
        Much faster than one process per song.
        """
        os.makedirs(download_path, exist_ok=True)
        total = len(songs)

        for batch_start in range(0, total, batch_size):
            if self._cancel_event.is_set():
                break

            batch = songs[batch_start:batch_start + batch_size]
            batch_end = min(batch_start + batch_size, total)
            logger.info(f"Downloading batch {batch_start + 1}-{batch_end} of {total}...")

            if progress_callback:
                progress_callback(batch_start, total, str(batch[0]) if batch else '')

            urls = [song.url for song in batch]
            command = self._spotdl_cmd('download', urls, ['--output', download_path, '--threads', '4'])

            if not self.cookies:
                logger.warning("No cookies file configured — downloads may fail due to YouTube rate limiting. Set one in Options.")

            files_before = set(os.listdir(download_path))
            try:
                self._current_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                try:
                    output, _ = self._current_process.communicate(timeout=300 * len(batch))
                except subprocess.TimeoutExpired:
                    self._current_process.kill()
                    output, _ = self._current_process.communicate()
                    logger.error(f"Batch timed out. Last output: {output[-500:] if output else 'none'}")
                finally:
                    self._current_process = None

                if output:
                    logger.info(f"spotdl batch output: {output.strip()[-2000:]}")
            except Exception as e:
                self._current_process = None
                logger.error(f"Exception in batch download: {e}")
                for song in batch:
                    result.add_failure(str(song), song.url, str(e))
                continue

            # Count new files created as successes
            files_after = set(os.listdir(download_path))
            new_files = files_after - files_before
            succeeded = len(new_files)
            failed = len(batch) - succeeded
            logger.info(f"Batch done: {succeeded} downloaded, {failed} failed")
            for _ in range(succeeded):
                result.add_success()
            for i, song in enumerate(batch):
                if i >= succeeded:
                    result.add_failure(str(song), song.url, "Not downloaded")

            if progress_callback:
                progress_callback(min(batch_start + batch_size, total), total, '')

    def download(self, objects, download_path, num_threads=2, progress_callback=None) -> 'SyncResult':
        """Override to use batch downloading for songs."""
        from model.song import Song as SongModel
        from model.playlist import Playlist as PlaylistModel

        result = SyncResult()
        if not objects:
            return result

        if all(isinstance(item, SongModel) for item in objects):
            self.download_songs_batch(objects, download_path, result, progress_callback=progress_callback)
            logger.info(f"Download complete: {result.success_count} succeeded, {result.failure_count} failed, {result.skipped_count} skipped")
            return result

        # Fall back to base class behaviour for playlists
        return super().download(objects, download_path, num_threads)

    def post_process_song(self, song, download_path: str) -> bool:
        """
        Embed metadata into the downloaded song file.

        Args:
            song: Song object with metadata
            download_path: Directory where the song was downloaded

        Returns:
            True if successful, False otherwise
        """
        if not self.embed_metadata:
            return True

        try:
            # Find the downloaded file
            file_path = self._find_downloaded_file(song, download_path)
            if not file_path:
                logger.warning(f"Could not find downloaded file for {song.name}")
                return False

            # Import here to avoid hard dependency
            try:
                from utils.metadatautils import embed_metadata as embed
                return embed(file_path, song, embed_art=False)
            except ImportError:
                logger.warning("metadatautils module not available, skipping metadata embedding")
                return True

        except Exception as e:
            logger.error(f"Failed to post-process song {song.name}: {e}")
            return False

    def download_playlist(self, playlist, download_path):
        # download_path should already include the full playlist path from library.py
        if self._cancel_event.is_set():
            return False
        try:
            os.makedirs(download_path, exist_ok=True)
            command = self._spotdl_cmd('download', [playlist.url], ['--output', download_path, '--threads', '4'])

            self._current_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                output, _ = self._current_process.communicate(timeout=3600)  # 1 hour for full playlist
                if output:
                    logger.debug(output.strip()[-1000:])
            except subprocess.TimeoutExpired:
                self._current_process.kill()
                logger.error(f"Download timed out for playlist '{playlist.name}'")
                return False
            finally:
                returncode = self._current_process.returncode
                self._current_process = None

            if returncode != 0:
                logger.error(f"Failed to download playlist '{playlist.name}'")
                return False
            return True
        except Exception as e:
            self._current_process = None
            logger.error(f"Exception downloading playlist '{playlist.name}': {e}")
            return False

    def download_song(self, song, download_path):
        """Download a single song. Used as fallback; prefer download_songs_batch."""
        result = SyncResult()
        self.download_songs_batch([song], download_path, result)
        return result.success_count > 0

