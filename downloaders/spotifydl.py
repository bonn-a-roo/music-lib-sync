import subprocess
from model.downloader import Downloader
from model.sync_result import SyncResult
from utils.fileutils import create_directory, sanitize_filename
from utils.logutils import get_logger

logger = get_logger(__name__)


class SpotifyDownloader(Downloader):

    def __init__(self, cookies=None):
        self.cookies = cookies

    def download_playlist(self, playlist, download_path):
        download_path = download_path + "/playlists/" + sanitize_filename(playlist.name)

        with self._lock:
            create_directory(download_path)

        try:
            command = ['spotdl', 'download', playlist.url, '--output', download_path, '--threads', '16']

            with self._lock:
                if self.cookies:
                    command.extend(['--cookies', self.cookies])

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            while process.poll() is None:
                output_chunk = process.stdout.read(4096)
                if output_chunk:
                    logger.debug(output_chunk.strip())

            final_output, _ = process.communicate()
            if final_output:
                logger.debug(final_output.strip())

            if process.returncode != 0:
                logger.error(f"Failed to download playlist '{playlist.name}'")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception downloading playlist '{playlist.name}': {e}")
            return False

    def download_song(self, song, download_path):
        download_path = download_path + "/my_songs"

        try:
            command = ['spotdl', 'download', song.url, '--output', download_path, '--threads', '16']

            with self._lock:
                if self.cookies:
                    command.extend(['--cookies', self.cookies])

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            while True:
                output_chunk = process.stdout.read(4096)
                if output_chunk:
                    logger.debug(output_chunk.strip())
                else:
                    break

            final_output, _ = process.communicate()
            if final_output:
                logger.debug(final_output.strip())

            if process.returncode != 0:
                logger.error(f"Failed to download song '{song.name}'")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception downloading song '{song.name}': {e}")
            return False

