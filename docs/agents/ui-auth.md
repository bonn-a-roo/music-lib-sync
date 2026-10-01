# UI and authentication guidance

- `ui/uimanager.py`: MainWindow handles account selection/background authentication; SyncWindow handles songs, playlists, repair, progress/ETA, cancellation and bounded logs; OptionsWindow edits destination, cookies and audio format. AuthWorker and generic SyncWorker catch exceptions before they escape QThread.run. Manual OAuth URL dialogs stay on the GUI thread.
- `ui/library_browser.py`: authenticated read-only library shell, immutable snapshot model/view, search/presence filtering and cancellable background metadata/scanning worker. Previous rows remain visibly stale on refresh errors. Existing SyncWindow remains accessible through Sync / repair; scoped jobs and playback are not connected.
- `model/user.py`: validates/refreshes cached tokens, performs state-checked loopback OAuth, and caches the authenticated profile. Getters do not call Spotify. Required scopes: `user-library-read playlist-read-private playlist-read-collaborative`.
- `model/session_manager.py`: singleton account list and selected account. Retrieving existing accounts does not authenticate.

## Invariants

Keep dialogs and widget access on the GUI thread. Catch exceptions inside QThread workers. Cancel and wait before closing active work. Account retrieval and profile getters must not trigger authentication/network calls. Refresh cached tokens before browser reauthorization and preserve OAuth state validation. The account list exists, but a user-facing Add account flow remains in the [backlog](../backlog.md).
