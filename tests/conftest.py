import atexit
import logging
import os
import shutil
import tempfile

# Keep test runs out of the real ~/.music-lib-sync/logs. Must happen before any
# application module creates its logger (conftest is imported first).
if 'MUSIC_LIB_SYNC_LOG_DIR' not in os.environ:
    _log_dir = tempfile.mkdtemp(prefix='mls-test-logs-')
    os.environ['MUSIC_LIB_SYNC_LOG_DIR'] = _log_dir
    def _cleanup():
        # File handlers keep the log open, which blocks deletion on Windows.
        logging.shutdown()
        shutil.rmtree(_log_dir, ignore_errors=True)

    atexit.register(_cleanup)
