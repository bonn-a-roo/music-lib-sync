# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

music-lib-sync is a Python desktop application for synchronizing music libraries from external services (Spotify) to a local directory. It uses PyQt5 for the GUI and integrates with external download tools (spotdl, yt-dlp) to fetch music content.

## Development Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
python main.py
```

### Running Tests
```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_models.py

# Run tests by marker
pytest -m unit
pytest -m integration
```

Tests are configured in `pytest.ini`. Markers: `unit`, `integration`, `slow`.

## Architecture

### Entry Point
- `main.py` - Creates the QApplication and launches `MainWindow`

### Layer Structure

**UI Layer (`ui/uimanager.py`)**
- `MainWindow` - User selection screen
- `SyncWindow` - Main sync interface (Sync Songs / Sync Playlists buttons)
- `OptionsWindow` - Configuration dialog
- Worker `QThread` subclasses handle background sync so the UI stays responsive

**Model Layer (`model/`)**
- `session_manager.py` - `SessionManager` singleton; holds the active `User` and user list
- `user.py` - `User` wraps spotipy authentication (browser-based OAuth with a local callback server)
- `library.py` / `spotify_library.py` - Abstract `Library` interface + Spotify implementation; `SpotifyLibrary.sync_songs()` / `sync_playlists()` are the top-level sync entry points
- `song.py` - `Song(Downloadable)` — rich Spotify metadata model; `Song.from_spotify_track()` builds from raw API response; `to_metadata_dict()` feeds ID3 embedding
- `playlist.py` - `Playlist(Downloadable)` data model
- `sync_result.py` - Thread-safe `SyncResult` accumulates success/failure/skipped counts and `DownloadError` records during a sync run
- `downloader.py` - Abstract `Downloader` with threading support

**Downloader Layer (`downloaders/`)**
- `spotifydl.py` - `SpotifyDownloader` wraps the `spotdl` CLI via subprocess; sends Spotify URIs in batches; cookies auth is supported
- `ytdl.py` - YouTube fallback using yt-dlp

**Utilities (`utils/`)**
- `configutils.py` - Read/write `config.ini`
- `fileutils.py` - File-system helpers
- `metadatautils.py` - Embed/read/verify ID3 tags (via `mutagen`) and export JSON sidecar files; handles album art download
- `logutils.py` - `get_logger(name)` — writes DEBUG to `~/.music-lib-sync/logs/music-sync.log`, INFO+ to console (UTF-8 safe)

### Application Flow

1. `SessionManager.get_users()` creates/returns `User` objects; first call triggers browser OAuth
2. `SyncWindow` calls `SpotifyLibrary.sync_songs()` or `sync_playlists()` inside a background `QThread`
3. `SpotifyLibrary` fetches track/playlist metadata from Spotify API (parallel where possible), then delegates to `SpotifyDownloader`
4. `SpotifyDownloader` invokes `spotdl` with batched Spotify URIs; cookies file used for authenticated downloads
5. Progress and outcomes accumulate in a `SyncResult`; the UI thread receives signals on completion
6. `metadatautils` can post-process downloaded MP3s to embed/verify ID3 tags

### Configuration (`config.ini`)

- `download_path` — where music files are saved
- `cookies_file` — path to `cookies.txt` for authenticated spotdl downloads
- Spotify credentials live in `config.ini` (not hardcoded); see `config.example.ini` for the format including the correct redirect URI

### Known Issues

- Genres field on `Song` is not populated by the default `from_spotify_track()` path (Spotify track objects don't include genres; a separate album/artist fetch is needed)
- Limited error handling for individual download failures within a batch spotdl call
