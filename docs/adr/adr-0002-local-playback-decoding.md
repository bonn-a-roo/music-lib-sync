# ADR-0002 — Cross-format local playback decoding

- Date: 2026-10-05
- Status: Accepted implementation choice; interactive desktop/audio-output verification remains pending.
- Related: Refines the playback recommendation in [ADR-0001](adr-0001-media-library-ui.md) without changing its local-only playback requirement.
- Implementation: `ui/playback.py` supplies persistent controls/queue through QtMultimedia and uses asynchronous FFmpeg-to-WAV fallback for Qt codec gaps. Generated temporary-audio tests exercise all six supported formats. Final Computer Use validation is pending.

## Context

ADR-0001 recommends PyQt5 QtMultimedia (`QMediaPlayer`) only after proving every supported format on the target environment. A Windows smoke test with temporary FFmpeg-generated audio loaded MP3 and WAV in QtMultimedia, but returned `InvalidMedia` for FLAC, M4A, Opus and Ogg. FFmpeg is already an operating requirement for downloads and is available on this environment. Adding VLC/libVLC would add another runtime dependency and deployment requirement.

Playback must use existing local files only, never trigger downloads or Spotify streaming, and must not modify library audio. Repair can move/quarantine files, so mutation jobs must not race a player or decoder holding the source file.

## Decision

- Keep `QMediaPlayer` as the persistent output/transport layer for play/pause, seek, position, volume and track changes.
- Attempt native Qt playback for MP3/WAV. For FLAC/M4A/Opus/Ogg, decode asynchronously with FFmpeg into a unique temporary PCM WAV, then play that file with QtMultimedia. If native Qt playback errors for MP3/WAV, make one bounded FFmpeg fallback attempt.
- Keep temporary output outside the music library. Never overwrite, retag, move or delete the source. Publish/play the temporary WAV only after FFmpeg exits successfully and the output is non-empty and below the temporary-output limit.
- Bound decoding to one active FFmpeg process, a 1 GiB temporary WAV cap (also constrained by available disk space), and a 10-minute preparation timeout. Show an actionable error rather than starting a partial/oversized file.
- Keep playback queue scope and order when navigating collections; queue playable local paths from the displayed collection, including explicitly identified elsewhere files. Playback errors do not imply download failures.
- Before Repair Library or a batch mutation that may flatten/move files, quiesce QtMultimedia and wait asynchronously until it reports `NoMedia` and any FFmpeg process has exited. Do not start the mutation or accept window close while a decoder still owns files. Resume playback after the mutation finishes or is cancelled.

## Consequences

- No additional player package is required; Qt remains responsible for controls/output and the existing FFmpeg runtime fills codec gaps.
- Unsupported-by-Qt formats incur full-file decode latency and temporary disk usage. Very long/large sources may exceed the explicit cap; this is reported rather than consuming unbounded scratch space.
- Qt codec support may differ on other Windows installations; the FFmpeg fallback is part of the supported path, not a reason to claim Qt natively decodes every format.
- Format tests use generated temporary audio. Manual audible output, window lifecycle, keyboard/high-DPI layout, and fallback interaction still require Computer Use on the target desktop.
