# music-lib-sync

A PyQt5 desktop app that reads your Spotify saved tracks and playlists, finds matching audio on YouTube or SoundCloud, and saves tagged local audio files.

## Requirements

- Python 3.10+
- FFmpeg on PATH, or `ffmpeg.exe` in `~/.spotdl/` (an existing installation is detected; spotdl itself is not required).
- Node.js 18+ on PATH for yt-dlp's YouTube challenge solver.
- Firefox with a profile logged into YouTube, **or** an exported Netscape-format cookies file.
- A Spotify Developer app with client ID, client secret, and the exact redirect URI `http://127.0.0.1:8888/callback` registered in its dashboard.
- Spotify Development Mode requires the app owner to have Premium. Playlist contents are limited to playlists you own or collaborate on; other playlists are reported as skipped.

Install Python dependencies:

```bash
pip install -r requirements.txt
```

yt-dlp downloads its EJS challenge-solver component from GitHub when needed. YouTube, SoundCloud, and browser-cookie extraction can change independently of this app; keep yt-dlp current. Exported cookies are credentials: do not commit or share them.

## Configuration

Copy `config.example.ini` to `config.ini` beside `main.py`, then fill in your Spotify credentials:

```ini
[Settings]
download_path = ~/Music/downloads
cookies_file =
audio_format = mp3

[Spotify]
client_id = YOUR_CLIENT_ID
client_secret = YOUR_CLIENT_SECRET
redirect_uri = http://127.0.0.1:8888/callback
```

- `download_path`: destination root; `~` expands to your home directory.
- `cookies_file`: optional exported cookies file. If empty, yt-dlp reads Firefox cookies.
- `audio_format`: `mp3`, `flac`, `m4a`, `opus`, `ogg`, or `wav`. Converting a lossy source to FLAC/WAV does not restore lost quality.

The Options window edits these settings. Config and token-cache locations are anchored to the project directory, not the launching directory. Config writes are atomic. `config.ini`, cookies and token caches must remain untracked.

## Running

```bash
python main.py
```

Authentication runs in a background thread. Cached tokens are refreshed before opening a browser; the first launch, revoked refresh token, or a change in required scopes needs authorization. The app requests saved-library, private-playlist and collaborative-playlist read permissions. Callback errors, denied access and timeouts are reported in the GUI.

## Syncing and repairing

1. Select the account and click **Go**.
2. **Sync Songs** writes saved tracks into `<download_path>/my_songs`.
3. **Sync Playlists** writes accessible playlists into `<download_path>/playlists/<safe name>`; colliding names receive playlist-ID suffixes.
4. **Repair Library** fixes existing files before you resume sync:
   - Flattens nested track folders left by older filename bugs.
   - Moves unreadable or grossly wrong-length files into that directory's `_rejected` folder, preserving the original for inspection/recovery.
   - Writes missing title/artist metadata, including available Spotify album information and artwork.
   - Leaves unknown track IDs and already-correct files alone.
5. Run sync again after repair to replace quarantined files. Review `_rejected` before deleting any originals yourself.

Already-present tracks are recognized by their `[SpotifyTrackID]` suffix across all supported audio formats. Switching formats does not transcode or duplicate already-present tracks. Existing library files are not overwritten by the downloader.

New downloads search several candidates using Spotify's duration, then verify the actual output file before marking success. This rejects previews and obvious wrong-length matches, but duration alone cannot prove the recording is the correct version. Listen to questionable matches. Genre enrichment is not implemented.

Spotify listing failures are surfaced rather than silently treating a partial library as complete. Transient errors use bounded, cancellable retries; exhausted quota is reported. Playlist progress is aggregated across the run, and download ETA excludes the Spotify-fetch phase.

**Cancel** terminates active downloader process trees and stops further work. Closing an active window requests cancellation and waits; if shutdown is still pending, the window remains open rather than destroying a running thread. Re-running sync skips completed files.

## Logs

UTF-8 logs are written to `~/.music-lib-sync/logs/music-sync.log`, rotating at 5 MiB with three backups. Console output is INFO and above; the file includes DEBUG and yt-dlp output. Set `MUSIC_LIB_SYNC_LOG_DIR` to override the directory. Tests use an isolated log directory.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m pytest tests/test_library.py
python -m pytest -m unit
```

The suite uses offline Spotify/browser fixtures and temporary audio. Native-format metadata tests use FFmpeg when available. Live Spotify authorization and real provider downloads require your own credentials and are not performed by the test suite.
