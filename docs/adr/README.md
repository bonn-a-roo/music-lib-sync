# Architecture decisions — index

| ADR | Decision | Status | Implementation |
|---|---|---|---|
| [0001](adr-0001-media-library-ui.md) | Media-library UI, truthful download coverage and local playback | Accepted product/visual direction; state contracts implemented | Read-only browsing, scoped sync, Sync all and queued Repair Library implemented; playback behavior refined by ADR-0002 |
| [0002](adr-0002-local-playback-decoding.md) | Local playback across Qt codec gaps | Accepted implementation choice, amended 2026-10-14 (MP3 decoded for correct timing) | QtMultimedia controls with bounded FFmpeg-to-WAV path for FLAC/M4A/Opus/Ogg and MP3 implemented; six-format generated-audio tests and live library playback pass |

For a new architectural or product decision, add `adr-NNNN-short-title.md` with date, status (proposed/accepted/superseded), context, decision, consequences and explicit implementation status. Link it here, and link related backlog work. Accepted decisions take precedence over the spec for their scope; update the spec when implemented. Preserve superseded decisions and link their replacements rather than rewriting history.
