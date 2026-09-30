# Roadmap

Planned improvements, roughly ordered by priority. Items move to CHANGELOG.md when shipped.

## Near term

### Retry failed downloads
After a batch finishes, surface a "Retry failed" button in the result dialog that re-queues only the tracks that errored.

### Genre metadata
`Song.from_spotify_track()` leaves `genres` empty because track responses do not include artist genres. Fetch individual artists, cache their genres, and merge them into songs. No album/artist enrichment pass currently exists; Spotify Development Mode no longer supports the batch artist endpoint.

### Browser selector in Options
Add a browser dropdown for automatic cookie extraction. Firefox is the default; an explicit cookies file can be selected instead. Browser/profile support depends on yt-dlp and the operating system.

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
