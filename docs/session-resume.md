# Session Resume — music-lib-sync

Short entrypoint for resuming development. Details belong in the [spec](spec.md), [runbook](runbook.md), [backlog](backlog.md), [ADR index](adr/README.md) and [area guidance](agents/README.md).

## State — 2026-10-05

`main` is published at the commit "Document scoped sync, queued repair and local playback (ADR-0002)"; the working tree was clean. Full offline suite: **238 passed**. Nothing in this handoff has been verified against live Spotify or yt-dlp.

Implemented and covered by offline tests plus Computer Use passes over generated audio:

- Library browser: collections, search/filters, per-track coverage, **Sync missing / Download selected / Retry failed / Sync all**, confirmed whole-library **Repair Library**, **Cancel jobs**. One serialized, cancellable job queue with stable-ID row updates, captured destination roots and a rescan when the queue drains. The legacy batch window ("Sync / repair") is retained and cannot overlap browser jobs.
- Local playback ([ADR-0002](adr/adr-0002-local-playback-decoding.md)): persistent controls and a per-collection queue on QtMultimedia. On this Windows setup Qt plays only MP3/WAV, so FLAC/M4A/Opus/Ogg use a bounded asynchronous FFmpeg-to-temporary-WAV fallback. Repair, batch work and window close wait until Qt and FFmpeg release files. Click/drag/keyboard seek, Enter/Space from the table, short actionable errors.
- The user confirmed audible output works.

Known limits (documented, not bugs to fix blindly): presence is not validity, so a damaged file with a valid ID counts as Downloaded and a collection can read Synced; repair reports aggregate progress and relies on a rescan for row state; scoped sync never flattens or repairs files; the layout has a minimum width of about 839 px.

## Next development session

1. Read [../CLAUDE.md](../CLAUDE.md) and the guidance for the affected area; run `python -m pytest` first to confirm the baseline.
2. **Verify live behavior** (needs the user's credentials, Node.js, FFmpeg and a Firefox/cookies profile): authenticate, browse real collections, Sync missing on a small playlist, Repair on a throwaway directory. Report live results separately from offline ones.
3. **Remaining desktop checks**: high-DPI/scaled displays (ask the user to change Windows scaling; Computer Use cannot), a Tab-order and screen-reader audit, and real window resizing.
4. **Decide the cutover** (ADR-0001 phase 5): retire the legacy batch window only after step 2 passes; then update spec, runbook and ADR status.
5. Candidate follow-ups, none started: validate audio on playback/repair so damaged files stop reading as Synced; per-row repair outcomes (needs a new event vocabulary, see the ADR-0001 event notes); selected-collection repair; genre enrichment and an Add account flow stay in the backlog.
6. Small cleanup: `tests/conftest.py` creates a new `mls-test-logs-*` directory in `%TEMP%` on every run and never removes it; older `mls-*` temp directories from earlier sessions can be deleted.

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
