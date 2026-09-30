import io
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor

import pytest
from utils import logutils

pytestmark = pytest.mark.unit


@pytest.fixture
def isolated_logger(tmp_path, monkeypatch):
    parent = logging.getLogger('mls')
    old_handlers = parent.handlers[:]
    old_configured = getattr(parent, '_mls_configured', False)
    parent.handlers = []
    parent._mls_configured = False
    monkeypatch.setenv('MUSIC_LIB_SYNC_LOG_DIR', str(tmp_path))
    monkeypatch.setattr(logutils.sys, 'stdout', io.StringIO())
    yield parent, tmp_path
    for handler in parent.handlers:
        handler.close()
    parent.handlers = old_handlers
    parent._mls_configured = old_configured


def test_unicode_and_concurrent_loggers_share_rotating_file(isolated_logger):
    parent, path = isolated_logger
    with ThreadPoolExecutor(max_workers=8) as pool:
        loggers = list(pool.map(logutils.get_logger, [f'worker{i}' for i in range(24)]))
    message = '中文 Zażółć gęślą jaźń Кириллица'
    for logger in loggers:
        logger.info(message)
    files = [handler for handler in parent.handlers if isinstance(handler, RotatingFileHandler)]
    assert len(files) == 1
    files[0].flush()
    assert files[0].maxBytes == 5 * 1024 * 1024
    assert files[0].backupCount == 3
    assert (path / 'music-sync.log').read_text(encoding='utf-8').count(message) == 24
    assert all(logger.parent is parent and not logger.handlers for logger in loggers)
    assert parent.propagate is False


def test_unusable_directory_falls_back_to_console(isolated_logger, monkeypatch, capsys):
    parent, path = isolated_logger
    invalid = path / 'not-a-directory'
    invalid.write_text('file', encoding='utf-8')
    monkeypatch.setenv('MUSIC_LIB_SYNC_LOG_DIR', str(invalid))
    logger = logutils.get_logger('fallback')
    logger.info('visible fallback')
    assert not any(isinstance(handler, RotatingFileHandler) for handler in parent.handlers)
    assert 'visible fallback' in capsys.readouterr().out


def test_pythonw_skips_console(isolated_logger, monkeypatch):
    parent, _ = isolated_logger
    monkeypatch.setattr(logutils.sys, 'stdout', None)
    logutils.get_logger('pythonw').info('file only')
    assert len(parent.handlers) == 1
    assert isinstance(parent.handlers[0], RotatingFileHandler)


def test_console_replaces_unencodable_characters(isolated_logger, monkeypatch):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding='ascii', errors='strict')
    monkeypatch.setattr(logutils.sys, 'stdout', stream)
    logutils.get_logger('ascii').info('中文 Łódź Москва')
    stream.flush()
    assert b'INFO: ?? ?' in buffer.getvalue()
    assert stream.errors == 'strict'
