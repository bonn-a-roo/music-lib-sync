# Session Resume — music-lib-sync

Short entrypoint for resuming development. Details belong in the [spec](spec.md), [runbook](runbook.md), [backlog](backlog.md), and [area guidance](agents/README.md).

## State — 2026-10-01

- Modern media-library UI direction recorded in [ADR-0001](adr/adr-0001-media-library-ui.md). Approved minimal dark/cyan styling now implemented in the read-only PyQt browser; integrated scoped sync and playback remain pending.
- Approved styling: minimal dark surfaces, restrained cyan borders/highlights, flat controls and reduced decoration; not super-high contrast. Built-in local playback remains required in the first complete redesigned release.
- Immutable collection/track snapshots, independent metadata/coverage/operation fields, read-only local index and operation-scoped WorkerEvent payload contracts implemented. Legacy batch sync does not emit structured events yet; Sync / repair remains accessible from the browser.
- Preview exercised in Chromium: collection navigation, filters/search, queue/cancel promotion, restricted/synced states, global activity, Details and player selection. Desktop rendering inspected; no real playback or sync connected. This is design-preview evidence, not production feature verification.
- Offline fixture browser smoke proved local presence, duplicate rows/unique counts, search/missing filters, playlist navigation, elsewhere-file exclusion and Restricted display; native Qt widget rendering inspected at 1200×800. Final affected library/UI/model/result checks: 70 passed. Full-suite run before final refinements: 196 passed, one unrelated `test_pythonw_skips_console` failure because pytest capture handlers were included in its handler-count assertion. Live auth/downloads and playback not exercised.

## Next development session

1. Read [../CLAUDE.md](../CLAUDE.md) and the guidance for the affected area.
2. Use the runbook to prepare the environment and run the relevant checks.
3. Integrate selected-collection/track sync, structured event emission, queue/retry/cancellation and repair into the browser using [ADR-0001](adr/adr-0001-media-library-ui.md). Preserve existing batch access until replacement flows work. Then prove playback decoding for all six supported formats and implement persistent local playback before end-to-end cutover. No repeat approval for unchanged visual direction.
   Start with a single mutation-job controller and selected-collection/track planning through the existing downloader. Emit operation/collection/track IDs rather than deriving row states from names/logs; reject late events with `WorkerEvent.belongs_to`. Reconcile each destination after verified completion. Exercise duplicate IDs/titles, partial failure, queued/active cancellation, navigation during work and safe close before replacing the legacy window.
   Known verification debt: fix the logging regression's pytest-capture handler assumption, then run the full suite. Do not interpret the earlier affected-suite pass as a clean full-suite result.
4. Keep implemented behavior in the spec, pending work in the backlog, shipped history in the changelog, and this handoff short and factual.

## Constraints to retain

Never use `test/` as fixtures or delete user audio to fix mismatches. Preserve quarantined originals and existing supported audio. Never commit config secrets, cookies or token caches. Duration is a matching heuristic, not identity proof. Genre enrichment and a user-facing Add account flow remain planned.
