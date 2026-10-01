# Core and configuration guidance

- `main.py`: creates QApplication/MainWindow and installs exception reporting hooks.
- `model/library.py`: LibrarySyncSource/SpotifyLibrary; complete-or-error pagination, cancellable Spotify retries, ownership-aware playlists, safe directory naming, dedupe, aggregate progress and repair. `sync_songs` and `sync_playlists` require an injected Downloader. `LibraryFetchError` reports incomplete listings.
- `model/song.py` / `playlist.py`: nullable Spotify metadata handling; Playlist carries ID, skip reason or fetch error.
- `model/sync_result.py`: thread-safe success/failure/skipped counts, DownloadError records, notes and merging. The lock is not a dataclass field; equality/serialization compare only result data. Success rate excludes skipped items.
- `model/library_state.py`: immutable account/collection keys, ordered track snapshots, independent metadata/coverage/operation state and validated WorkerEvent payloads. Unique-ID counts retain duplicate rows. WorkerEvent is not yet emitted by legacy sync; `belongs_to` rejects obsolete operation/collection scopes.
- `SpotifyLibrary.browse_collections`: sidebar metadata first, Saved tracks then selected-priority playlist contents; read-only local index uses the shared destination resolver. Supported top-level files satisfy current-destination coverage; elsewhere and quarantined paths are distinct. Failed/incomplete scans imply unknown coverage, never successful absence.
- `model/downloader.py`: slim abstract download/cancel/is_cancelled interface and preflight contract.
- `utils/configutils.py`: project-root config/cache paths, interpolation-free config reads, home expansion and atomic writes.
- `utils/logutils.py`: one shared `mls` parent logger with UTF-8 rotating file handler and safe console output. `MUSIC_LIB_SYNC_LOG_DIR` overrides the default log directory.

## Invariants

Keep Spotify fetching complete-or-error and retries cancellable. Inject downloaders into sync calls. Preserve nullable metadata and result serialization/equality without the lock. Keep project-root paths, interpolation-free config reads, home expansion and atomic writes. Use the shared `mls` logger; preserve UTF-8 rotation and safe console output.
