# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Read-only PyQt library browser with Saved tracks/playlist navigation, background metadata and local-file reconciliation, track search/presence filters and retained batch sync/repair access.
- Immutable collection/track snapshots and structured operation-event contracts separating metadata freshness, local coverage and transfer activity.
- Repair Library: flatten nested tracks, quarantine wrong-length/unreadable originals, and tag existing audio with missing basic metadata.
- Multi-candidate searches, Spotify-duration checks, and verification of decoded output before recording download success.
- Native tagging and artwork for all six output formats; cached artwork downloads.
- Blocking-prerequisite checks, download-attempt deadlines, and whole-process-tree cancellation.
- Offline regressions for authentication, GUI worker failures, retries, safe filenames, repairs, tagging and subprocess shutdown.

### Fixed
- Unhandled worker exceptions aborting the entire PyQt application.
- Expired-token browser reauthorization instead of refresh; denied authorization, state validation, and GUI-thread blocking.
- Slash/template characters in titles creating nested or incorrect filenames.
- Silent partial Spotify listings and empty-playlist results after fetch failures.
- Wrong skip counts, resetting playlist progress, and ETA including library-fetch time.
- Account selection receiving a button boolean as an index and parsing IDs from display names.
- Ignored audio-format/cookie settings, empty-setting persistence, literal `~` paths, and current-directory-dependent configuration.
- Missing tags on new downloads, nullable Spotify metadata, invalid numeric tags discarding other metadata, and SyncResult lock serialization/equality.
- Mixed-encoding/unbounded logs and tests writing into the user's log directory.

### Changed
- Background authentication and one exception-safe sync/repair worker.
- Spotify Development Mode ownership restrictions are surfaced as skip notes; item responses accept the current `item` key.
- Runtime dependencies use current Spotify/yt-dlp APIs; pytest moved to `requirements-dev.txt`.
- Duration-only matching remains a heuristic; unknown track IDs and existing audio are preserved.
- Reorganized documentation into specification, runbook, backlog, session handoff, ADR index and area guidance under `docs/`, following fallas-nfc's structure; replaced the root roadmap with `docs/backlog.md`.

### Removed
- Unused spotdl and legacy ytdl backends, dead WIP paths and obsolete provider options.
- Tracked configuration secrets from the local unpushed history; local config remains on disk, untracked. Secret rotation still requires the Spotify dashboard.
- Editor files from tracking and the stray Windows `nul` artifact; development audio is ignored.

## [0.5.0] - 2026-06-19

### Added
- **`YoutubeDownloader`** (`downloaders/ytdlp.py`) — new primary downloader that calls `yt-dlp` directly instead of `spotdl`:
  - Searches YouTube with `ytsearch1:{artist} - {title}` per track
  - Forces HLS/m3u8 format (`bestaudio[protocol=m3u8_native]/…`) which works where DASH formats return HTTP 403
  - Reads Firefox cookies via `--cookies-from-browser firefox` (avoids Windows DPAPI encryption that blocks Chrome/Edge)
  - Uses Node.js + EJS challenge solver (`--remote-components ejs:github`) for YouTube's JS challenges
  - Output filename includes the Spotify track ID so existing deduplication logic (`[trackid].mp3`) continues to work
- **Real-time terminal output pane** in `SyncWindow`: a `QPlainTextEdit` below the progress bar streams each `yt-dlp` output line as it arrives, auto-scrolling to the latest entry
- **Progress bar** and **Cancel button** in `SyncWindow` — the UI no longer freezes during sync
- `audio_providers` setting in `config.ini` / Options window (kept for spotdl compatibility)
- `SyncResult.cancelled` flag; summary prefixed with "Sync cancelled." when set

### Changed
- Workers (`SyncSongsWorker`, `SyncPlaylistsWorker`) now use `YoutubeDownloader` instead of `SpotifyDownloader`
- `download_songs_batch` reads subprocess stdout line-by-line (real-time) instead of waiting for `communicate()` to return
- Log pane appears during sync and hides after the summary dialog

### Fixed
- Download failures caused by `spotdl`'s `filter_results` rejecting all YouTube search results
- HTTP 403 on DASH audio formats (`251`/`140`) — resolved by switching to HLS streams

## [0.4.0] - 2026-03-31

### Added
- Parallel playlist-item fetching (no separate album/artist enrichment pass).
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

[Unreleased]: https://github.com/bonn-a-roo/music-lib-sync/commits/main/
