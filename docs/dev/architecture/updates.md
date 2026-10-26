# Manual Application Updates

[简体中文](../../zh-CN/dev/architecture/updates.md)

[Architecture](../architecture.md) · [Release workflow](../development.md#build-portable-packages)

Updates are explicit user operations. No startup, settings mount, status read, timer, or recovery from a cached download checks GitHub or starts an installation. A running download or installation completes only as part of the action the user requested.

## Ownership

`backend/updates/` owns release metadata, compatibility checks, downloads, package validation, and independent file replacement. Its contracts live in `contracts.py`. It does not import candidate, recommendation, or generation services. `backend/update_cli.py` orchestrates CLI requests before ordinary startup or model preparation. Host assembles the update service, transports HTTP/SSE, and manages shutdown; Application guards tasks, concurrent writes, and Roam before installation.

The General settings component reads local status through `GET /api/updates`. Only explicit `POST` actions to `/api/updates/check`, `/download`, and `/install` perform operations. Existing SSE publishes `updates` events. Download progress does not refresh Roam or cause prefetch. Installation is restricted to localhost clients; LAN clients can check and view status.

`--check-updates` checks and prints JSON without starting a server, tray, setup wizard, or MiniLM preparation. `--update` explicitly checks, downloads, and hands installation to a separate process. With a running instance, it uses that instance's API and lifecycle; otherwise it checks the selected data's task records before preparing a plan. The command exits once installation is handed off so Windows can release its executable. Results are recorded under `data/tmp/updates/result.json`.

## Compatibility and release publication

`scripts/update-policy.json` declares the source-version range the target release supports upgrading from. The target version owns any data initialization or migration needed during its normal startup; the updater only checks the declared range. Maintain the range deliberately when release behavior or persistent data changes; version numbers alone do not prove compatibility. The target must be a newer stable release, accept the current version, match the updater protocol and native platform/architecture, and have a verified native installation smoke. Source checkouts and read-only or overlapping-data installations use manual upgrade instructions.

Native packages embed `resources/installation.json` with schema, version, platform, and architecture. The publisher creates `update.json` from the policy, archives, build reports, and successful native smoke reports. Each asset includes its name, compressed and unpacked sizes, SHA-256, and native verification status. GitHub asset metadata must agree. Missing or unverified metadata offers manual updates rather than guessing.

`scripts/smoke_portable.py` also exercises `scripts/smoke_updates.py`. Release CI passes `--previous-release` to download and start the latest older stable native package, save settings with the old version, and verify failure recovery followed by upgrading to the new package. Checks cover the actual service version, HTTP readiness, existing settings and database records, backups, personal files, and MiniLM weights. `--previous-archive PATH` uses an already downloaded older package. Without an older release, the same-version replacement smoke still runs, but does not enable `install_verified`. Version-tag pushes build releases automatically; the [manual release rerun](../development.md#github-actions-releases) can rebuild the same pinned tag after a workflow correction.

## Installation and recovery

Explicit downloads use `data/cache/updates/<version>/`, verify size and digest, and validate archive paths and symlinks before extraction. macOS uses native archive tools and verifies the existing ad-hoc signatures; no system security settings or quarantine attributes are changed. The app does not auto-install an existing cache on a later launch.

The update plan and helper log live under `data/tmp/updates/`. The helper runs directly from the verified package in `data/cache/updates/`, without copying another runtime. A file lease serializes operations across GUI and CLI. Before replacement the helper waits for the old service and macOS launcher to exit and rejects other processes using the same installation. Frozen restarts reset the PyInstaller environment to load the correct runtime.

Backups under `data/backups/updates/` contain consistent SQLite snapshots and the replaced program files. Windows replaces the executable and `_internal/`; macOS replaces the `.app`; Linux replaces its launcher, packaged runtime, and release documents. The data directory, data-location pointer, images, models, vocabularies, and unrelated installation files remain outside the replacement set.

After replacing program files, the helper runs the existing `--help` entry to check that the bundled runtime loads. This does not prepare data, download dependencies, or start services. It then starts the application once in its original mode. Replacement, runtime-check, or process-launch failures restore the program files and attempt to restart the previous version. Database snapshots are retained for manual recovery; the updater never restores or removes runtime databases.

On macOS, the native launcher supplies its original arguments, including an empty list for a normal Finder launch. The host preserves that list instead of inheriting the service's internal `--cli --no-browser` flags, so a desktop update restarts the menu-bar launcher. The core regression check covers empty and explicit launcher arguments as well as ordinary CLI startup. The native cross-version smoke currently covers CLI restart and data preservation; it does not verify the visible macOS menu bar.

Affected older releases may already have recorded worker flags as their restart arguments. Those records cannot reliably distinguish a desktop launch from an intentional CLI launch. After such an upgrade, quit `PictideService` in Activity Monitor and reopen `Pictide.app` from Finder. The corrected host records the intended mode for subsequent updates.

The runtime check does not establish that business initialization or later operation will succeed. Normal HTTP readiness is verified by the native release smoke, rather than a special application mode or update-only endpoints. Detailed output and the result remain with the update plan. Backups are retained for recovery.

After the user requests installation, the page waits up to two minutes for the service to reconnect. Individual status requests time out after five seconds. If the wait expires, polling stops and a floating notification points to the application log; it does not trigger another check, download, or installation. A later successful local SSE reconnection can still refresh the page.

## Focused verification

Run `python -m unittest tests.backend.updates.test_updates -v`, the architecture checks, and the update browser flows. These use temporary data and simulated release/download responses. Keep this separate from the native package smoke, which runs the packaged executable without submitting generation tasks.
