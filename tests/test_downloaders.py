"""
Tests for downloaders - Spotify and YouTube downloaders with mocked subprocesses.
"""
from unittest.mock import MagicMock, patch, Mock
import pytest

from downloaders.spotifydl import SpotifyDownloader
from downloaders.ytdl import YoutubeDownloader
from model.song import Song
from model.playlist import Playlist
from model.sync_result import SyncResult


class TestSpotifyDownloader:
    """Tests for SpotifyDownloader class."""

    @pytest.mark.unit
    def test_initialization_without_cookies(self):
        """Test creating SpotifyDownloader without cookies."""
        downloader = SpotifyDownloader()
        assert downloader.cookies is None

    @pytest.mark.unit
    def test_initialization_with_cookies(self):
        """Test creating SpotifyDownloader with cookies file."""
        cookies_path = "/path/to/cookies.txt"
        downloader = SpotifyDownloader(cookies=cookies_path)
        assert downloader.cookies == cookies_path

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_playlist_success(self, mock_create_dir, mock_popen):
        """Test successful playlist download."""
        # Mock subprocess
        mock_process = MagicMock()
        # First call to poll() returns None (process running), second returns exit code
        mock_process.poll.side_effect = [None, 0]
        mock_process.returncode = 0
        mock_process.stdout.read.return_value = ""
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        downloader = SpotifyDownloader()
        playlist = Playlist(name="Test Playlist", url="https://open.spotify.com/playlist/test")

        result = downloader.download_playlist(playlist, "/download/path")

        assert result is True
        mock_create_dir.assert_called_once()
        mock_popen.assert_called_once()

        # Verify command structure
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == 'spotdl'
        assert 'download' in call_args
        assert playlist.url in call_args

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_playlist_with_cookies(self, mock_create_dir, mock_popen):
        """Test playlist download with cookies file."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 0]
        mock_process.returncode = 0
        mock_process.stdout.read.return_value = ""
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        cookies = "/cookies.txt"
        downloader = SpotifyDownloader(cookies=cookies)
        playlist = Playlist(name="Test", url="https://open.spotify.com/playlist/test")

        downloader.download_playlist(playlist, "/path")

        call_args = mock_popen.call_args[0][0]
        assert '--cookies' in call_args
        assert cookies in call_args

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_playlist_failure_nonzero_exit(self, mock_create_dir, mock_popen):
        """Test playlist download with non-zero exit code."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 1]  # Returns exit code 1
        mock_process.returncode = 1  # Non-zero = failure
        mock_process.stdout.read.return_value = ""
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        downloader = SpotifyDownloader()
        playlist = Playlist(name="Test", url="https://open.spotify.com/playlist/test")

        result = downloader.download_playlist(playlist, "/path")

        assert result is False

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_song_success(self, mock_create_dir, mock_popen):
        """Test successful song download."""
        mock_process = MagicMock()
        mock_process.stdout.read.side_effect = ["", ""]  # Then return empty to break loop
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        downloader = SpotifyDownloader()
        song = Song(name="Test Song", url="https://open.spotify.com/track/test")

        result = downloader.download_song(song, "/download/path")

        assert result is True

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_song_failure(self, mock_create_dir, mock_popen):
        """Test song download with failure."""
        mock_process = MagicMock()
        mock_process.stdout.read.side_effect = ["", ""]
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        downloader = SpotifyDownloader()
        song = Song(name="Test Song", url="https://open.spotify.com/track/test")

        result = downloader.download_song(song, "/path")

        assert result is False

    @pytest.mark.unit
    @patch('downloaders.spotifydl.subprocess.Popen')
    @patch('downloaders.spotifydl.create_directory')
    def test_download_song_exception_handling(self, mock_create_dir, mock_popen):
        """Test song download exception handling."""
        mock_popen.side_effect = Exception("Subprocess error")

        downloader = SpotifyDownloader()
        song = Song(name="Test Song", url="https://open.spotify.com/track/test")

        result = downloader.download_song(song, "/path")

        assert result is False


