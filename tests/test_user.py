import http.client
import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse
from unittest.mock import Mock

import pytest
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheHandler
from model import user as module
from model.session_manager import SessionManager

pytestmark = pytest.mark.unit


@pytest.fixture
def auth(monkeypatch, tmp_path):
    token = {'access_token': 'old', 'refresh_token': 'refresh', 'expires_at': 0, 'scope': module.SCOPES}
    class MemoryCache(CacheHandler):
        def get_cached_token(self):
            return token

        def save_token_to_cache(self, token_info):
            token.clear()
            token.update(token_info)

    cache = MemoryCache()
    monkeypatch.setattr(module, 'CacheFileHandler', lambda **kw: cache)
    monkeypatch.setattr(module.configutils, 'get_spotify_client_id', lambda: 'client')
    monkeypatch.setattr(module.configutils, 'get_spotify_client_secret', lambda: 'secret')
    monkeypatch.setattr(module.configutils, 'get_token_cache_path', lambda: str(tmp_path / 'token'), raising=False)
    monkeypatch.setattr(module.configutils, 'get_spotify_redirect_uri', lambda: 'http://127.0.0.1:8888/callback')
    current_user = Mock(return_value={'id': 'id3', 'display_name': 'Bob (the Builder)'})
    monkeypatch.setattr(module.spotipy, 'Spotify', lambda **kw: SimpleNamespace(current_user=current_user))
    monkeypatch.setattr(module, 'SpotifyLibrary', lambda client: SimpleNamespace())
    browser = Mock()
    monkeypatch.setattr(module.webbrowser, 'open', browser)
    return token, cache, current_user, browser


def test_expired_token_refreshes_without_browser(auth, monkeypatch):
    token, cache, profile, browser = auth
    refreshed = dict(token, access_token='new', expires_at=int(time.time()) + 3600)
    refresh = Mock(return_value=refreshed)
    monkeypatch.setattr(SpotifyOAuth, 'refresh_access_token', refresh)
    user = module.User()
    refresh.assert_called_once_with('refresh')
    browser.assert_not_called()
    assert user.get_id() == 'id3'
    assert user.get_name() == 'Bob (the Builder)'
    assert user.get_email() == 'N/A'
    user.get_raw_info()
    manager = SessionManager()
    manager.users = [user]
    manager.set_session_id('id3')
    assert manager.get_selected_user() is user
    profile.assert_called_once()


def test_insufficient_scope_starts_browser(auth, monkeypatch):
    token, cache, profile, browser = auth
    token.update(scope='user-library-read', expires_at=int(time.time()) + 3600)
    monkeypatch.setattr(module.configutils, 'get_spotify_redirect_uri', lambda: 'http://localhost/callback')
    exchange = Mock(return_value='new')
    monkeypatch.setattr(SpotifyOAuth, 'get_access_token', exchange)
    def paste(url):
        state = parse_qs(urlparse(url).query)['state'][0]
        return 'http://localhost/callback?' + urlencode({'state': state, 'code': 'approved'})
    module.User(manual_url_provider=paste)
    browser.assert_called_once()
    exchange.assert_called_once_with('approved', as_dict=False, check_cache=False)


def test_denied_callback_fails_fast(auth, monkeypatch):
    token, cache, profile, browser = auth
    token.clear()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    monkeypatch.setattr(module.configutils, 'get_spotify_redirect_uri', lambda: f'http://127.0.0.1:{port}/callback')
    def deny(url):
        state = parse_qs(urlparse(url).query)['state'][0]
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
        connection.request('GET', '/callback?' + urlencode({'state': state, 'error': 'access_denied'}))
        assert connection.getresponse().status == 400
        connection.close()
    browser.side_effect = deny
    start = time.monotonic()
    with pytest.raises(ValueError, match='access_denied'):
        module.User(callback_timeout=5)
    assert time.monotonic() - start < 2
    profile.assert_not_called()


@pytest.mark.parametrize('query', ['state=expected', 'state=wrong&code=approved'])
def test_bad_callback_rejected(query):
    server = module.OAuthCallbackServer(0, 'expected')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    try:
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=1)
        connection.request('GET', '/callback?' + query)
        response = connection.getresponse()
        assert response.status == 400
        assert not server.done.is_set()
        assert server.auth_code is None
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_manual_state_mismatch(auth, monkeypatch):
    auth[0].clear()
    monkeypatch.setattr(module.configutils, 'get_spotify_redirect_uri', lambda: 'http://localhost/callback')
    with pytest.raises(ValueError, match='state mismatch'):
        module.User(manual_url_provider=lambda url: 'http://localhost/callback?state=wrong&code=x')
