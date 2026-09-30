import http.server
import secrets
import threading
import time
import webbrowser
from urllib.parse import parse_qs, urlparse

import spotipy
import requests
from urllib3.util.retry import Retry
from spotipy import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler

from model.library import SpotifyLibrary
from utils import configutils
from utils.logutils import get_logger

logger = get_logger(__name__)
SCOPES = 'user-library-read playlist-read-private playlist-read-collaborative'


def _callback_code(url, state):
    query = parse_qs(urlparse(url).query, keep_blank_values=True)
    if query.get('state', [''])[0] != state:
        raise ValueError('Spotify authentication state mismatch. Please retry.')
    if 'error' in query:
        raise ValueError(f"Spotify authorization failed: {query['error'][0]}")
    code = query.get('code', [''])[0]
    if not code:
        raise ValueError('Spotify callback is missing the authorization code.')
    return code


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    timeout = 2

    def do_GET(self):
        if urlparse(self.path).path != self.server.callback_path:
            self.send_response(404)
            self.end_headers()
            return
        try:
            code = _callback_code(self.path, self.server.state)
        except ValueError as exc:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(exc).encode('utf-8'))
            # Malformed or unsolicited requests must not complete authentication.
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
            if query.get('state', [''])[0] == self.server.state and 'error' in query:
                self.server.auth_error = exc
                self.server.done.set()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Authentication successful. You can close this window.')
        self.server.auth_code = code
        self.server.done.set()

    def log_message(self, format, *args):
        pass  # Do not log callback URLs containing credentials.


class OAuthCallbackServer(http.server.HTTPServer):
    allow_reuse_address = True

    def __init__(self, port, state, callback_path='/callback'):
        super().__init__(('127.0.0.1', port), OAuthCallbackHandler)
        self.state = state
        self.callback_path = callback_path
        self.done = threading.Event()
        self.auth_code = None
        self.auth_error = None


class User:
    def __init__(self, scope=SCOPES, manual_url_provider=None, callback_timeout=120,
                 cancel_event=None):
        client_id = configutils.get_spotify_client_id()
        client_secret = configutils.get_spotify_client_secret()
        if not client_id or not client_secret:
            raise ValueError('Spotify credentials not configured. Add client_id and client_secret to config.ini.')
        self.redirect_uri = configutils.get_spotify_redirect_uri()
        self.manual_url_provider = manual_url_provider
        self.callback_timeout = callback_timeout
        self.cancel_event = cancel_event or threading.Event()
        cache_handler = CacheFileHandler(cache_path=configutils.get_token_cache_path())
        self.auth_manager = SpotifyOAuth(
            client_id=client_id, client_secret=client_secret, redirect_uri=self.redirect_uri,
            scope=scope, cache_handler=cache_handler, open_browser=False, show_dialog=False,
        )
        try:
            token = self.auth_manager.validate_token(cache_handler.get_cached_token())
        except Exception:
            logger.exception('Cached Spotify token could not be refreshed')
            token = None
        if not token:
            self._authenticate_with_browser()
        session = requests.Session()
        retry = Retry(total=0, raise_on_status=False, respect_retry_after_header=False)
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        self.auth = spotipy.Spotify(auth_manager=self.auth_manager, requests_session=session,
                                    retries=0, status_retries=0)
        self._user_info = self.auth.current_user()
        self.library = SpotifyLibrary(self.auth)
        self.library._user_id = self._user_info.get('id')
        logger.info('Authenticated as: %s', self.get_name())

    def _authenticate_with_browser(self):
        state = secrets.token_urlsafe(32)
        auth_url = self.auth_manager.get_authorize_url(state=state)
        parsed = urlparse(self.redirect_uri)
        if parsed.port is None:
            if self.manual_url_provider is None:
                raise ValueError('This redirect URI requires a manual URL provider.')
            webbrowser.open(auth_url)
            response = self.manual_url_provider(auth_url)
            if not response:
                raise ValueError('Spotify authentication cancelled: no redirect URL provided.')
            code = _callback_code(response, state)
        else:
            server = OAuthCallbackServer(parsed.port, state, parsed.path or '/')
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            thread.start()
            try:
                webbrowser.open(auth_url)
                deadline = time.monotonic() + self.callback_timeout
                while not server.done.wait(0.05):
                    if self.cancel_event.is_set():
                        raise ValueError('Spotify authentication cancelled.')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Spotify authentication timed out. Please retry.')
                if server.auth_error:
                    raise server.auth_error
                code = server.auth_code
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
        if not self.auth_manager.get_access_token(code, as_dict=False, check_cache=False):
            raise ValueError('Failed to get Spotify access token.')

    def get_raw_info(self):
        return dict(self._user_info)

    def get_email(self):
        return self._user_info.get('email', 'N/A')

    def get_name(self):
        return self._user_info.get('display_name') or self.get_id()

    def get_id(self):
        return self._user_info.get('id', 'N/A')
