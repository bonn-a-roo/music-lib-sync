# ADR-0001 — Media-library desktop UI

- Date: 2026-09-30
- Status: Accepted product/visual direction on 2026-09-30. The user approved the revised minimal dark layout with restrained cyan accents. Library-first browsing and local playback in the first complete redesigned release are confirmed. State/snapshot/event contracts are implemented and offline-validated; playback backend remains a proposal requiring format verification.
- Implementation: Read-only PyQt browser, immutable state/event contracts and filesystem reconciliation implemented. Existing batch sync/repair remains accessible separately. Structured events are not emitted by legacy sync yet; scoped integration, queue and playback are pending. The [interactive visual preview](../design/README.md) remains the approved complete-release visual reference.
- Related work: [backlog](../backlog.md), [session handoff](../session-resume.md).

## Goal

Replace the basic sync-button interface with a modern media-player-style library. The primary task is seeing which tracks are downloaded, which are missing, and what each playlist is doing. Local audio playback is secondary in emphasis but required in the first complete redesigned release, not Spotify streaming.

Success: select a playlist in the sidebar, inspect its track list and local coverage, download missing tracks, observe live status without leaving the list, and play downloaded audio.

## Agreed delivery sequence

1. Finalize stable collection/track identity, local-file reconciliation and structured worker-event contracts.
2. Implement the read-only PyQt library browser using the approved preview: sidebar, Saved tracks, collection header, track table, search/status filters and real local coverage.
3. Connect scoped sync and repair: selected collection/tracks, all collections, retry, queue, live activity and cancellation.
4. Integrate local-file playback and persistent controls after proving supported-format decoding.
5. Verify the complete auth-to-library flow, responsiveness and file safety, then remove obsolete UI paths and update operational documentation.

These are implementation checkpoints, not reduced-scope releases. The first complete redesigned release includes both download visibility/sync controls and local playback. The read-only browser checkpoint must not disable existing sync/repair access before replacements work. Keep implemented behavior in the spec until each replacement is exercised; do not present the approved preview as shipped functionality.

## Existing implementation and constraints

- `ui/uimanager.py` currently contains account/auth, Options and a separate SyncWindow with batch buttons, aggregate progress, bounded logs and result dialogs.
- `SpotifyLibrary.get_playlists()` fetches playlist metadata and contents together. Restricted playlists carry a skip reason; individual fetch failures carry an error. Saved tracks are fetched separately.
- Sync entrypoints currently download saved tracks or all playlists. There is no public single-playlist or selected-track sync operation.
- Worker progress is `(current, total, name)`, not a stable track/playlist event stream. It cannot reliably drive individual row states, especially when titles repeat.
- Local presence is currently a directory-scoped set of track IDs. Playlist paths depend on safe names and collision suffixes. No persistent catalog or playback engine exists.
- Song already carries title, artists, album, artwork URL, Spotify duration and track ID. Playlist has ID, name, songs, skip reason and error, but no artwork field.

Reuse authentication, downloader verification, naming, tagging, repair and cancellation. Stay on Python/PyQt5; a web/Electron migration is not needed for this design.

## Screen structure

```text
+-------------------+------------------------------------------------+
| Library           | Search current list          Account / Settings|
| Saved tracks      |                                                |
|                   | Artwork   Playlist title                       |
| Playlists         |           36 / 48 downloaded · Last refreshed  |
| Name   36/48      | Sync missing   Cancel   Repair   Open folder   |
| Name   Synced     |                                                |
| Name   Restricted | All / Downloaded / Missing / Failed            |
|                   | #  Title / Artist   Album   Duration   Status  |
|                   | Track rows; selection and per-row actions      |
|                   |                                                |
| Refresh library   | Download activity / progress / Details         |
+-------------------+------------------------------------------------+
| Artwork  Track / Artist    Previous  Play/Pause  Next   Seek  Volume |
+--------------------------------------------------------------------+
```

### Visual direction

User-selected direction: minimalistic, dark, originally blue tones; refined after initial preview feedback to darker charcoal/navy surfaces and restrained cyan borders/highlights, explicitly not super-high contrast. Use cyan selectively for active controls, selection indicators, focus and progress, not bright outlines around every panel. Prefer flat surfaces, thin dividers, smaller neutral artwork placeholders, underlined filter tabs and text-led track statuses over gradients, shadows and filled pills. Keep text legible without neon/glow effects. Define shared colors, spacing, typography and component states rather than styling each widget independently. Use album/playlist artwork when available, a neutral placeholder otherwise; artwork failure must not block browsing.

Resizable sidebar and main pane; track headers remain visible while scrolling. Keep download-state badges readable in selected/hovered rows. Pair color with text/icons; no color-only status. Keyboard navigation, visible focus, accessible control names and tooltips for truncated text. Use model/view tables rather than a widget per song for large libraries.

### Navigation and actions

