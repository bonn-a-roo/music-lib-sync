# music-lib-sync

A Python/PyQt5 desktop app that reads Spotify saved tracks and playlists, finds matching audio on YouTube or SoundCloud through yt-dlp, and saves tagged local audio. Spotify supplies metadata, not audio.

## Repository contents

| Path | Purpose |
|---|---|
| `main.py`, `ui/` | Desktop entrypoint, windows and background workers |
| `model/` | Accounts, Spotify library, track metadata and sync results |
| `downloaders/`, `utils/` | yt-dlp, tags, file safety, repair, configuration and logs |
| `tests/` | Isolated regression tests; `test/` is user audio, not fixtures |
| `docs/` | Specification, runbook, backlog, handoff, decisions and area guidance |

## Quick start

Requires Python 3.10+, FFmpeg, Node.js 18+, Firefox cookies or an exported cookies file, and a Spotify Developer app. Register exactly `http://127.0.0.1:8888/callback`. Development Mode requires the app owner to have Premium and restricts playlist contents to owned/collaborative playlists.

```bash
pip install -r requirements.txt
```

Copy [config.example.ini](config.example.ini) to `config.ini` beside `main.py`, fill in Spotify credentials, then run:

```bash
python main.py
```

Full setup, configuration, syncing, repair, cancellation and troubleshooting context: [docs/runbook.md](docs/runbook.md). Never commit secrets, cookies, tokens or downloaded audio. Repair quarantines suspicious originals; it does not delete them. Duration matching cannot prove recording identity.

## Development commands

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m pytest tests/test_library.py
python -m pytest -m unit
```

Offline checks do not perform live Spotify authorization or provider downloads. See [test guidance](docs/agents/tests.md).

## Documentation

- Current behavior and limits: [specification](docs/spec.md).
- Setup and operation: [runbook](docs/runbook.md).
- Current handoff and next work: [session resume](docs/session-resume.md) and [backlog](docs/backlog.md).
- Architecture decisions: [ADR index](docs/adr/README.md); accepted decisions take precedence for their scope, with implementation status recorded separately.
- Contributor entrypoint: [CLAUDE.md](CLAUDE.md); [area guidance](docs/agents/README.md).
- Release history: [CHANGELOG.md](CHANGELOG.md).
