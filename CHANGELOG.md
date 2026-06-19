# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-03-31

### Added
- Parallel metadata fetching from the Spotify API (album + artist details fetched concurrently)
- `SyncResult` model — thread-safe accumulator for success/failure/skipped counts and error details
- `metadatautils` module — embed, read, verify, and export ID3 tags using `mutagen`; supports album art download
- Test suite: `pytest` with `unit` / `integration` / `slow` markers

### Fixed
- Cookie authentication passed correctly to `spotdl` via `--cookie-file`
- UTF-8 encoding for playlist names and console output (no more crashes on non-ASCII titles)

### Changed
- `spotdl` now invoked with batched Spotify URIs in a single subprocess call instead of one call per track

## [0.3.0] - 2026-01-13

### Added
- Browser-based OAuth flow: a local HTTP server on port 8888 handles the Spotify callback automatically
- `requirements.txt`
- `logutils` module — structured logging to `~/.music-lib-sync/logs/music-sync.log`; console shows INFO+, file shows DEBUG+
- `configutils` module — centralized `config.ini` read/write with defaults; exposes `download_path`, `cookies_file`, `audio_format`, and Spotify credentials
- Audio format selector in Options (mp3, flac, m4a, opus, ogg, wav)
- Playlist song checking before download to skip already-present tracks

### Fixed
- Duplicate detection now uses Spotify track IDs instead of filenames (eliminates false matches on renamed files)
- Redirect URI format corrected in `config.example.ini`

### Refactored
- Config management extracted from scattered hardcoded values into `configutils`
- Error handling added throughout download and sync paths

## [0.2.0] - 2023-07-31

### Added
- Separate **Sync Songs** and **Sync Playlists** buttons
- Skip re-download of tracks already present in the download directory

### Changed
- GUI replaced from Tkinter to PyQt5
- Sync runs in a background `QThread` to keep the UI responsive

## [0.1.0] - 2023-06-21

### Added
- Initial Spotify library sync: authenticated via spotipy, downloads saved tracks using `spotdl`
- Basic Tkinter GUI with user account selector

[Unreleased]: https://github.com/your-org/music-lib-sync/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/your-org/music-lib-sync/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/your-org/music-lib-sync/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/your-org/music-lib-sync/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/your-org/music-lib-sync/releases/tag/v0.1.0
