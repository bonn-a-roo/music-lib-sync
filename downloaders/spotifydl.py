import subprocess

from model.downloader import Downloader
from utils.fileutils import create_directory, sanitize_filename


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

            # Start the subprocess and capture the output
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            while process.poll() is None:
                # Read a chunk of output
                output_chunk = process.stdout.read(4096)  # Adjust the chunk size as needed

                if output_chunk:
                    # Process the output chunk and update progress as needed
                    print(output_chunk)

            # Print the final output
            final_output, _ = process.communicate()
            if final_output:
                print(final_output)

            if process.returncode != 0:
                print(f"An error occurred while downloading the playlist '{playlist.name}'")
        except Exception as e:
            print(f"An error occurred while downloading the playlist '{playlist.name}': {str(e)}")

    def download_song(self, song, download_path):
        download_path = download_path + "/my_songs"

        try:
            command = ['spotdl', 'download', song.url, '--output', download_path, '--threads', '16']

            with self._lock:
                if self.cookies:
                    command.extend(['--cookies', self.cookies])

            # Start the subprocess and capture the output
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            while True:
                # Read a chunk of output
                output_chunk = process.stdout.read(4096)  # Adjust the chunk size as needed

                if output_chunk:
                    # Process the output chunk and update progress as needed
                    print(output_chunk)
                else:
                    break

            # Print the final output
            final_output, _ = process.communicate()
            if final_output:
                print(final_output)

            if process.returncode != 0:
                print(f"An error occurred while downloading '{song.name}'")
        except Exception as e:
            print(f"An error occurred while downloading '{song.name}': {str(e)}")

