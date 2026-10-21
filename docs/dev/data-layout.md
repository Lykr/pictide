# Data Layout and Responsibilities

[简体中文](../zh-CN/dev/data-layout.md)

[Developer Documentation](README.md). This page defines directories for runtime data, development materials, and release artifacts. See the [SQLite Storage Reference](reference/storage.md) for tables.

## Data Location

The data directory is selected in this order: startup argument → PICTIDE_DATA_DIR → legacy PICTIDE_WEB_DATA_DIR → remembered Windows location → default data. Source deployments default to `data/` inside the project. Windows and Linux packages default to `data/` beside the program; the macOS app defaults to `~/Library/Application Support/Pictide/`, outside its bundle. Replacing the macOS app preserves personal data; moving a Windows or Linux portable directory includes data stored inside it. External Windows data stays at its selected location.

The Windows interactive launcher confirms the data location before application initialization or downloads and remembers it in `pictide.local.json` beside the executable (in the project root for source startup). This launcher file contains only the directory pointer; all runtime content stays under the selected root. Paths inside the program directory are stored relatively; external paths are absolute. `--setup` reopens the choice. Changing the location leaves previous data in place without migration. Explicit arguments and environment variables retain precedence. Source bootstrapping prepares its Python environment before the application guide.

For custom directories, follow your platform's guide: [Windows](../guides/setup/windows.md#port-and-data-directory) · [Linux](../guides/setup/linux.md#port-and-data-directory) · [macOS](../guides/setup/macos.md#port-and-data-directory). Relative paths resolve from the working directory where the command is run.

## Runtime Data

The following paths are relative to the selected data directory:

| Path | Contents |
| --- | --- |
| `db/pictide.sqlite3` | Images, tasks, feedback, backends, settings, and recommendation learning; WAL/SHM files may exist at runtime |
| `db/candidate.sqlite3` | Personal prompt presets, fixed terms, and current library selection |
| `libraries/*.sqlite3` | Selectable read-only statistical libraries |
| `models/minilm/` | Recommendation dependency files (MiniLM), verified before startup: model.onnx, tokenizer.json, config.json, tokenizer_config.json, special_tokens_map.json; interrupted downloads use `.part` files |
| `models/generation/` | Models downloaded by Windows local generation preparation, grouped by ComfyUI type such as `diffusion_models/`, `text_encoders/`, and `vae/`; retained across cache cleanup |
| `images/` | Images and matching prompt JSON files containing only positive / negative |
| `workflows/` | API workflows; .backups holds versions from before updates or deletion |
| `history-cleanup.json` | Historical image retention in days; defaults to 1 day |
| `runtime/` | Source Python environment; the existing Linux package also keeps its bundled program here. New Windows and macOS packages keep program dependencies outside user data |
| `runtime/comfyui/` | ComfyUI and its portable Python environment prepared by Pictide on Windows |
| `runtime/local-generation.json` | Local preparation selection, installed versions, startup settings, and installation state |
| `cache/` | Regenerable runtime caches for Python, pip, and related tools |
| `cache/downloads/` | Local generation installation archives and resumable partial downloads; model weights belong under `models/generation/` |
| `tmp/` | Runtime temporary files |
| `logs/pictide.log` | Startup, application events, image tasks, and exceptions |
| `logs/comfyui.log` | Output from ComfyUI started by Pictide; absent when using an external service |
| `backups/` | Data backups |

