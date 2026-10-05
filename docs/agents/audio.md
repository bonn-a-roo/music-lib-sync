# Download, metadata and repair guidance

- `model/downloader.py` and `downloaders/ytdlp.py`: Downloader exposes an optional per-track callback for downloading/success/failure/skip/cancelled. YoutubeDownloader searches multiple YouTube/SoundCloud candidates, filters by duration, invokes yt-dlp, verifies output duration, embeds metadata, and tracks/kills full process trees on cancellation or timeout. Success callbacks include an existing verified final path; duplicate output paths are serialized and verified audio is protected from cleanup.
- `ui/playback.py`: PlaybackController owns the local queue and QtMultimedia transport; Qt codec failures use an asynchronous, bounded FFmpeg-to-temporary-WAV fallback. Never write fallback audio into the library or begin file-moving repair/batch mutations until the player and decoder are quiescent.
- `utils/fileutils.py`: safe single path components, bounded filenames retaining `[trackID]`, supported-format ID recognition.
- `utils/durationcheck.py`: strict duration tolerance for new downloads; lenient tolerance for existing-library repair.
- `utils/repair.py`: flatten nested track files and quarantine invalid files without overwriting originals. `_rejected` is excluded from flattening.
- `utils/metadatautils.py`: native tags/artwork for MP3/WAV ID3, FLAC/Vorbis/Opus and MP4; duration/basic-tag checks and JSON sidecars. ID3 saves use v2.3; artwork downloads are cached.

## Invariants

Protect existing supported audio from overwrite/deletion, including cancellation races and cleanup errors. Retain track IDs in bounded safe filenames and dedupe across formats. Cancel/timeout must stop full process trees; per-track success callbacks require an existing verified file. Playback uses only existing paths, cleans app-owned temporary WAVs, and releases file handles before repair. Repair quarantines originals without overwrite and excludes `_rejected` from flattening; unknown IDs remain unchanged. Keep strict new-download and lenient repair tolerances distinct. Duration alone does not prove recording identity. Provider behavior and cookie extraction are external dependencies.
