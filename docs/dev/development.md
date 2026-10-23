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

Prepare a native builder environment using the [Windows](setup/windows.md#build-a-portable-package), [Linux](setup/linux.md#build-a-portable-package), or [macOS](setup/macos.md#build-a-portable-package) instructions. Python 3.12 is recommended. Install `backend/requirements-release.txt` into `dev/runtime/builder/`; add `corpus/requirements.txt` when processing raw metadata locally, which requires Python 3.11+.

Run `scripts/build_portable.py` with that environment. It installs locked frontend dependencies, checks types, builds temporary frontend assets, prepares resources, creates a PyInstaller directory bundle, and checks its ZIP archive. Temporary assets live under `dev/build/`; the running checkout's `web/dist/` and application `data/` are preserved. Starting the application before packaging is unnecessary.

The default vocabulary profile is `corpus/profiles/compact.json`. Raw shards and the download manifest stay in `dev/datasets/danbooru-2026/`; intermediate statistics and verified libraries live in `dev/cache/portable/`. A valid library cache supports offline resource preparation. Missing resources are downloaded and processed as needed. Clearing build caches preserves the raw dataset.

Use `--dataset-dir`, `--cache-dir`, and `--profile` to select other locations or settings. `--prebuilt-library DIR` consumes a verified `vocabulary.sqlite3` and `report.json` matching the dataset revision, profile, and processing code. Invalid resources stop the build; this mode does not fall back to raw processing and does not require PyArrow or SciPy. See [prebuilt vocabularies](corpus.md#prebuilt-vocabulary).

The build retains FastEmbed, ONNX Runtime, tokenizers, and `backend/recommendation/model.json`, without downloading or bundling MiniLM weights. Startup verifies the selected data directory's model files before exposing HTTP; failures stop startup, and a later attempt resumes retained partial downloads.

Only final `pictide-VERSION-PLATFORM-ARCH.zip` files go into `releases/`. `--output-dir DIR` selects an existing alternative directory. After archive checks succeed, a repeated local build atomically replaces the same ZIP; other versions and previous successful output survive a failed build. Temporary frontend, PyInstaller, and expanded-package directories are cleaned on success or failure. Reports remain in `dev/verification/portable/VERSION-PLATFORM-ARCH/build-report.json`.

Windows packages expose `Pictide.exe` beside `_internal/`, with `data/` as the default runtime location. macOS packages contain `Pictide.app`, a small native AppKit launcher, and default to the user's Application Support directory. macOS builds use ad-hoc signing without Developer ID signing or notarization. Linux uses `start.sh` in a ZIP. ComfyUI and image-generation weights are optional runtime downloads, separate from the portable archive.

## GitHub Actions releases

`.github/workflows/release.yml` runs on pushed `v*` tags. It builds Windows x64, Linux x64, macOS ARM64, and macOS Intel packages on native runners using Python 3.12 and Node.js 22. The tag without `v` must match the versions in `backend/__init__.py` and `web/package.json`.

1. Prepare and publish the [prebuilt vocabulary](corpus.md#prebuilt-vocabulary) as immutable assets of a `corpus-<fingerprint>` resource Release. This tag does not match the application release trigger.
2. Commit and push `corpus/prebuilt.json` with the version changes. Regenerate the resource when the dataset revision, profile, or processor changes.
3. Confirm the tagged commit includes the workflow, lock, and matching versions; create and push the version tag. For example, when both source versions are `0.5.0`:

```shell
git tag v0.5.0
git push origin v0.5.0
```

Use a new version for each release; existing published versions and assets are preserved.

The workflow checks locked resource sizes, SHA-256 hashes, provenance, report, and database. Runners use `--prebuilt-library` rather than downloading or processing raw metadata. Core, UI, and browser checks gate native packaging; every native package then passes an isolated startup smoke check. Once all platforms succeed, the workflow publishes ZIPs, `SHA256SUMS`, and reports together. Versions with prerelease suffixes become prereleases.

Ordinary branch pushes use local verification and do not trigger Actions. Resource Releases persist the vocabulary; Actions caches only accelerate builds. For check preparation and coverage limits, see [release checks](testing.md#release-checks).

For Mac validation without publishing, manually run `.github/workflows/macos-validation.yml` with the Intel or Apple Silicon target. It uses the release builder and startup smoke, retaining ZIPs, checksums, revision metadata, and reports as an Actions artifact for seven days. Transfer the same ZIP to the target Mac, verify its SHA-256, and record actual launcher and startup behavior separately from CI results.

The optional `source_ref` selects an existing branch or tag; provenance records the checked-out commit. `previous_release` pins the older package and downloads it through authenticated GitHub CLI access, allowing upgrade checks for an existing tag without changing that tag. Normal release smoke jobs also use the workflow token for GitHub metadata queries to avoid shared-runner anonymous rate limits. Tokens remain confined to CI and are never bundled with the application.

If Apple Silicon validation fails for an external download reason while the other three release builds succeed, validate the same tag with the manual Mac workflow. The release workflow's manual recovery accepts `release_tag`, the original `build_run`, and the successful `macos_run`. It collects the three original assets and the replacement Apple Silicon asset inside GitHub, verifies matching source commits and package hashes, and runs the same report, manifest, and checksum checks before publication. It refuses to replace an existing platform asset or an existing Release. This recovery path is explicitly triggered; ordinary branch pushes still do not start workflows.

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
