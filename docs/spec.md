# music-lib-sync — system specification

Current implemented behavior, not a feature wishlist. Planned changes live in [backlog.md](backlog.md); recorded architectural decisions live in [adr/README.md](adr/README.md). An accepted ADR takes precedence for its decision; its implementation status must be explicit rather than implying that planned behavior exists.

## Purpose and boundaries

A Python/PyQt5 desktop application reads Spotify saved tracks and playlists as metadata, finds matching audio on YouTube or SoundCloud through yt-dlp, and writes tagged local audio. Spotify is not the audio source. The former spotdl and legacy ytdl backends are removed.

## User flows

- Select an account and authenticate, then open the sync window.
- Sync saved tracks into `<download_path>/my_songs`.
- Sync accessible playlists into `<download_path>/playlists/<safe name>`; colliding names receive playlist-ID suffixes.
- In the library browser, sync missing tracks for the selected collection, download selected rows, retry failed tracks that remain missing, or queue Sync all across accessible collections. Browse other collections while work continues.
- Run confirmed whole-library Repair Library from the browser or use the retained batch window for all-songs/all-playlists sync and repair.
- Double-click an available local track to play it; use persistent play/pause, previous/next, seek and volume controls. Playback never downloads or streams from Spotify.
- Repair existing library files, then sync again to replace quarantined tracks.
- Edit destination, cookies and output format in Options.
- Cancel active work; closing an active window requests cancellation and waits rather than destroying a running thread.

Authentication is background work. Cached tokens are validated/refreshed before browser authorization. Denial, callback errors and timeouts are reported in the GUI. Required scopes: `user-library-read playlist-read-private playlist-read-collaborative`.

### Library browser and scoped sync

After account selection, the library browser presents Saved tracks and playlists in a sidebar, with an ordered model/view track table, collection-local search and presence filters. Metadata retrieval and filesystem reconciliation run in a background worker; browsing alone does not download, create directories, move files or write tags.

**Sync missing**, **Download selected** and **Retry failed** enqueue operation-scoped jobs for the selected collection. There is one active library mutation job and an explicit queue; selection/navigation does not change a job's scope. Stable operation, collection and track IDs drive live row state, including duplicate playlist rows. Late events from older jobs are ignored. **Cancel jobs** drops queued work and requests cancellation of the active downloader. The destination root is captured when a job is queued, and the library is rescanned after the queue drains. A track is marked Downloaded only after the downloader verifies an existing final file in the collection's current destination.

Sync missing and Sync all do not implicitly flatten, retag or repair existing files. Repair Library is an explicit whole-library operation in the same serialized queue; it captures the destination root, reports aggregate progress/results, invalidates coverage while running, then rescans to show repaired/quarantined files. The retained batch window remains available for all-songs/all-playlists sync and repair.

Local playback uses existing paths only, with a persistent queue built from playable rows in the selected collection's displayed order; navigating collections does not replace the queue. QtMultimedia provides controls and output. In this Windows environment it rejected FLAC/M4A/Opus/Ogg, so [ADR-0002](adr/adr-0002-local-playback-decoding.md) records the FFmpeg fallback: asynchronous decode to a bounded temporary WAV without changing the source. Repair and batch mutations wait asynchronously for playback/decoder file release. The position slider seeks on click, drag and keyboard; Enter plays the selected row and Space toggles pause from the keyboard. Playback failures show a short message naming the file, with technical detail in the log. Generated-audio checks cover all six formats and Computer Use passes exercised playback, pause, seek, next/previous, rapid switching, repair (including a native MP3 being moved while playing), Sync all, cancellation, keyboard use, narrow windows and close; high-DPI scaling and screen readers remain unverified.

Coverage counts unique eligible Spotify track IDs while preserving repeated playlist occurrences as rows. Only supported final files in the collection's current destination satisfy Downloaded coverage. Files elsewhere can be reported separately; `_rejected` originals do not satisfy coverage. Presence is not recording-identity or decoded-audio validation. Empty, restricted, failed, stale and incomplete snapshots must not appear Synced.

## Library and result contract

Spotify pagination is complete-or-error: incomplete listings raise `LibraryFetchError`, not a successful partial library. Transient failures use bounded, cancellable retries. Development Mode playlist ownership restrictions become skip notes; playlist entries accept `item` and the legacy `track` response key.

Track identity uses the `[SpotifyTrackID]` filename suffix across mp3/flac/m4a/opus/ogg/wav. Existing supported audio is not overwritten; changing output format neither transcodes nor duplicates existing tracks. Names are safe, bounded path components retaining track IDs.

Results accumulate success, failure, skipped items, error details, notes and cancellation. Success rate excludes skipped items. Playlist progress is aggregated across the run; download ETA excludes the Spotify-fetch phase.

## Downloads and metadata

An injected Downloader supplies download, cancel, cancellation-state and preflight behavior, plus an optional per-track callback for scoped sync. The callback carries stable Song identity and reports active/terminal phases; success requires the verified final file to exist. YoutubeDownloader searches multiple candidates, filters using Spotify duration, verifies output duration, then embeds metadata. Deadlines and cancellation terminate full subprocess trees.

Native tags/artwork support MP3/WAV ID3, FLAC/Vorbis/Opus and MP4. ID3 uses v2.3; artwork downloads are cached. Spotify metadata can be nullable. Duration matching rejects previews and obvious length mismatches but cannot establish recording identity.

## Repair and data safety

Repair flattens nested track files, excludes `_rejected` from flattening, and quarantines unreadable or grossly wrong-length files without overwriting originals. It writes missing basic metadata and leaves unknown IDs and already-correct files unchanged. Existing-library duration tolerance is more lenient than new-download tolerance. Never delete user audio to resolve a mismatch.

Configuration and token-cache paths are anchored beside `main.py`; config reads disable interpolation and writes are atomic. Destination paths expand `~`. An empty cookies setting uses Firefox. Secrets, cookie/token caches and downloaded audio remain untracked. `test/` is user data; `tests/` is the regression suite.

## External limitations and unimplemented work

Spotify Development Mode requires the app owner to have Premium and limits playlist contents to owned/collaborative playlists. Batch artist/album endpoints are unavailable there. Genre enrichment is not implemented. Provider formats and browser-cookie extraction depend on yt-dlp and can change externally. Live authorization and provider downloads are outside the offline test suite.

## Code map

See [core guidance](agents/core.md), [UI/auth guidance](agents/ui-auth.md), [audio guidance](agents/audio.md), and [test guidance](agents/tests.md). Setup, configuration, logs and recovery procedures: [runbook.md](runbook.md).
