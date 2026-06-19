# music-lib-sync

A desktop app for syncing your Spotify library (saved tracks and playlists) to a local folder as MP3/FLAC/other audio files.

## Requirements

- Python 3.10+
- [spotdl](https://github.com/spotDL/spotify-downloader) (`pip install spotdl`)
- A [Spotify Developer](https://developer.spotify.com/dashboard) app with:
  - Client ID and Client Secret
  - Redirect URI set to `http://127.0.0.1:8888/callback`

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copy the example config and fill in your Spotify credentials:

```bash
cp config.example.ini config.ini
```

Edit `config.ini`:

```ini
[Settings]
download_path = C:\Users\you\Music\downloads
cookies_file =
audio_format = mp3

[Spotify]
client_id     = YOUR_CLIENT_ID
client_secret = YOUR_CLIENT_SECRET
redirect_uri  = http://127.0.0.1:8888/callback
```

- **`download_path`** — where audio files are saved (default: `~/Music/downloads`)
- **`cookies_file`** — optional path to a `cookies.txt` (Netscape format) for age-restricted content
- **`audio_format`** — output format: `mp3`, `flac`, `m4a`, `opus`, `ogg`, or `wav`

You can also change these at runtime via the **Options** button in the app.

## Running

```bash
python main.py
```

On first launch a browser window opens for Spotify OAuth. After authorizing, the token is cached and future launches skip the browser step.

## Usage

1. Select your Spotify account from the dropdown and click **Go**.
2. On the sync screen:
   - **Sync Songs** — downloads all your saved/liked tracks.
   - **Sync Playlists** — downloads every playlist in your library.
   - **Options** — change download path, cookies file, and audio format.
3. Already-downloaded tracks are skipped automatically (detected by Spotify track ID).
4. A summary dialog appears when sync finishes, listing successes, skips, and any errors.

## Logs

Detailed logs are written to `~/.music-lib-sync/logs/music-sync.log`. Console output shows INFO-level messages.

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run a specific test file
pytest tests/test_models.py

# Run only unit tests
pytest -m unit
```