- Saved tracks are a first-class collection alongside playlists.
- Clicking a playlist changes the main view without starting a download or cancelling another playlist's job.
- Header shows downloaded/eligible counts, missing and failed counts, activity and metadata refresh time.
- Search/filter operates on the selected collection; changing a filter never changes sync scope silently.
- Primary action: Sync missing for the selected collection. Also expose Download selected, Retry failed and Sync all accessible collections with explicit scope.
- Keep settings, account/auth feedback, Repair Library and open-folder actions discoverable. Repair stays explicit and preserves the existing confirmation/safety contract.
- Surface activity inline. Logs/errors belong in a collapsible Details panel, not the main browsing surface. Completion should not require dismissing a modal before browsing can continue.

## State model

Keep independent fields for metadata freshness, file coverage and active operation. Do not store a single status string as the source of truth.

### Collection metadata

`not_loaded -> loading -> ready | restricted | error`

Refreshing an existing collection keeps its previous snapshot visible with a stale indicator. A failed or cancelled refresh does not replace it with an empty successful listing. Restricted playlists show the Spotify reason, not zero-track Synced. Empty but successfully loaded playlists show Empty, not an error.

### Local coverage

`unknown | missing | partial | complete`

Unknown means metadata or the directory scan is incomplete. Missing/partial/complete derive from the latest complete eligible-track snapshot and a successful scan of the collection's destination. Count unique downloadable track IDs for coverage; preserve duplicate occurrences in playlist rows. Show skipped/unavailable-entry notes separately and never silently count unsupported items as downloaded.

A supported file with a matching ID means Downloaded, not proof of recording identity or successful deep audio validation. Files in `_rejected`, temporary outputs and unrelated directories do not satisfy coverage. Downloaded files in another playlist may be available for playback, but do not make this collection's destination complete. Explicitly distinguish that case from Downloaded here.

### Collection operation

`idle -> queued -> syncing -> downloading -> idle`

- Syncing: refreshing/reconciling the selected scope and planning missing files.
- Downloading: at least one track is actively being downloaded.
- Cancellation: queued work returns to idle; active work enters cancelling until the worker/process trees stop. Remaining tracks return to their truthful presence state.
- Failure: retain an operation outcome/error alongside coverage. Partial successes remain downloaded; retry targets only relevant failed IDs that are still missing.
- Display priority: restricted/metadata error; cancelling; downloading; syncing; queued; failed outcome; Synced/Partial/Not downloaded/Unknown coverage. Keep counts visible even when the activity badge takes precedence.
- Synced means no active work, a successful current reconciliation and complete local coverage for that snapshot. It is not a perpetual guarantee that Spotify or the filesystem has not changed. Show refresh time and stale/error indicators.

### Track rows

File presence: `unknown | missing | downloaded | quarantined`; transfer activity: `idle | queued | downloading | cancelling`; last attempt outcome: none/succeeded/failed/cancelled. Playback is independent (stopped/playing/paused/error).

Use stable account, collection and track IDs, not display names. A completed download becomes Downloaded only after verified success and an existing final path. Failure never creates a false green badge. A removed file becomes Missing after reconciliation; a bad file moved by repair becomes Quarantined/Missing with a recovery explanation. No automatic destructive cleanup.

## Data and worker design

### Read-only browsing and reconciliation

Separate metadata retrieval and filesystem reconciliation from download commands. Opening the UI must not create directories, flatten files, tag files or start downloads. All Spotify/network calls and potentially large scans stay off the GUI thread.

Load playlist metadata for the sidebar before fetching every playlist's tracks; load selected contents first and reconcile the rest with bounded concurrency. Preserve complete-or-error pagination and cancellation. Cache complete snapshots in memory; persisted browsing snapshots are not required initially. On startup/refresh/root change, treat previous coverage as unknown until rescanned.

Create an in-memory local index of supported files, track IDs and actual paths, scoped by destination and account snapshot. Scan existing layout without moving audio. Centralize the destination resolver used by browsing and sync, including collision naming. Resolve against the full playlist-name set, not only the selected playlist. Recognize renamed/orphaned directories for playback without claiming current-destination coverage or silently moving/deleting them. Persistent download-state storage remains the separate incremental-state backlog item; disk presence is authoritative.

### Download commands and events

Add collection/selected-track operations using the existing downloader rather than a second download pipeline. Preserve the batch saved-track/all-playlist operations through the same planning path; migrate all affected callers when contracts change.

Use structured events carrying operation ID, collection ID, track ID, phase, completed/total counters, final path on success, and error/reason on failure. Include start/success/failure/skip/cancel transitions; never infer row status from yt-dlp text logs or title strings. Operation IDs prevent late events from a finished/cancelled worker overwriting a newer run. Qt signals carry immutable snapshots/events; only the GUI thread mutates visible models.

Keep one active library mutation job initially, with an explicit queue and no simultaneous sync/repair. Deduplicate requested collection/track jobs; completing one destination does not imply a duplicate track's other destination exists. Browse and play while downloading. Report attempted progress separately from downloaded coverage; an attempt failure can advance work progress without increasing coverage.

