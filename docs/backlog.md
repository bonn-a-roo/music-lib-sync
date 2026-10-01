# Backlog — music-lib-sync

The existing feature list was migrated from the root roadmap; the media-library UI redesign was added on 2026-09-30 at the user's request and takes priority before further feature development. All unchecked items are planned, not implemented. Record shipped changes in [../CHANGELOG.md](../CHANGELOG.md) and update [spec.md](spec.md) and [session-resume.md](session-resume.md).

## Current priority — modern media-library UI

Design and acceptance criteria: [ADR-0001](adr/adr-0001-media-library-ui.md). The minimal dark/cyan preview was approved on 2026-09-30. State contracts and the read-only production browser are implemented; integrated scoped work and playback remain pending. All stages below are required for the first complete redesigned release.

- [x] Create, refine and review the concrete visual mockup; dark surfaces and restrained cyan accents approved.
- [x] Finalize collection/track state transitions, local-file reconciliation and structured worker-event contracts; legacy sync event emission remains part of integration.
- [x] Build a read-only library browser: playlist sidebar, Saved tracks, track table, local presence/counts, search and status filters.
- [ ] Integrate scoped sync, live collection/track activity, queue, retry, cancellation and repair.
- [ ] Add local-file playback with persistent controls and verified format support.
- [ ] Verify end-to-end desktop behavior and replace obsolete UI paths; update implemented-behavior documentation.

Coverage and activity are separate: a partially downloaded playlist may be idle or downloading. Synced requires a complete successfully reconciled snapshot. Restricted or failed Spotify listings must not appear synced. Preserve existing audio and quarantined originals.

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
