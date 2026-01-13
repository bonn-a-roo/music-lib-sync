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

## Architecture

### Entry Point
- `main.py` - Creates the QApplication and launches the MainWindow

### Layer Structure

**UI Layer (`ui/`)**
- `uimanager.py` - Contains all PyQt5 window classes:
  - `MainWindow` - User selection screen
  - `SyncWindow` - Main sync interface with songs/playlists buttons
  - `OptionsWindow` - Configuration dialog
  - Worker threads for background sync operations (inheriting from QThread)

**Model Layer (`model/`)**
- `user.py` - `SessionManager` (singleton) handles Spotify authentication via spotipy
- `library.py` - Abstract base class `Library` defining the sync interface
- `spotify_library.py` - `SpotifyLibrary` implements the Library interface for Spotify
- `song.py`, `playlist.py` - Data models for tracks and playlists
- `downloadable.py` - Abstract base for items that can be downloaded
- `downloader.py` - Abstract `Downloader` class with threading support

**Downloader Layer (`downloaders/`)**
- `spotifydl.py` - `SpotifyDownloader` wraps the spotdl CLI tool
- `ytdl.py` - YouTube-specific downloader using yt-dlp

**Utilities (`utils/`)**
- `configutils.py` - Configuration file management (config.ini)
- `fileutils.py` - File system operations

### Application Flow

1. User selects account from `SessionManager.get_users()`
2. `SyncWindow` provides two sync options:
   - **Sync Songs** - Downloads user's saved tracks
   - **Sync Playlists** - Downloads user's playlists
3. Sync runs in a background QThread, calling `SpotifyLibrary.sync_songs()` or `SpotifyLibrary.sync_playlists()`
4. Downloads use `SpotifyDownloader` which invokes spotdl via subprocess
5. Existing files are checked to avoid re-downloads ("My Songs" optimization)

### Key Design Patterns

- **MVC** - UI separated from model/business logic
- **Strategy Pattern** - Pluggable downloader implementations for different music sources
- **Singleton** - `SessionManager` manages user sessions globally
- **Template Method** - Abstract `Library` and `Downloader` classes define interfaces

### Configuration

The app uses `config.ini` for settings:
- `download_path` - Where music files are saved
- `cookies_file` - Path to cookies.txt for authenticated downloads

### External Dependencies

- **spotdl** - CLI tool for Spotify downloads (invoked via subprocess)
- **yt-dlp** - Fallback YouTube downloader

### Known Issues

- Spotify credentials are currently hardcoded in the code (should be moved to config)
- No test suite exists
- Limited error handling for download failures