Cancel selected queued work or the active job with clear scope. Preserve full-process-tree shutdown, exception-safe workers, preflight checks, bounded logs and safe close/wait behavior. Switching accounts/destination invalidates the relevant model snapshot and cannot redirect a running job to a different destination.

## Local playback

Recommended backend: PyQt5 QtMultimedia (`QMediaPlayer`) behind a small playback controller. Validate native Windows codec support before committing to it. FFmpeg availability for downloading does not prove Qt can decode every output format.

Playback uses an existing local path, never a Spotify URL or an implicit download. Double-click a playable row or use its Play action. Support play/pause, previous/next, seek, elapsed/total time and volume. Build the playback queue from downloaded tracks in the selected list in displayed order; selection changes do not silently replace an active queue. Keep playback controls persistent across playlist navigation.

Verify mp3/flac/m4a/opus/ogg/wav on the target environment. If Qt cannot cover the supported formats, document evidence and select an alternative backend/dependency before declaring playback complete; do not silently drop formats. Missing files and decoder errors produce actionable feedback without crashing or changing download success history. Coordinate repair of the currently playing file: stop/release the media before moving it, rather than racing file handles.

## Implementation phases and gates

### 1. Visual design and state contracts

- Completed: interactive visual mockup and restrained-cyan revision, approved by the user on 2026-09-30. Use [the preview](../design/README.md) as the visual reference.
- Carry the preview's theme tokens, responsive layout and control hierarchy into Qt; verify keyboard/focus behavior in the actual desktop UI.
- Completed: immutable collection/track state, unique-ID coverage with duplicate rows, read-only reconciliation and validated operation-scoped WorkerEvent payloads. Transfer/outcome/playback fields remain independent; read-only snapshots do not invent mutation outcomes.
- Offline contract validation passed for loading, empty, restricted, failed/stale snapshots, duplicate IDs, missing/quarantined/elsewhere files, scan failures and obsolete operation scope. Live provider behavior and playback backend support remain separate gates.

### 2. Read-only library browser

- Build the shell, sidebar, collection header and track model/view.
- Introduce background metadata loading, safe destination resolution and local presence/path reconciliation.
- Support search/status filters, counts, refresh, loading/error/restricted states and folder actions.
- Gate: real local files and a Spotify fixture with missing/duplicate/restricted tracks produce truthful rows/counts; browsing performs no file mutations. Inspect the rendered desktop UI.

### 3. Integrated sync and repair

- Add selected-collection and selected-track commands and structured job/track events.
- Wire queue, live badges, coverage updates, cancellation, retry and Details panel.
- Migrate existing batch entrypoints and keep settings/auth/repair available; remove obsolete sync windows once replacement flows are complete.
- Gate: exercise partial success, repeated titles, duplicate IDs, skip, provider failure, cancellation during fetch/download, changing selection during work and safe close. Repair preserves originals and updates row presence.

### 4. Playback

- Prove backend/format support, then integrate the persistent player and playlist queue.
- Gate: real temporary audio in all supported formats; play/pause, seek, next/previous, volume, unavailable files, decoder failure, navigation during playback and repair/file-handle coordination. Do not test with user audio.

### 5. End-to-end cutover

- Verify the redesigned auth-to-library flow and real rendered states, including high-DPI, narrow windows, keyboard operation and a large collection.
- Run affected existing UI/library/downloader regressions; add focused behavior tests for uncertain state transitions and presence boundaries, not style/source-text assertions.
- Update the spec, runbook, area guidance, changelog and handoff to describe implemented behavior. Remove temporary mockups/scaffolding and obsolete UI paths after their replacements work.
- Live Spotify/provider checks require credentials and must be reported separately from offline and temporary-audio checks.

## Acceptance criteria

1. Playlists and Saved tracks are browsable from the left sidebar without launching downloads.
2. Selecting a collection shows its ordered tracks, artists, albums, durations, local status and coverage counts.
3. Missing/downloaded/failed rows are discoverable by filtering; display names do not determine identity.
4. Queued, Syncing, Downloading, Cancelling and Synced states reflect actual work and file coverage; restricted/incomplete/error listings never look successfully synced.
5. Sync selected collection, Download selected, Sync all, Retry failed and Cancel have explicit, correct scopes. Results remain correct while navigating.
6. Local coverage survives application restart by rescanning files; removed/quarantined files no longer show Downloaded. Existing audio is never silently moved, deleted or overwritten.
7. Users can play downloaded local audio from the list with persistent controls, with verified supported-format handling and clear errors.
8. Authentication, settings, repair, preflight reporting, bounded logs and cancellation-safe shutdown remain available.
9. The UI stays responsive during metadata fetches, scanning and downloads, and remains usable with keyboard navigation and high-DPI/resizable layouts.

## Out of scope

Spotify streaming, playlist editing on Spotify, automatic deletion of removed tracks, scheduled sync, genre enrichment, new music providers and a new multi-account management feature. The design must preserve account isolation but does not add the separate Add account flow. This is a desktop UI redesign, not a backend rewrite.
