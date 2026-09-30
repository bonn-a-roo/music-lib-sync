import os
import tempfile

# Keep test runs out of the real ~/.music-lib-sync/logs. Must happen before any
# application module creates its logger (conftest is imported first).
os.environ.setdefault('MUSIC_LIB_SYNC_LOG_DIR', tempfile.mkdtemp(prefix='mls-test-logs-'))
