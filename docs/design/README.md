# Media-library visual preview

Interactive visual proposal: [media-library.html](media-library.html). Design contract: [ADR-0001](../adr/adr-0001-media-library-ui.md).

This is a browser-based design artifact, not an application frontend or a framework migration. It uses fictional tracks and placeholder artwork. No Spotify requests, file operations, downloads or audio playback occur. Controls change simulated state or explain proposed actions. The production application now has a read-only PyQt browser using this visual direction; integrated sync/activity and playback remain pending.

## Visual revision — restrained cyan

User liked the initial layout and requested slightly more contrast, darker backgrounds, cyan borders/highlights and more minimal styling, then clarified that contrast should not be extreme. The revision uses near-black charcoal surfaces with muted cyan (`#78bdc9`), selective thin accent borders, outlined primary/player controls, underlined filter tabs and text-led row statuses. Removed decorative gradients, shadows and filled status pills; reduced placeholder artwork and corner rounding. No neon effects or bright outlines around every surface.

## Open

Open `media-library.html` directly in a browser. Alternatively, from the repository root:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory docs/design
```

Then visit `http://127.0.0.1:8766/media-library.html`.

## Review scenarios

- **After hours:** partial local coverage with downloaded, missing and failed tracks. Try status filters and search.
- **In motion:** a downloading playlist with queued tracks. The activity strip remains visible while browsing another playlist.
- **Blue Sunday:** complete coverage with a Synced badge.
- **Discovery radio:** restricted Spotify access with an explanation, not an empty successful playlist.
- **Saved tracks:** the same coverage-focused browsing layout for saved music.
- **Sync missing:** previews Queued while another job is active, otherwise Syncing. Cancel the active preview to show the queued collection entering Syncing. Refresh the page to reset fictional state.
- Double-click a downloaded row or press Enter to preview player selection; missing files do not change the player selection. Play/pause, previous/next and sliders demonstrate control placement only, without audio.
- Details expands the proposed log/error area. Folder, repair, settings and retry controls explain intent but perform no real operations.

## Verification — 2026-09-30

Rendered and inspected at 1440×960; rendered at 1000×760 with no document horizontal overflow. Exercised collection navigation, missing/search filters, restricted/synced disabled sync actions, queue/cancel promotion, global activity preservation, Details visibility and player selection/next/missing-file refusal. Fixed row re-rendering that prevented double-click selection and notifications that intercepted control clicks. Browser reported no JavaScript errors in the exercised preview.

After the cyan revision, inspected the 1440×960 rendering and exercised missing/search filters, restricted/synced states, player selection, queue/cancel promotion and Details. At 1000×760, document width did not exceed viewport width; browser reported no JavaScript errors. Main/secondary text tokens were checked against the main background for readability; this is not a complete accessibility audit.

## Approval and implementation boundary

The user approved the darker, minimal muted-cyan revision on 2026-09-30. This preview is the visual reference for the PyQt implementation; unchanged styling/layout does not need another approval gate. State/event contracts and playback backend support still require implementation validation. Approval does not mean sync/playback exists in this artifact or that production features have shipped. Remove this temporary proposal after the implemented desktop UI supersedes it.
