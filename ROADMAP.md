# Roadmap

Planned improvements, roughly ordered by priority. Items move to CHANGELOG.md when shipped.

## Near term

### Download progress UI
Currently the sync window shows no progress while a batch is running. Add a progress bar and a live log/status label fed by signals from the worker threads.

### Retry failed downloads
After a batch finishes, surface a "Retry failed" button in the result dialog that re-queues only the tracks that errored.

### Genre metadata
`Song.from_spotify_track()` leaves `genres` empty because the Spotify track endpoint doesn't include genres. Fix by making a secondary call to the album or artist endpoint (already fetched in parallel metadata pass) and merging genres back into the `Song`.

### yt-dlp fallback
`downloaders/ytdl.py` exists but is not wired up. Activate it as a fallback when `spotdl` cannot find a track.

## Medium term

### Multiple account support
`SessionManager` and the UI dropdown support multiple users, but only one account is ever created per session. Expose an "Add account" flow so users can manage several Spotify profiles.

### Incremental sync state
Persist a local record of which track IDs have been downloaded (with timestamp and file path) so that duplicate checks do not rely on the filesystem alone. This enables faster syncs after the library grows large and makes it possible to detect deletions on Spotify's side.

### Auto-sync on schedule
Add an optional background mode that runs a sync at a configured interval (e.g., daily) without opening the GUI.

## Long term

### Additional music sources
Abstract `SpotifyLibrary` further so that other services (Apple Music, Tidal, YouTube Music) can be plugged in following the same `Library` interface.

### Lyrics embedding
After download, fetch synced or unsynced lyrics (via a provider like `syncedlyrics`) and embed them as an ID3 USLT/SYLT frame.

### Packaged installer
Ship as a self-contained executable (PyInstaller / cx_Freeze) so users don't need a Python environment.
