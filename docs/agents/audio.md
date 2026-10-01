# Download, metadata and repair guidance

- `downloaders/ytdlp.py`: YoutubeDownloader searches multiple YouTube/SoundCloud candidates, filters by duration, invokes yt-dlp, verifies output duration, embeds metadata, and tracks/kills full process trees on cancellation or timeout. Existing supported audio is protected from overwrite/deletion.
- `utils/fileutils.py`: safe single path components, bounded filenames retaining `[trackID]`, supported-format ID recognition.
- `utils/durationcheck.py`: strict duration tolerance for new downloads; lenient tolerance for existing-library repair.
- `utils/repair.py`: flatten nested track files and quarantine invalid files without overwriting originals. `_rejected` is excluded from flattening.
- `utils/metadatautils.py`: native tags/artwork for MP3/WAV ID3, FLAC/Vorbis/Opus and MP4; duration/basic-tag checks and JSON sidecars. ID3 saves use v2.3; artwork downloads are cached.

## Invariants

Protect existing supported audio from overwrite/deletion. Retain track IDs in bounded safe filenames and dedupe across formats. Cancel/timeout must stop full process trees. Repair quarantines originals without overwrite and excludes `_rejected` from flattening; unknown IDs remain unchanged. Keep strict new-download and lenient repair tolerances distinct. Duration alone does not prove recording identity. Provider behavior and cookie extraction are external dependencies.
