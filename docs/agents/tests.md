# Test guidance

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m pytest tests/test_library.py
python -m pytest -m unit
```

The suite uses offline Spotify/browser fixtures and temporary audio. Native-format metadata tests use FFmpeg when available. Live Spotify authorization and real provider downloads require your own credentials and are not performed by the test suite.

## Isolation and conventions

Runtime requirements are in `requirements.txt`; pytest is in `requirements-dev.txt`. Markers in `pytest.ini`: `unit`, `integration`, `slow`. Tests use temporary audio and isolated logs, never the user download directory. `test/` contains user data, not fixtures. Do not commit credentials, cookies, caches or audio.

Select the existing test file covering the changed area: library, downloader, UI, user/auth, models/results, metadata, file/config/log utilities. Exercise changed runtime behavior as well as regression checks; live auth/download verification requires credentials and must be reported separately from offline results. Do not record fixed suite counts as current evidence.
