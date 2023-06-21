import subprocess

from model.downloader import Downloader


class YoutubeDownloader(Downloader):

    def __init__(self, cookies=None):
        self.cookies = cookies

    def download_playlist(self, playlist, download_path):
        try:
            command = ['yt-dlp', '--extract-audio', '--audio-format', 'mp3', '-o', f'{download_path}/%(title)s.%(ext)s']

            if self.cookies:
                command.extend(['--cookies', self.cookies])

            command.append(f'--yes-playlist')
            command.append(f'https://www.youtube.com/playlist?list={playlist.url}')

            # Capture the output of the youtube-dl command
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)

            # Print the output
            print(output)
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while downloading playlist with ID '{playlist.url}': {e.output}")
        except Exception as e:
            print(f"An error occurred while downloading playlist with ID '{playlist.url}': {str(e)}")

    def download_song(self, song, download_path):
        try:
            command = ['yt-dlp', '--extract-audio', '--audio-format', 'mp3', '-o', f'{download_path}/%(title)s.%(ext)s']

            if self.cookies:
                command.extend(['--cookies', self.cookies])

            command.append(f'ytsearch1:{song.name}')

            # Capture the output of the youtube-dl command
            output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)

            # Print the output
            print(output)
            # print(f"Downloaded '{song_name}' successfully.")
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while downloading '{song.name}': {e.output}")
        except Exception as e:
            print(f"An error occurred while downloading '{song.name}': {str(e)}")