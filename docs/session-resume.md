# Session Resume — music-lib-sync

Short entrypoint for resuming development. Details belong in the [spec](spec.md), [runbook](runbook.md), [backlog](backlog.md), [ADR index](adr/README.md) and [area guidance](agents/README.md).

## State — 2026-10-14

Full offline suite: **239 passed**. Live verification against the user's real Spotify account and yt-dlp was run on 2026-10-14 (results below); everything else in this handoff comes from offline tests and Computer Use passes over generated audio.

### Live verification — 2026-10-14

Run with Computer Use against a throwaway destination in `%TEMP%` seeded with *copies* of library files; `test/` was never written and `config.ini` was restored afterwards.

- Passed: cached-token authentication (no browser), full browse (153 collections in about 90 s: Saved tracks 3539/3662 Partial, 109 playlists never synced, 40 Restricted, 3 Empty), Options destination change and rescan, **Sync missing** on a 2-track playlist (verified durations within 0.05 s of Spotify, tags and artwork), confirmed **Repair Library** (flattened nested folders, quarantined a truncated and a garbage file shown as Quarantined, tagged untagged files with byte-identical audio, left unknown IDs, `.part` leftovers and playlists untouched), Spotify 429 responses recovered by the bounded retries, playback and pause.
- Fixed: closing the app with paused playback left an empty main window and a live process (the deferred close only closed the embedded browser).
- Open: QtMultimedia on Windows reports VBR MP3 durations 3.6–4× too long (e.g. 27:48 for a 7:04 track), so the position label and seek range are wrong; files carry correct Xing headers and mutagen/ffprobe read them correctly. Affects new downloads and existing library files.
- Observations: several files in the user's library have no tags (Repair would add them); `test/my_songs` still contains nested folders and `.part`/`.ytdl` leftovers; the legacy `audio_bitrate` key in `config.ini` is unused (downloads use VBR quality 0, about 228 kbps average); every mutation ends with a full library rescan (about 90 s).
- Not yet run live: Sync or Repair against the user's real library, Sync all, cancellation of a real download.

Implemented and covered by offline tests plus Computer Use passes over generated audio:

- Library browser: collections, search/filters, per-track coverage, **Sync missing / Download selected / Retry failed / Sync all**, confirmed whole-library **Repair Library**, **Cancel jobs**. One serialized, cancellable job queue with stable-ID row updates, captured destination roots and a rescan when the queue drains. The legacy batch window ("Sync / repair") is retained and cannot overlap browser jobs.
- Local playback ([ADR-0002](adr/adr-0002-local-playback-decoding.md)): persistent controls and a per-collection queue on QtMultimedia. On this Windows setup Qt plays only MP3/WAV, so FLAC/M4A/Opus/Ogg use a bounded asynchronous FFmpeg-to-temporary-WAV fallback. Repair, batch work and window close wait until Qt and FFmpeg release files. Click/drag/keyboard seek, Enter/Space from the table, short actionable errors.
- The user confirmed audible output works.

Known limits (documented, not bugs to fix blindly): presence is not validity, so a damaged file with a valid ID counts as Downloaded and a collection can read Synced; repair reports aggregate progress and relies on a rescan for row state; scoped sync never flattens or repairs files; the layout has a minimum width of about 839 px.

## Next development session

1. Read [../CLAUDE.md](../CLAUDE.md) and the guidance for the affected area; run `python -m pytest` first to confirm the baseline.
2. **Fix the VBR MP3 playback duration** reported by Qt (see Live verification), then decide whether live verification is sufficient or should also cover Sync all and cancelling a real download.
3. **Remaining desktop checks**: high-DPI/scaled displays (ask the user to change Windows scaling; Computer Use cannot), a Tab-order and screen-reader audit, and real window resizing.
4. **Decide the cutover** (ADR-0001 phase 5): the core live checks passed on 2026-10-14; retire the legacy batch window once the user agrees, then update spec, runbook and ADR status.
5. Candidate follow-ups, none started: validate audio on playback/repair so damaged files stop reading as Synced; per-row repair outcomes (needs a new event vocabulary, see the ADR-0001 event notes); selected-collection repair; genre enrichment and an Add account flow stay in the backlog.

## Computer Use recipe (what worked, what bit us)

- Resolve the CLI with `where orca`; load the guide with `orca skills get computer-use --json`. Do not print `ORCA_*`/`PI_*` environment variables (the safety classifier blocks it).
- Use a throwaway harness outside the repo (it was deleted; recreate it in `%TEMP%`): generate 20–30 s tones in the six formats with FFmpeg, build `CollectionSnapshot`s from the files on disk, give `SimpleNamespace(library=...)` a fake `browse_collections`, `sync_collection` (emit `WorkerEvent`s, honor `downloader.is_cancelled()`) and `repair_library` (use `utils.repair.quarantine` for a real move), patch `ui.uimanager.YoutubeDownloader` with a fake whose `preflight()` returns `[]`, and patch `ui.library_browser.configutils.get_download_path`. Never use `test/` or the user's music.
- The provider cannot focus or resize windows. Ask the user to bring the target window to the front first, otherwise synthetic clicks land on whatever covers it (this happened once). Our clicks also pull focus, which sent a few keystrokes the user typed elsewhere into the app; ask them not to type during runs.
- Target by `pid:<n>` plus `--window-id` from `list-windows`; get a fresh PID/window id after every relaunch. Click list items and table rows with `--x/--y` (window-local); accessibility `click` on list items did not change the selection. Use `--click-count 2` for double-click and `set-value` to clear text fields.
- Modal dialogs (`QMessageBox`) appear in the tree after a delay; poll for `Yes`/`No` and retry, because `get-app-state` intermittently returns nothing while a modal is open. Do not match accented labels from a heredoc script on Windows (the encoding corrupts them); match with `bot.n`.
- Screenshots may include windows behind the target; trust the accessibility tree for state and treat unrelated content as private.
- A 20–30 s tone decodes faster than a GUI round trip, so "close during decode" is only provable with the automated test.

## Constraints to retain

Never use `test/` as fixtures or delete user audio to fix mismatches. Preserve quarantined originals and existing supported audio. Never commit config secrets, cookies or token caches. Duration is a matching heuristic, not identity proof. Genre enrichment and a user-facing Add account flow remain planned. Keep implemented behavior in the spec, pending work in the backlog, shipped history in the changelog, and this handoff short and factual.
