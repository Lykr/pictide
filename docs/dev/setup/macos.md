# macOS development setup

[简体中文](../../zh-CN/dev/setup/macos.md)

[Development workflow](../development.md) · [macOS user guide](../../guides/setup/macos.md)

Run commands from the repository root. Prepare Git, Python, Node.js, and the declared pnpm version; see [requirements](../development.md#prepare-a-checkout).

## Prepare from source

```bash
project_dev="$PWD/dev"
mkdir -p "$project_dev/tmp"
export TMPDIR="$project_dev/tmp" TEMP="$project_dev/tmp" TMP="$project_dev/tmp"
(cd web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build)
chmod +x start.sh start.command
./start.command
```

The source launcher prepares its Python environment under `data/`. Recommendation files are verified and downloaded before HTTP starts. Source startup uses the terminal; the portable `.app` provides the native preparation window and menu-bar lifecycle.

## Ports and data directories

```bash
./start.sh --lan --port 8191 --data-dir dev/verification/macos/data
```

Use a separate port and runtime directory for tests. Source startup already runs in the terminal. Keep test data independent of the user's Application Support directory. For direct Host invocation after preparing the source environment, see `python -m backend.host --help`.

## Build a portable package

Build on a native macOS runner with Xcode Command Line Tools. Confirm Swift is available:

```bash
xcrun --find swiftc
```

Prepare a separate Python builder:

```bash
python3.12 -m venv dev/runtime/builder
./dev/runtime/builder/bin/python -m pip install -r backend/requirements-release.txt
```

Build with the native interpreter:

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py
```

The build compiles `scripts/macos_launcher.swift` with system AppKit, bundles the service, and creates a ZIP containing `Pictide.app`. See [portable builds](../development.md#build-portable-packages) for output, reports, and automatic cleanup. Vocabulary and MiniLM downloads happen at application startup. Signing is ad-hoc; Developer ID signing and notarization are outside the current distribution process.

`Contents/MacOS/Pictide` owns preparation progress, the menu bar, session locking, and its child service. `PictideService` runs Host; browser opening waits for HTTP readiness. Quitting requests normal service shutdown. CLI arguments delegate to the engine:

```bash
/Applications/Pictide.app/Contents/MacOS/Pictide --cli
```

The bundled default data directory is in the user's Application Support location, so replacing the `.app` preserves personal data. Explicit data paths and environment variables take precedence. MiniLM files are downloaded before service startup using the application's shared network and certificate handling.

Intel and Apple Silicon archives have separate native CI builds and startup checks. These checks verify packaging and service readiness, not every Gatekeeper path or local GPU generation. For real Mac validation, use an Actions-built ZIP with a verified checksum; see [manual validation workflow](../development.md#github-actions-releases).