class TestYoutubeDownloader:
    """Tests for YoutubeDownloader class."""

    @pytest.mark.unit
    def test_initialization_without_cookies(self):
        """Test creating YoutubeDownloader without cookies."""
        downloader = YoutubeDownloader()
        assert downloader.cookies is None

    @pytest.mark.unit
    def test_initialization_with_cookies(self):
        """Test creating YoutubeDownloader with cookies file."""
        cookies_path = "/path/to/cookies.txt"
        downloader = YoutubeDownloader(cookies=cookies_path)
        assert downloader.cookies == cookies_path

    @pytest.mark.unit
    @patch('downloaders.ytdl.subprocess.check_output')
    def test_download_playlist_success(self, mock_check_output):
        """Test successful playlist download."""
        mock_check_output.return_value = "Download output"

        downloader = YoutubeDownloader()
        playlist = Playlist(name="Test Playlist", url="playlist_id_123")

        # Method doesn't return anything, just check it doesn't crash
        downloader.download_playlist(playlist, "/download/path")

        mock_check_output.assert_called_once()
        call_args = mock_check_output.call_args[0][0]
        assert 'yt-dlp' in call_args

    @pytest.mark.unit
    @patch('downloaders.ytdl.subprocess.check_output')
    def test_download_playlist_with_cookies(self, mock_check_output):
        """Test playlist download with cookies file."""
        mock_check_output.return_value = "Output"

        cookies = "/cookies.txt"
        downloader = YoutubeDownloader(cookies=cookies)
        playlist = Playlist(name="Test", url="playlist_id")

        downloader.download_playlist(playlist, "/path")

        call_args = mock_check_output.call_args[0][0]
        assert '--cookies' in call_args
        assert cookies in call_args

    @pytest.mark.unit
    @patch('builtins.print')
    def test_download_playlist_error_handling(self, mock_print):
        """Test playlist download error handling."""
        from subprocess import CalledProcessError
        import subprocess

        # Simulate CalledProcessError with output attribute
        error = CalledProcessError(1, 'cmd')
        error.output = "Error output"

        with patch('downloaders.ytdl.subprocess.check_output', side_effect=error):
            downloader = YoutubeDownloader()
            playlist = Playlist(name="Test", url="playlist_id")

            # Should handle exception and print error
            downloader.download_playlist(playlist, "/path")

            # Verify error was printed
            mock_print.assert_called()

    @pytest.mark.unit
    @patch('downloaders.ytdl.subprocess.check_output')
    def test_download_song_success(self, mock_check_output):
        """Test successful song download."""
        mock_check_output.return_value = "Download complete"

        downloader = YoutubeDownloader()
        song = Song(name="Test Song")

        downloader.download_song(song, "/download/path")

        call_args = mock_check_output.call_args[0][0]
        assert 'ytsearch1:Test Song' in call_args

    @pytest.mark.unit
    @patch('builtins.print')
    def test_download_song_error_handling(self, mock_print):
        """Test song download error handling."""
        from subprocess import CalledProcessError

        error = CalledProcessError(1, 'cmd')
        error.output = "Download failed"

        with patch('downloaders.ytdl.subprocess.check_output', side_effect=error):
            downloader = YoutubeDownloader()
            song = Song(name="Test Song")

            downloader.download_song(song, "/path")

            mock_print.assert_called()


class TestDownloaderBase:
    """Tests for the base Downloader class functionality."""

    @pytest.mark.unit
    def test_download_songs_worker_calls_download_song(self):
        """Test that download_songs_worker calls download_song for each song."""
        from model.downloader import Downloader

        # Create a minimal concrete implementation
        class TestDownloader(Downloader):
            def download_playlist(self, playlist, download_path) -> bool:
                return True

            def download_song(self, song, download_path) -> bool:
                return True

        with patch('model.downloader.create_directory'):
            downloader = TestDownloader()
            songs = [
                Song(name="Song1", url="url1"),
                Song(name="Song2", url="url2"),
                Song(name="Song3", url="url3")
            ]
            result = SyncResult()

            downloader.download_songs_worker(songs, "/path", result)

            assert result.success_count == 3
            assert result.failure_count == 0

    @pytest.mark.unit
    def test_download_songs_worker_handles_failures(self):
        """Test that download_songs_worker records failures."""
        from model.downloader import Downloader

        class TestDownloader(Downloader):
            def __init__(self, fail_on=None):
                self.fail_on = fail_on or []

            def download_playlist(self, playlist, download_path) -> bool:
                return True

            def download_song(self, song, download_path) -> bool:
                return song.name not in self.fail_on

        with patch('model.downloader.create_directory'):
            downloader = TestDownloader(fail_on=["Song2"])
            songs = [
                Song(name="Song1", artist="Artist1", url="url1"),
                Song(name="Song2", artist="Artist2", url="url2"),
                Song(name="Song3", artist="Artist3", url="url3")
            ]
            result = SyncResult()

            downloader.download_songs_worker(songs, "/path", result)

            assert result.success_count == 2
            assert result.failure_count == 1
            # str(song) returns "name - artist"
            assert result.errors[0].item_name == "Song2 - Artist2"

    @pytest.mark.unit
    @patch('model.downloader.threading.Thread')
    def test_download_with_songs_uses_threads(self, mock_thread):
        """Test that download method creates threads for songs."""
        from model.downloader import Downloader

        class TestDownloader(Downloader):
            def download_playlist(self, playlist, download_path) -> bool:
                return True

            def download_song(self, song, download_path) -> bool:
                return True

        # Capture the worker function and execute it immediately
        workers_started = []

        def capture_thread(target, args):
            workers_started.append((target, args))
            # Execute the worker immediately
            target(*args)
            m = MagicMock()
            m.join = MagicMock()
            return m

        mock_thread.side_effect = capture_thread

        with patch('model.downloader.create_directory'):
            downloader = TestDownloader()
            # Use 4 songs (evenly divisible by 2 threads)
            songs = [Song(name=f"Song{i}", artist=f"Artist{i}") for i in range(4)]

            result = downloader.download(songs, "/path", num_threads=2)

            # Should have created 2 threads
            assert len(workers_started) == 2
            assert result.success_count == 4
