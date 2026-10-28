# Development workflow

[简体中文](../zh-CN/dev/development.md)

[Developer documentation](README.md) · [Focused smoke checks](testing.md)

The repository root contains `README.md`, `backend/`, `web/`, and the launch scripts. `main` holds verified integration results; `origin` is `git@github.com:Lykr/pictide.git`.

Follow [task setup](#start-a-task) → [environment preparation](#prepare-a-checkout) → [verification](#verify-and-commit) → [integration](#integrate-and-deploy).

## Start a task

Inspect existing work before changing files:

```shell
git status --short --branch
git diff
```

Use a separate task branch. Codex branches use `codex/<topic>`; other contributors may use `feat/`, `fix/`, or `chore/`. Use separate worktrees, data directories, and ports for parallel work or changes involving running instances:

```shell
git worktree add ../pictide-example -b codex/example main
cd ../pictide-example
```

Check whether the branch or directory already exists. Git carries source files; ignored data and dependencies are prepared separately. Simple documentation changes can use a clean checkout directly. When delegating independent work, agree on file ownership, shared interfaces, and delivery requirements.

## Design agreement and data protection

Before changing architecture, cross-module calls or data flow, or public module interfaces, present those three design aspects and obtain user confirmation. Use the Chinese [design template](../zh-CN/dev/design-template.md), focusing on the changes. Reuse approved boundaries without asking again; UI details and internal implementation are autonomous.

Preserve unrelated changes and existing history; do not reset, stash, or rewrite history without authorization. Delegate only worthwhile independent tasks, with explicit file ownership and coordinated interfaces.

Before directly modifying existing user data, back it up. Present historical data deletion as a reviewable inventory and obtain user confirmation. Preserve images, tasks, likes, and preference records; use temporary data for verification. Follow the [data layout](data-layout.md) and [backup procedure](../guides/backup.md).

## Prepare a checkout

Source development needs Git, Python 3.10+, Node.js 20.19+ or 22.12+, and the pnpm version declared in `web/package.json`. Runtime dependencies are in `backend/requirements.txt`; offline processing dependencies are in `corpus/requirements.txt`. Install frontend dependencies from the lockfile.

Follow the instructions for your system:

- [Windows](setup/windows.md#prepare-from-source)
- [Linux](setup/linux.md#prepare-from-source)
- [macOS](setup/macos.md#prepare-from-source)

Build `web/dist/` before using the page or static-asset checks; it is ignored by Git. Each checkout keeps runtime data in its own `data/`. Development dependencies, datasets, caches, and verification outputs belong in `dev/`; see [data layout](data-layout.md).

Use a separate port and temporary data for verification. Prefer neutral fixtures and simulated generation services. Check real ComfyUI connections with read-only requests before any explicitly scoped GPU test. A simulated result verifies orchestration, not image quality or GPU compatibility.

MiniLM is prepared before the HTTP service starts. Portable packages include the inference runtime and a pinned model catalog; model files are downloaded on first startup. See [recommendation dependency preparation](../guides/getting-started.md#recommendation-dependency-preparation).

## Build portable packages

Prepare a native builder environment using the [Windows](setup/windows.md#build-a-portable-package), [Linux](setup/linux.md#build-a-portable-package), or [macOS](setup/macos.md#build-a-portable-package) instructions. Standard Python 3.12 is recommended. Install `backend/requirements-release.txt` into `dev/runtime/builder/`; PyInstaller and its contributed hooks are pinned together. Do not borrow another environment's dependencies through `PYTHONPATH` or site-packages links: the builder rejects dependencies outside its interpreter's install directories. Offline vocabulary production uses a separate environment with `corpus/requirements.txt` and Python 3.11+.

Run `scripts/build_portable.py` with that environment. It installs locked frontend dependencies, checks types, builds temporary frontend assets, prepares resources, creates a PyInstaller directory bundle, and checks its ZIP archive. Temporary assets live under `dev/build/`; the running checkout's `web/dist/` and application `data/` are preserved. Starting the application before packaging is unnecessary.

Portable packages contain the pinned download catalogs in `backend/setup/vocabularies.json` and `backend/recommendation/model.json`, without vocabulary databases or model weights. Building needs no raw dataset, processed library, or corpus-processing dependencies. At startup, existing valid vocabularies are reused; otherwise an interactive terminal chooses an edition and unattended startup defaults to `filtered`. `--vocabulary filtered|all-ratings` explicitly chooses the edition when none is valid. All-ratings is marked as potentially generating explicit content. See [Vocabulary editions](../guides/vocabularies.md).

The build retains FastEmbed, ONNX Runtime, tokenizers, and `backend/recommendation/model.json`, without downloading or bundling MiniLM weights. Python imports and native-library hooks collect runtime code; data-only collection avoids copying all package source files and optional tooling. Startup verifies the selected data directory's model files before exposing HTTP; failures stop startup, and a later attempt resumes retained partial downloads.

Only final `pictide-VERSION-PLATFORM-ARCH.zip` files go into `releases/`. `--output-dir DIR` selects an existing alternative directory. After archive checks succeed, a repeated local build atomically replaces the same ZIP; other versions and previous successful output survive a failed build. Temporary frontend, PyInstaller, and expanded-package directories are cleaned on success or failure. Reports remain in `dev/verification/portable/VERSION-PLATFORM-ARCH/build-report.json`.

Every build records its Python environment, installed dependency versions, and a file inventory with sizes and SHA-256 hashes. Before publishing the local ZIP, the audit rejects loose Python source/bytecode, bundled databases/model weights, and regular binary files duplicated under the same filename with identical contents. Identical license notices and differently named library aliases remain visible in the report without automatic removal. Review the inventory and archive-size changes when changing dependencies or collection rules; run the native inference and upgrade smoke before delivery.

Windows packages expose `Pictide.exe` beside `_internal/`, with `data/` as the default runtime location. macOS packages contain `Pictide.app`, a small native AppKit launcher, and default to the user's Application Support directory. macOS builds use ad-hoc signing without Developer ID signing or notarization. Linux uses `start.sh` in a ZIP. ComfyUI and image-generation weights are optional runtime downloads, separate from the portable archive.

## GitHub Actions releases

`.github/workflows/release.yml` runs on pushed `v*` tags. It builds Windows x64, Linux x64, macOS ARM64, and macOS Intel packages, plus Linux amd64/arm64 Docker images, on native runners. The tag without `v` must match the versions in `backend/__init__.py` and `web/package.json`.

1. Publish [vocabulary editions](corpus.md#export-both-vocabulary-editions) as immutable resource Release assets when the vocabulary changes.
2. Update `backend/setup/vocabularies.json` from the published editions manifest when needed, retaining the release tag, edition file sizes and SHA-256 hashes. Commit the catalog and application version changes.
3. Confirm the tagged commit includes the workflow, lock, and matching versions; create and push the version tag. For example, when both source versions are `0.5.0`:

```shell
git tag v0.5.0
git push origin v0.5.0
```

Use a new version for each release; existing published versions and assets are preserved.

The workflow resolves the tag once to an immutable commit; every build checks out that SHA. `scripts/release_artifacts.py` binds native archive hashes and tested Docker image digests to that commit and version, rejecting a missing platform or mixed sources before publication. Never build a release image from a newer `main` or attach it to older portable packages.

The workflow validates the pinned download catalog. Native builds download neither vocabularies nor raw metadata; isolated startup smokes exercise first-start `filtered` preparation and integrity checks. Core, UI, and browser checks gate packaging, and each package then passes its native startup, CPU inference and upgrade smoke. Docker images pass native Compose, CPU inference and offline persistent-volume replacement checks. Successful images are staged under run-specific tags; the publisher pulls their immutable digests and verifies configuration IDs and source labels instead of rebuilding them.

Only after all four portable builds and both Docker architectures pass does publication create the versioned multi-architecture image, Docker image downloads, version-pinned `compose.yaml`, ZIPs, `update.json`, `release.json`, checksums and reports. Anonymous manifest and pull checks verify public registry access. The stable `latest` image alias advances after the GitHub Release is published; prereleases leave it unchanged. Existing versioned images and published Releases are preserved.

The workflow token needs `contents: write` and `packages: write` for publication. GHCR initially creates a private package: on its first staged upload, set the repository-linked `pictide` package visibility to public before publication reaches its anonymous-access checks. Subsequent releases reuse that public package.

Ordinary branch pushes use local verification and do not trigger Actions. Docker validation additionally runs on relevant pull requests and manual dispatches; see [Docker builds](#build-and-verify-docker). Resource Releases persist the vocabulary; Actions caches only accelerate builds. For check preparation and coverage limits, see [release checks](testing.md#release-checks).

To rerun the complete release after a CI-only correction, dispatch `release.yml` from `main` with the existing `release_tag` and leave `build_run` and `macos_run` empty. Validation and all four builds check out that tag, then use the same native smoke and publication gates. This keeps the application source pinned while using the corrected workflow. Core HTTP fixtures receive an empty `web/dist/` before their checks; browser checks use the fully compiled isolated assets. An existing Release is never replaced.

For a Docker/publication-only failure after all four native builds passed, supply the original `build_run` and leave `macos_run` empty. Recovery reuses the verified native files and rebuilds Docker from the same resolved tag commit. The registry helper comes from the workflow revision, so CI-only upload corrections need no tag rewrite; it is outside the Docker build context and native payload. `release.json` records both the application `commit` and `tooling_commit`.

For Mac validation without publishing, manually run `.github/workflows/macos-validation.yml` with the Intel or Apple Silicon target. It uses the release builder and startup smoke, retaining ZIPs, checksums, revision metadata, and reports as an Actions artifact for seven days. Transfer the same ZIP to the target Mac, verify its SHA-256, and record actual launcher and startup behavior separately from CI results.

The optional `source_ref` selects an existing branch or tag; provenance records the checked-out commit. `previous_release` pins the older package and downloads it through authenticated GitHub CLI access, allowing upgrade checks for an existing tag without changing that tag. Normal release smoke jobs also use the workflow token for GitHub metadata queries to avoid shared-runner anonymous rate limits. Tokens remain confined to CI and are never bundled with the application.

If one macOS validation fails while the other three release builds succeed, validate the same tag with the manual Mac workflow for the failed architecture. Both macOS builders statically link source-built cryptography to avoid conflicting OpenSSL dylibs in the packaged app. The release workflow's manual recovery accepts `release_tag`, the original `build_run`, and the successful `macos_run`. It collects the three original assets and the matching replacement Mac asset inside GitHub, verifies matching application source commits and package hashes, and runs the same report, manifest, and checksum checks before publication. A workflow-only correction can run from `main` while `source_ref` keeps the application checkout on the original tag. It refuses to replace an existing platform asset or an existing Release. This recovery path is explicitly triggered; ordinary branch pushes still do not start workflows.

## Build and verify Docker

`Dockerfile` builds locked frontend assets in a Node.js stage and copies them into a Python 3.12 runtime. Runtime installs only `backend/requirements.txt`, runs as UID/GID 10001, and starts the existing CLI host. All mutable state stays under `/data`; vocabulary and MiniLM catalogs retain the same first-start download and verification path as source/portable startup. The allowlisted `.dockerignore` excludes personal data, developer environments, generated assets and local secrets from the build context.

```shell
docker compose -f compose.yaml -f compose.build.yaml up -d --build
python scripts/smoke_docker.py --image pictide:local
```

The smoke creates its own uniquely named Compose project and volume, checks non-root execution, published HTTP/frontend assets, actual CPU MiniLM scoring, and host-gateway API connectivity. It then replaces the container with networking disabled and verifies resource reuse plus database, settings and image persistence. Only those temporary containers and their volume are removed. Reports stay in `dev/verification/docker/`; no GPU or image/LLM provider requests are made.

`.github/workflows/docker-validation.yml` runs these checks natively on Linux amd64 and arm64 for relevant pull requests, or by manual dispatch with an optional `source_ref`. Those runs retain reports without publishing. The unified release reuses the same workflow with the resolved commit and registry staging enabled. Deployment and update commands are in the [Docker guide](../guides/setup/docker.md).

## Verify and commit

Choose a few meaningful checks for the affected behavior. Use `python scripts/check.py core|ui|corpus|browser`; `--list` shows the selected group's cases. Frontend changes also need type checking, a build, and focused interaction checks. See [testing](testing.md) for environments, browser setup, and the distinction between mocks and real generation.

Documentation-only changes need content, link, and diff checks. Report what was verified and any remaining limits. Current instructions belong in their topic documents; Chinese proposals and delivery records remain under `docs/zh-CN/dev/issues/`. Follow the [documentation policy](README.md#documentation-maintenance).

Before committing, run `git diff --check`, review the diff, stage explicit task paths, and review `git diff --cached`. Preserve unrelated changes. Keep runtime data, secrets, dependencies, and build artifacts out of commits.

### Commit conventions

- Write commit titles and bodies in English. Use `type: short summary` or `type(scope): short summary`, for example `fix(roam): defer prefetch after anchor changes`.
- Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `chore`, and `revert`.
- Keep each commit focused on one complete purpose. Add rationale and verification in the body when useful.
- Push task commits to `origin` before delivery. Use `git push -u origin <branch>` for a new task branch. Push integrated results to `origin/main`.
- On push failure, retain local commits and report the pending branch. Resolve divergence through merging; preserve existing history. Distinguish committed, pushed, and released states.

## Integrate and deploy

Confirm the main checkout has no changes needing protection, then integrate the verified branch:

```shell
git switch main
git merge --ff-only codex/example
git push origin main
```

If `main` advanced, merge it into the task branch, resolve conflicts, and repeat affected checks before integration.

Deploy frontend assets built from the matching source. For a running instance, back up its old `web/dist/` under `data/backups/`, copy new chunks and assets first, and replace the entry last. Retain old chunks for open tabs. Build in an isolated output directory while serving the application. Before a backend restart, inspect processes and tasks, announce the restart, and preserve drafts and executing work. Deployment preserves the selected runtime data directory.

Close verification instances and tabs after the task. Remove a worktree only after its work is integrated, its tracked changes are clean, and needed ignored data is preserved.

After integration and a successful push to `origin/main`, delete completed task branches locally and, if published, on `origin`. Verify that their commits are included in `main`; after cherry-picking, check patch equivalence as well. Finish any worktree cleanup before deleting its branch. Keep branches with ongoing work or independent unmerged changes. `main` remains the integration branch; version tags and Releases remain available independently of task branches.

```shell
git branch -d codex/example
git push origin --delete codex/example
```

## Version-control scope

Track source, neutral test fixtures, documentation, lockfiles, icons, and maintained workflow templates. Ignore `data/`, `dev/`, `releases/`, environments, dependencies, generated assets, caches, reports, logs, secrets, SQLite files, model weights, and raw Parquet data. Keep placeholder-only `.env.example` / `.env.template` files and shared VS Code configuration. Avoid extension-wide exclusions for JSON, images, or lockfiles. Check already tracked ignored files with `git ls-files -ci --exclude-standard` when changing ignore rules.

Restore downloaded resources with the preparation scripts. `.gitattributes` defines LF for source and CRLF for Windows launch scripts.
