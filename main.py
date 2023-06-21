from downloaders import spotydl
import configparser

from model.song import Song
from model.user import get_all_saved_songs_stub, User
from ui import uimanager as ui


def get_download_path_from_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config.get('Settings', 'download_path')


def parse_songs_from_file(file_path):
    songs = []
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

            for line in lines:
                parts = line.strip().split(' - ')

                if len(parts) == 2:
                    name = parts[0].strip()
                    artist = parts[1].strip()

                    song = Song(name, artist)
                    songs.append(song)

    except Exception as e:
        print(f"An error occurred while parsing the file: {str(e)}")

    return songs


def ask_download_path():
    while True:
        download_path = input("Enter the download path: ")
        if download_path.strip():
            return download_path
        else:
            print("Invalid input. Please provide a valid download path.")


def sync_music_library():
    user = User()

    downloader = spotydl.SpotifyDownloader()
    download_path = get_download_path_from_config()
    # download_path = ask_download_path()

    my_songs = user.get_all_saved_songs()
    #my_songs = get_all_saved_songs_stub()
    my_playlists = user.get_playlists()

    downloader.download(my_songs, download_path, num_threads=16)
    #downloader.download(my_playlists, download_path, num_threads=16)

    # cookies_file = "path/to/cookies.txt"

    print("Done")


def main():
    # Call the function to create the main window
    ui.create_main_window()


if __name__ == '__main__':
    main()
