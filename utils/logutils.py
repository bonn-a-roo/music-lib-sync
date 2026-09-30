import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading

_config_lock = threading.Lock()


class _SafeConsoleStream:
    """Preserve stdout ownership while replacing unsupported console characters."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        try:
            return self.stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self.stream, 'encoding', None) or 'utf-8'
            return self.stream.write(text.encode(encoding, errors='replace').decode(encoding))

    def flush(self):
        self.stream.flush()


def get_logger(name: str) -> logging.Logger:
    """Return a child of the once-configured, shared application logger."""
    parent = logging.getLogger('mls')
    with _config_lock:
        if not getattr(parent, '_mls_configured', False):
            parent.setLevel(logging.DEBUG)
            parent.propagate = False
            try:
                logs_dir = Path(os.environ.get('MUSIC_LIB_SYNC_LOG_DIR') or
                                Path.home() / '.music-lib-sync' / 'logs')
                logs_dir.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(
                    logs_dir / 'music-sync.log', maxBytes=5 * 1024 * 1024,
                    backupCount=3, encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                parent.addHandler(file_handler)
            except OSError:
                # Logging must remain usable even with an unwritable directory.
                pass
            if sys.stdout is not None:
                console_handler = logging.StreamHandler(_SafeConsoleStream(sys.stdout))
                console_handler.setLevel(logging.INFO)
                console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
                parent.addHandler(console_handler)
            parent._mls_configured = True
    return logging.getLogger('mls.' + name)
