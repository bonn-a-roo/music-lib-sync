# Contributor guidance

music-lib-sync is a Python/PyQt5 desktop app. Spotify is the metadata source; yt-dlp supplies matching audio. spotdl and legacy ytdl backends have been removed.

## Read before editing

- [Session resume](docs/session-resume.md): current handoff and next work.
- [Specification](docs/spec.md): implemented behavior and limits.
- [Runbook](docs/runbook.md): setup, configuration and operation.
- [Backlog](docs/backlog.md): planned features, not implemented behavior.
- [Architecture decisions](docs/adr/README.md): decision status and precedence.

## Area rules

Read every affected area before editing:

| Area | Rules |
|---|---|
| Library, models, config and logging | [docs/agents/core.md](docs/agents/core.md) |
| Qt UI, worker lifecycle and OAuth | [docs/agents/ui-auth.md](docs/agents/ui-auth.md) |
| Downloader, tags, filenames and repair | [docs/agents/audio.md](docs/agents/audio.md) |
| Tests and verification | [docs/agents/tests.md](docs/agents/tests.md) |

## Non-negotiable safety

Never commit Spotify secrets, cookies, token caches or downloaded audio. `config.ini` and `.spotipy_cache` live beside `main.py`; destination paths support `~`. Empty cookies means Firefox. Supported formats: mp3/flac/m4a/opus/ogg/wav; legacy `audio_providers` is unused.

`test/` is user data, not fixtures; regression tests live in `tests/`. Preserve existing supported audio, unknown IDs and quarantined originals. Never delete user audio to resolve a mismatch. Duration matching is not recording-identity proof. Genre enrichment is not implemented; Development Mode lacks batch artist/album endpoints.

## Documentation maintenance

Keep the README short. Update the spec for implemented behavior, runbook for operating procedures, backlog for pending work, changelog for shipped changes and session resume for the current handoff. Put detailed implementation guidance in the affected area document rather than duplicating it here. Record new decisions as ADRs with explicit implementation status.
