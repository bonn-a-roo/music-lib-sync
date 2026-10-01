# music-lib-sync — system specification

Current implemented behavior, not a feature wishlist. Planned changes live in [backlog.md](backlog.md); recorded architectural decisions live in [adr/README.md](adr/README.md). An accepted ADR takes precedence for its decision; its implementation status must be explicit rather than implying that planned behavior exists.

## Purpose and boundaries

A Python/PyQt5 desktop application reads Spotify saved tracks and playlists as metadata, finds matching audio on YouTube or SoundCloud through yt-dlp, and writes tagged local audio. Spotify is not the audio source. The former spotdl and legacy ytdl backends are removed.

## User flows

- Select an account and authenticate, then open the sync window.
- Sync saved tracks into `<download_path>/my_songs`.
- Sync accessible playlists into `<download_path>/playlists/<safe name>`; colliding names receive playlist-ID suffixes.
- Repair existing library files, then sync again to replace quarantined tracks.
- Edit destination, cookies and output format in Options.
- Cancel active work; closing an active window requests cancellation and waits rather than destroying a running thread.

Authentication is background work. Cached tokens are validated/refreshed before browser authorization. Denial, callback errors and timeouts are reported in the GUI. Required scopes: `user-library-read playlist-read-private playlist-read-collaborative`.

### Read-only library browser

After account selection, the library browser presents Saved tracks and playlists in a sidebar, with an ordered model/view track table, collection-local search and presence filters. Metadata retrieval and filesystem reconciliation run in a background worker; browsing does not download, create directories, move files or write tags. **Sync / repair** retains the existing batch operations until scoped browser actions replace them. Local playback and integrated queue/transfer activity remain unimplemented.

Coverage counts unique eligible Spotify track IDs while preserving repeated playlist occurrences as rows. Only supported final files in the collection's current destination satisfy Downloaded coverage. Files elsewhere can be reported separately; `_rejected` originals do not satisfy coverage. Presence is not recording-identity or decoded-audio validation. Empty, restricted, failed, stale and incomplete snapshots must not appear Synced.

## Library and result contract

Spotify pagination is complete-or-error: incomplete listings raise `LibraryFetchError`, not a successful partial library. Transient failures use bounded, cancellable retries. Development Mode playlist ownership restrictions become skip notes; playlist entries accept `item` and the legacy `track` response key.

Track identity uses the `[SpotifyTrackID]` filename suffix across mp3/flac/m4a/opus/ogg/wav. Existing supported audio is not overwritten; changing output format neither transcodes nor duplicates existing tracks. Names are safe, bounded path components retaining track IDs.

Results accumulate success, failure, skipped items, error details, notes and cancellation. Success rate excludes skipped items. Playlist progress is aggregated across the run; download ETA excludes the Spotify-fetch phase.

## Downloads and metadata

An injected Downloader supplies download, cancel, cancellation-state and preflight behavior. YoutubeDownloader searches multiple candidates, filters using Spotify duration, verifies output duration, then embeds metadata. Deadlines and cancellation terminate full subprocess trees.

Native tags/artwork support MP3/WAV ID3, FLAC/Vorbis/Opus and MP4. ID3 uses v2.3; artwork downloads are cached. Spotify metadata can be nullable. Duration matching rejects previews and obvious length mismatches but cannot establish recording identity.

## Repair and data safety

Repair flattens nested track files, excludes `_rejected` from flattening, and quarantines unreadable or grossly wrong-length files without overwriting originals. It writes missing basic metadata and leaves unknown IDs and already-correct files unchanged. Existing-library duration tolerance is more lenient than new-download tolerance. Never delete user audio to resolve a mismatch.

Configuration and token-cache paths are anchored beside `main.py`; config reads disable interpolation and writes are atomic. Destination paths expand `~`. An empty cookies setting uses Firefox. Secrets, cookie/token caches and downloaded audio remain untracked. `test/` is user data; `tests/` is the regression suite.

## External limitations and unimplemented work

Spotify Development Mode requires the app owner to have Premium and limits playlist contents to owned/collaborative playlists. Batch artist/album endpoints are unavailable there. Genre enrichment is not implemented. Provider formats and browser-cookie extraction depend on yt-dlp and can change externally. Live authorization and provider downloads are outside the offline test suite.

## Code map

See [core guidance](agents/core.md), [UI/auth guidance](agents/ui-auth.md), [audio guidance](agents/audio.md), and [test guidance](agents/tests.md). Setup, configuration, logs and recovery procedures: [runbook.md](runbook.md).
