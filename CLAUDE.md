# CLAUDE.md

## Project Overview

music-lib-sync is a Python/PyQt5 desktop app that reads Spotify library metadata and downloads matching audio with yt-dlp. Spotify is the metadata source, not the audio source. The former spotdl and legacy ytdl backends have been removed.

## Development Commands

```bash
pip install -r requirements-dev.txt
python main.py
python -m pytest
python -m pytest tests/test_library.py
python -m pytest -m unit
```

Runtime dependencies are in `requirements.txt`; pytest is in `requirements-dev.txt`. FFmpeg and Node.js are external requirements. Tests use temporary audio and isolated logs, not real Spotify authorization or the user's download directory. Pytest markers: `unit`, `integration`, `slow`.

## Architecture

- `main.py`: creates QApplication/MainWindow and installs exception reporting hooks.
- `ui/uimanager.py`: MainWindow handles account selection/background authentication; SyncWindow handles songs, playlists, repair, progress/ETA, cancellation and bounded logs; OptionsWindow edits destination, cookies and audio format. AuthWorker and generic SyncWorker catch exceptions before they escape QThread.run. Manual OAuth URL dialogs stay on the GUI thread.
- `model/user.py`: validates/refreshes cached tokens, performs state-checked loopback OAuth, and caches the authenticated profile. Getters do not call Spotify. Required scopes: `user-library-read playlist-read-private playlist-read-collaborative`.
- `model/session_manager.py`: singleton account list and selected account. Retrieving existing accounts does not authenticate.
- `model/library.py`: LibrarySyncSource/SpotifyLibrary; complete-or-error pagination, cancellable Spotify retries, ownership-aware playlists, safe directory naming, dedupe, aggregate progress and repair. `sync_songs` and `sync_playlists` require an injected Downloader. `LibraryFetchError` reports incomplete listings.
- `model/song.py` / `playlist.py`: nullable Spotify metadata handling; Playlist carries ID, skip reason or fetch error.
- `model/sync_result.py`: thread-safe success/failure/skipped counts, DownloadError records, notes and merging. The lock is not a dataclass field; equality/serialization compare only result data. Success rate excludes skipped items.
- `model/downloader.py`: slim abstract download/cancel/is_cancelled interface and preflight contract.
- `downloaders/ytdlp.py`: YoutubeDownloader searches multiple YouTube/SoundCloud candidates, filters by duration, invokes yt-dlp, verifies output duration, embeds metadata, and tracks/kills full process trees on cancellation or timeout. Existing supported audio is protected from overwrite/deletion.
- `utils/fileutils.py`: safe single path components, bounded filenames retaining `[trackID]`, supported-format ID recognition.
- `utils/durationcheck.py`: strict duration tolerance for new downloads; lenient tolerance for existing-library repair.
- `utils/repair.py`: flatten nested track files and quarantine invalid files without overwriting originals. `_rejected` is excluded from flattening.
- `utils/metadatautils.py`: native tags/artwork for MP3/WAV ID3, FLAC/Vorbis/Opus and MP4; duration/basic-tag checks and JSON sidecars. ID3 saves use v2.3; artwork downloads are cached.
- `utils/configutils.py`: project-root config/cache paths, interpolation-free config reads, home expansion and atomic writes.
- `utils/logutils.py`: one shared `mls` parent logger with UTF-8 rotating file handler and safe console output. `MUSIC_LIB_SYNC_LOG_DIR` overrides the default log directory.

## Configuration and safety

`config.ini` and `.spotipy_cache` live beside `main.py`. Destination paths can use `~`. An empty cookies setting uses Firefox cookies. Supported output formats are mp3/flac/m4a/opus/ogg/wav. Legacy `audio_providers` is no longer used.

Never commit Spotify secrets, cookies, token caches, or downloaded audio. `config.ini`, cookie/cache files, the development `test/` audio directory, and editor-local files are ignored. `tests/` contains regression tests; `test/` is user data, not test fixtures.

Repair quarantines suspicious audio to `_rejected`, writes missing basic metadata, and leaves unknown IDs unchanged. A subsequent sync replaces quarantined tracks. Do not delete user audio to address a mismatch.

## External limitations

Spotify Development Mode limits playlist contents to owned/collaborative playlists and requires the app owner to have Premium. Read playlist entries through `item`, with the deprecated `track` key accepted for existing API responses. Batch artist/album endpoints are unavailable in Development Mode. Genre enrichment is not implemented; duration validation does not prove recording identity. Browser cookie extraction and provider formats depend on yt-dlp and may require dependency updates.