See the [Prompt Guide](../guides/prompts.md#add-and-switch-libraries) for adding and selecting libraries. MiniLM is a recommendation runtime resource stored separately under models; routine cache cleanup preserves it. Source and portable startup download missing files and verify the fixed catalog before serving the application; valid files are reused offline. See [startup preparation](../guides/getting-started.md#recommendation-dependency-preparation). The program serves compiled frontend assets. In the source tree, web/node_modules points to dev/runtime/frontend/node_modules at the project root.

## Runtime Logging

Both logs use UTF-8 and rotate at 1 MiB, retaining three backups (`.1` through `.3`) per log. The default level is INFO; set `PICTIDE_LOG_LEVEL=DEBUG` before startup for debug messages. HTTP access logging stays disabled. Task events include identifiers, backend, elapsed time, and failures with tracebacks; full prompts, API credentials, and request bodies are not intentionally logged.

The tray and menu bar **View logs** action opens `logs/pictide.log`. Startup progress is also written there. Desktop launchers keep a temporary raw capture under `tmp/` only until startup succeeds; failed captures retain the latest three per platform. Historical logs using older names are preserved. Development validation output belongs in `dev/verification/`.

## Development Materials

Development materials and release artifacts are organized relative to the project root; data is dedicated to application runtime:

| Path | Contents |
| --- | --- |
| [`corpus/`](corpus.md) | Version-controlled offline download and configurable statistics processing tools, with dependency manifests |
| [`docs/dev/`](README.md) | Version-controlled English development documentation, architecture and API references |
| [`docs/zh-CN/`](../zh-CN/index.md) | Chinese translations, change proposals, design templates, and issue records |
| `dev/datasets/` | Long-lived raw Parquet and download manifests; manual offline processing outputs |
| `dev/runtime/frontend/`, `dev/runtime/importer/`, `dev/runtime/builder/` | Frontend dependencies, offline import environment, and independent portable-build environment |
| `dev/models/` | Historical build model resources; current builds do not use this directory, and existing files are retained |
| `dev/cache/portable/` | Rebuildable portable statistics, completed libraries, reports, and prebuilt exports under `exports/<fingerprint>/` |
| `dev/cache/`, `dev/tmp/` | Other development caches and temporary files |
| `dev/build/` | Temporary frontend output, PyInstaller workspace, and expanded portable package; automatically removed after build success or failure |
| `dev/verification/` | Isolated validation instances, screenshots, and reports; portable build reports remain at `portable/<version>-<platform>-<architecture>/build-report.json`, including on failure |
| `dev/maintenance/` | Local maintenance scripts and execution records |
| `dev/designs/`, `dev/previews/` | Design assets and historical screenshots |
| `dev/legacy/` | Retired library directories, model download caches, and historical temporary materials |
| `releases/` | Final portable ZIP files named `pictide-<version>-<platform>-<architecture>.zip` and completed vocabulary release resources under `vocabularies-<contentfingerprint12>/`; build workspaces and validation reports stay under `dev/` |

Portable builds prepare resources independently of runtime data. After the build environment is prepared once, `scripts/build_portable.py` installs locked frontend dependencies, checks types, and builds temporary frontend assets before preparing resources and packaging. The source runtime's `web/dist/` stays in place. The final package collection directory defaults to `releases/`; `--output-dir DIR` can select an existing directory. Builds atomically replace the same local ZIP only after archive checks succeed, preserving other versions and any previous final ZIP on failure. [Prebuilt release vocabularies](corpus.md#prebuilt-vocabulary) are published as fixed resource Release assets and referenced by the version-controlled `corpus/prebuilt.json`; SQLite files remain outside Git. GitHub Actions validates and packages those files instead of processing raw metadata. Vocabulary fingerprints, verification, and raw-data retention are described in the [corpus cache reference](corpus.md#cache-verification). MiniLM files are prepared at application startup under runtime data, using the fixed catalog `backend/recommand/model.json`; `corpus/resources.json` records only the raw dataset. Optional Windows local generation downloads use their own pinned runtime and model recipes. Neither ComfyUI nor generation weights are bundled in the portable ZIP.

Source and packaged deployments use the same personal data responsibilities and relative paths. The source startup environment is `data/runtime/venv`. Windows packages place `Pictide.exe` and `_internal/` beside `data/`; macOS packages place the native `Pictide` launcher, `PictideService` engine, frameworks, and bundled resources inside `Pictide.app`. Linux retains `data/runtime/pictide/`. Paths in historical reports reflect their location at the time; see dev/maintenance for the current mapping. Independently installed ComfyUI keeps its own directories. Pictide-managed ComfyUI, models, download state, and logs stay inside the selected data directory; extra model paths expose `models/generation/` to that process, and `logs/comfyui.log` holds its service log. The saved workflow and image API use the existing workflow and database storage.

## Data Lifecycle

For disposable caches, frontend backups and validation files, use the [project cleanup script](cleanup.md). It previews a reviewable list and preserves long-lived resources and personal data.

- Each backend save creates an immutable revision; existing tasks reference their submission-time snapshot. Workflow versions are backed up before editing.
- Liked images are retained across sections. Cleaning up unliked images reclaims images and prompt JSON files while retaining task history.
- Time-based cleanup and roam history count cleanup run at startup and operation entry points. See [Settings and Cleanup](../guides/settings.md#historical-image-cleanup).
- Feedback and pending learning records are persisted in one transaction; recommendation processes them in the background. Historical records are interpreted using generation-time snapshots.

See the [User Guide](../guides/backup.md#backup-and-recovery) for backup and recovery. To retain local development environments, raw data, or release artifacts, separately back up `dev/` and `releases/` at the project root.
