# Session Resume — music-lib-sync

Short entrypoint for resuming development. Details belong in the [spec](spec.md), [runbook](runbook.md), [backlog](backlog.md), [ADR index](adr/README.md) and [area guidance](agents/README.md).

## Next session — 2026-10-14

**Last completed:** MP3 playback now decodes to a temporary WAV so duration and seeking are accurate ([ADR-0002](adr/adr-0002-local-playback-decoding.md) amendment); everything is pushed to `origin/main` (`11cbc09`).
**Next task:** confirm MP3 playback in the GUI (duration label matches the track, slider seek lands correctly, close exits the process), then agree with the user whether to Repair + Sync the real library (see "Open" below).

### To start

- `main` is clean and in sync with `origin/main`. Run `python -m pytest` first; the last full run was 241 passed.
- Live runs need `config.ini` (Spotify credentials, `download_path` = the user's real library `test/`), `.spotipy_cache` (cached token still valid on 2026-10-14), `cookies.txt` (still accepted by yt-dlp), Node.js, FFmpeg and Firefox. All present on this machine; never print or commit their contents.
- `python main.py` → **Go** opens the browser; the first full browse takes about 90 s (153 collections).

### Essential context

- Live verification on 2026-10-14 passed: cached-token auth, full browse, Options destination change, Sync missing on a 2-track playlist (durations within 0.05 s, tags, artwork), confirmed Repair Library (flatten, quarantine shown as Quarantined, tags added with byte-identical audio, unknown IDs and `.part` files untouched), Spotify 429s recovered by retries, playback. It ran against a throwaway `%TEMP%` destination seeded with copies; `test/` was not written.
- Two bugs found live and fixed (see [CHANGELOG](../CHANGELOG.md)): closing with paused playback left an empty window and a live process; Qt's Windows DirectShow backend mis-timed MP3s (VBR Xing header ignored, ID3/artwork bytes counted as audio), so duration and seeking were wrong.
- Media Foundation was evaluated for playback and rejected because it keeps files open after playback stops, which would break Repair; details in the ADR-0002 amendment. Do not switch backends without solving that.
- spotipy prints `HTTP Error ... 429` lines to the console during large refreshes; they are retried and are noise, not failures.

### Open / blockers

- **About 30 s previews in the real library:** 361 of 3557 MP3s in `test/my_songs` last about 30 s. Repair Library would move them to `_rejected` (originals kept) and a later Sync would download full tracks. Needs the user's go-ahead before running on the real library.
- Real library also has untagged files, nested folders from the old filename bug and `.part`/`.ytdl` leftovers; Saved tracks is 3539/3662 and 109 playlists were never synced.
- Not yet run live: Sync or Repair on the real library, Sync all, cancelling a real download.
- Desktop checks need the user: high-DPI scaling (change Windows scaling), Tab order/screen reader, real resizing.
- ADR-0001 phase 5 cutover (retire the legacy "Sync / repair" window): core live checks have passed; waiting for the user's decision.
- Candidate follow-ups, none started: audio validation so damaged files with valid IDs stop reading as Downloaded/Synced; per-row repair outcomes; selected-collection repair; faster post-job refresh (see [backlog](backlog.md)).

### Suggested prompt

> Read docs/session-resume.md. Run the tests, then launch the app and check MP3 playback in the GUI with Computer Use (I'll leave the window in front and won't type). After that, help me decide whether to run Repair Library + Sync on my real library to replace the 30 s previews.

## Implemented (offline tests plus Computer Use and live passes)

- Library browser: collections, search/filters, per-track coverage, **Sync missing / Download selected / Retry failed / Sync all**, confirmed whole-library **Repair Library**, **Cancel jobs**. One serialized, cancellable job queue with stable-ID row updates, captured destination roots and a rescan when the queue drains. The legacy batch window ("Sync / repair") is retained and cannot overlap browser jobs.
- Local playback ([ADR-0002](adr/adr-0002-local-playback-decoding.md)): persistent controls and a per-collection queue on QtMultimedia. Only WAV plays natively; MP3/FLAC/M4A/Opus/Ogg use a bounded asynchronous FFmpeg-to-temporary-WAV path (MP3s over the cap play natively with approximate timing). Repair, batch work and window close wait until Qt and FFmpeg release files.

Known limits (documented, not bugs to fix blindly): presence is not validity, so a damaged file with a valid ID counts as Downloaded and a collection can read Synced; repair reports aggregate progress and relies on a rescan for row state; scoped sync never flattens or repairs files; the layout has a minimum width of about 839 px; every queue drain triggers a full browse (about 90 s here).

## Computer Use recipe (what worked, what bit us)

- Resolve the CLI with `where orca`; load the guide with `orca skills get computer-use --json` (stdout starts with a crashpad warning line; parse from the first `{`). Do not print `ORCA_*`/`PI_*` environment variables.
- Live runs: back up `config.ini` to `%TEMP%` (it holds secrets, so delete the backup afterwards), set a throwaway destination through **Options**, seed it with *copies* of library files, restore the backup at the end. Never let Sync/Repair target `test/` without the user's explicit agreement.
- Offline GUI harness (recreate in `%TEMP%` when needed): generated tones in six formats, `CollectionSnapshot`s from disk, a fake `SimpleNamespace(library=...)` with `browse_collections`/`sync_collection`/`repair_library`, `ui.uimanager.YoutubeDownloader` patched with a fake whose `preflight()` returns `[]`.
- The provider cannot focus windows; ask the user to keep the app in front and not type. `get-app-state --restore-window` restores a minimized window. Target `pid:<n>` plus `--window-id`; refresh both after every relaunch.
- While **Options** (a separate top-level window) is open, `list-windows` shows only Options and the browser returns `windowNotFound`; close Options with a coordinate click on its title-bar X (`Escape` does nothing and `Alt+F4` is rejected as an unsupported key).
- Click list items and table rows with window-local `--x/--y`; use accessibility indexes for buttons; `--click-count 2` to play a row; `set-value` on the search box filters rows.
- After Sync, Repair or an Options save the browser rebrowses everything (about 90 s) and disables mutation buttons; poll for `Library ready` before the next action, or clicks are silently ignored.
- `QMessageBox` confirmations appear in the main window's tree after a short delay; poll for `Yes`. Use `grep -a` on tree output (non-UTF-8 bytes) and match accented labels loosely (`bot.n`).
- Git Bash rewrites `/d/...` arguments for native tools unreliably (ffprobe reported user files as missing); pass Windows paths from Python instead. Scripts that `chdir` into the repo write relative outputs there; check `git status` afterwards.

## Constraints to retain

Never use `test/` as fixtures or delete user audio to fix mismatches. Preserve quarantined originals and existing supported audio. Never commit config secrets, cookies or token caches. Duration is a matching heuristic, not identity proof. Genre enrichment and a user-facing Add account flow remain planned. Keep implemented behavior in the spec, pending work in the backlog, shipped history in the changelog, and this handoff short and factual.
