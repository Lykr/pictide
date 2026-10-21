# Manual Application Updates

[Architecture](../architecture.md) · [Release workflow](../development.md#build-portable-packages)

Updates are explicit user operations. No startup, settings mount, status read, timer, or recovery from a cached download checks GitHub or starts an installation. A running download or installation completes only as part of the action the user requested.

## Ownership

`backend/updates/` owns release metadata, compatibility checks, downloads, package validation, and independent file replacement. Its contracts live in `contracts.py`. It does not import candidate, recommendation, or generation services. `backend/update_cli.py` orchestrates CLI requests before ordinary startup or model preparation. Host assembles the update service, transports HTTP/SSE, and manages shutdown; Application guards tasks, concurrent writes, and Roam before installation.

The General settings component reads local status through `GET /api/updates`. Only explicit `POST` actions to `/api/updates/check`, `/download`, and `/install` perform operations. Existing SSE publishes `updates` events. Download progress does not refresh Roam or cause prefetch. Installation is restricted to localhost clients; LAN clients can check and view status.

`--check-updates` checks and prints JSON without starting a server, tray, setup wizard, or MiniLM preparation. `--update` explicitly checks, downloads, and hands installation to a separate process. With a running instance, it uses that instance's API and lifecycle; otherwise it checks the selected data's task records before preparing a plan. The command exits once installation is handed off so Windows can release its executable. Results are recorded under `data/tmp/updates/result.json`.

## Compatibility and release publication

`scripts/update-policy.json` declares the source-version range eligible for direct upgrades. Maintain it deliberately when release behavior or persistent data changes; version numbers alone do not prove compatibility. The target must be a newer stable release, accept the current version, match the updater protocol and native platform/architecture, and have a verified native installation smoke. Source checkouts and read-only or overlapping-data installations use manual upgrade instructions.

Native packages embed `resources/installation.json` with schema, version, platform, and architecture. The publisher creates `update.json` from the policy, archives, build reports, and successful native smoke reports. Each asset includes its name, compressed and unpacked sizes, SHA-256, and native verification status. GitHub asset metadata must agree. Missing or unverified metadata offers manual updates rather than guessing.

`scripts/smoke_portable.py` also exercises `scripts/smoke_updates.py`: a copied native runtime applies its own package, verifies a temporary headless service, restarts the application, and checks existing data and MiniLM weights. `install_verified` is enabled per platform only when this smoke passes. Releases still build exclusively on version-tag pushes.

## Installation and recovery

Explicit downloads use `data/cache/updates/<version>/`, verify size and digest, and validate archive paths and symlinks before extraction. macOS uses native archive tools and verifies the existing ad-hoc signatures; no system security settings or quarantine attributes are changed. The app does not auto-install an existing cache on a later launch.

The update plan and copied helper runtime live under `data/tmp/updates/`. A file lease serializes operations across GUI and CLI. Before replacement the helper waits for the old service and macOS launcher to exit and rejects other processes using the same installation. Frozen restarts reset the PyInstaller environment to load the correct runtime.

Backups under `data/backups/updates/` contain consistent SQLite snapshots and the replaced program files. Windows replaces the executable and `_internal/`; macOS replaces the `.app`; Linux replaces its launcher, packaged runtime, and release documents. The data directory, data-location pointer, images, models, vocabularies, and unrelated installation files remain outside the replacement set.

Before the normal application restarts, a temporary headless worker verifies the new runtime and selected data behind a token-protected readiness endpoint. It does not start generation, preference learning, history cleanup, managed ComfyUI, or the browser. On failure the helper restores the program and database snapshots and restarts the previous version. Detailed output and the result remain with the update plan. Backups are retained for recovery.

## Focused verification

Run `python -m unittest tests.backend.updates.test_updates -v`, the architecture checks, and the update browser flows. These use temporary data and simulated release/download responses. Keep this separate from the native package smoke, which runs the packaged executable without submitting generation tasks.
