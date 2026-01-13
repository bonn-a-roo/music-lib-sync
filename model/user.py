import http.server
import socketserver
import socket
import threading
import webbrowser
from urllib.parse import parse_qs

import spotipy
from spotipy import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

from model.library import SpotifyLibrary
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to catch Spotify OAuth callback."""

    def do_GET(self):
        # Check for callback path (either /callback?code= or /?code=)
        if self.path.startswith('/callback?code=') or self.path.startswith('/?code='):
            # Parse the authorization code from the URL
            query = parse_qs(self.path.split('?', 1)[1])
            code = query.get('code', [None])[0]

            if code:
                # Store the code for the main thread to retrieve
                OAuthCallbackHandler.auth_code = code
                logger.info("Received OAuth callback code")

            # Send response to browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html><body><h1>Authentication successful!</h1>
                <p>You can close this window and return to the application.</p></body></html>
            """)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default log messages."""
        pass

    # Class variable to store the auth code between threads
    auth_code = None


def get_available_port():
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class User:

    def __init__(self, scope='user-library-read'):
        client_id = configutils.get_spotify_client_id()
        client_secret = configutils.get_spotify_client_secret()
        redirect_uri = configutils.get_spotify_redirect_uri()

        if not client_id or not client_secret:
            raise ValueError(
                "Spotify credentials not configured. Please edit config.ini and add your "
                "client_id and client_secret from https://developer.spotify.com/dashboard"
            )

        # Use cache handler to persist tokens, avoiding re-authentication
        cache_handler = CacheFileHandler(cache_path='.spotipy_cache')

        self.auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_handler=cache_handler,
            open_browser=False,  # We'll open the browser ourselves
            show_dialog=False,
        )

        logger.info("Initializing Spotify authentication")

        # Try to get cached token first
        cached_token = cache_handler.get_cached_token()

        if not cached_token or not self._is_token_valid(cached_token):
            # Need to authenticate - start local server and open browser
            self._authenticate_with_browser()

        self.auth = spotipy.Spotify(auth_manager=self.auth_manager)
        self.library = SpotifyLibrary(self.auth)

        # Verify authentication worked
        try:
            user_info = self.auth.current_user()
            logger.info(f"Authenticated as: {user_info.get('display_name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def _is_token_valid(self, token_info):
        """Check if the cached token is still valid."""
        return token_info and not self.auth_manager.is_token_expired(token_info)

    def _authenticate_with_browser(self):
        """Open browser and handle OAuth callback with local server."""
        # Extract port from redirect_uri
        import re
        redirect_uri = configutils.get_spotify_redirect_uri()
        port_match = re.search(r':(\d+)', redirect_uri)
        port = int(port_match.group(1)) if port_match else None

        # If no port in redirect_uri (e.g., http://localhost), use manual copy-paste flow
        if port is None:
            logger.info("Using manual copy-paste authentication flow...")
            self._authenticate_manual()
            return

        # Start local HTTP server to catch callback
        OAuthCallbackHandler.auth_code = None

        with socketserver.TCPServer(("127.0.0.1", port), OAuthCallbackHandler) as httpd:
            # Run server in background thread
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            logger.info(f"Local OAuth server started on port {port}")

            # Open browser for user to authorize
            auth_url = self.auth_manager.get_authorize_url()
            logger.info("Opening browser for Spotify authorization...")
            logger.info(f"Auth URL: {auth_url}")
            logger.info(f"Redirect URI in config: {redirect_uri}")
            webbrowser.open(auth_url)

            # Wait for callback
            logger.info("Waiting for OAuth callback...")
            timeout = 120  # 2 minutes
            start_time = __import__('time').time()

            while OAuthCallbackHandler.auth_code is None:
                if __import__('time').time() - start_time > timeout:
                    raise TimeoutError("Authentication timed out. Please try again.")
                __import__('time').sleep(0.5)

            # Get the code and exchange for token
            code = OAuthCallbackHandler.auth_code
            token_info = self.auth_manager.get_access_token(code, as_dict=False, check_cache=False)

            if not token_info:
                raise ValueError("Failed to get access token")

            logger.info("Authentication successful!")

            # Shutdown the server
            httpd.shutdown()

    def _authenticate_manual(self):
        """Manual copy-paste authentication flow for http://localhost redirect URI."""
        auth_url = self.auth_manager.get_authorize_url()
        logger.info("Opening browser for Spotify authorization...")
        logger.info(f"Auth URL: {auth_url}")
        webbrowser.open(auth_url)

        # Qt dialog for URL input (need to import here to avoid circular dependency)
        from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

        class AuthDialog(QDialog):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Spotify Authentication")
                self.setMinimumWidth(500)
                layout = QVBoxLayout()

                layout.addWidget(QLabel("1. Click 'Agree' in the browser"))
                layout.addWidget(QLabel("2. Copy the FULL URL from the browser address bar"))
                layout.addWidget(QLabel("3. Paste it below:"))

                self.url_input = QLineEdit()
                self.url_input.setPlaceholderText("http://localhost/?code=...")
                layout.addWidget(self.url_input)

                submit_btn = QPushButton("Submit")
                submit_btn.clicked.connect(self.accept)
                layout.addWidget(submit_btn)

                self.setLayout(layout)
                self.url = None

            def get_url(self):
                return self.url_input.text()

        # Create and show dialog (blocking)
        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        dialog = AuthDialog()
        dialog.exec()

        redirect_url = dialog.get_url()
        if not redirect_url:
            raise ValueError("No URL provided. Authentication cancelled.")

        logger.info(f"Received redirect URL, exchanging for token...")

        # Extract code from URL and get token
        try:
            code = self.auth_manager.parse_response_code(redirect_url)
            token_info = self.auth_manager.get_access_token(code, as_dict=False)
            if not token_info:
                raise ValueError("Failed to get access token")
            logger.info("Authentication successful!")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def sync_music_library(self):
        return self.library.sync_library_locally()

    def get_raw_info(self):
        return self.auth.current_user()

    def get_email(self):
        return self.auth.current_user().get("email", "N/A")

    def get_name(self):
        return self.auth.current_user().get("display_name", "N/A")

    def get_id(self):
        return self.auth.current_user().get("id", "N/A")