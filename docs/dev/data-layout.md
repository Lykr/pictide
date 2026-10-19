# Data Layout and Responsibilities

[简体中文](data-layout.zh-CN.md)

[Developer Documentation](README.md). This page defines directories for runtime data, development materials, and release artifacts. See the [SQLite Storage Reference](reference/storage.md) for tables and [Separating Development and Release Directories (Chinese)](issues/development-release-directories.md) for the reorganization record.

## Data Location

The data directory is selected in this order: startup argument → PICTIDE_DATA_DIR → legacy PICTIDE_WEB_DATA_DIR → default data. Source deployments default to data inside the project; portable deployments default to data inside the release directory. Moving the entire portable directory preserves personal data alongside the program.

For custom directories, follow your platform's guide: [Windows](../guides/setup/windows.md#port-and-data-directory) · [Linux](../guides/setup/linux.md#port-and-data-directory) · [macOS](../guides/setup/macos.md#port-and-data-directory). Relative paths resolve from the working directory where the command is run.

## Runtime Data

The following paths are relative to the selected data directory:

| Path | Contents |
| --- | --- |
| `db/pictide.sqlite3` | Images, tasks, feedback, backends, settings, and recommendation learning; WAL/SHM files may exist at runtime |
| `db/candidate.sqlite3` | Personal prompt presets, fixed terms, and current library selection |
| `libraries/*.sqlite3` | Selectable read-only statistical libraries |
| `models/minilm/` | Offline recommendation model: model.onnx, tokenizer.json, config.json, tokenizer_config.json, special_tokens_map.json |
| `images/` | Images and matching prompt JSON files containing only positive / negative |
| `workflows/` | API workflows; .backups holds versions from before updates or deletion |
| `history-cleanup.json` | Historical image retention in days; defaults to 1 day |
| `runtime/` | Program and dependencies: venv for source deployments; pictide program and bundled resources for portable deployments |
| `cache/` | Regenerable runtime caches for Python, pip, and related tools |
| `tmp/` | Runtime temporary files |
| `logs/` | Runtime logs |
| `backups/` | Data backups |

See the [Prompt Guide](../guides/prompts.md#add-and-switch-libraries) for adding and selecting libraries. MiniLM is a recommendation runtime resource stored separately under models; routine cache cleanup preserves it. The program serves compiled frontend assets. In the source tree, web/node_modules points to dev/runtime/frontend/node_modules at the project root.

## Development Materials

Development materials and release artifacts are organized relative to the project root; data is dedicated to application runtime:

| Path | Contents |
| --- | --- |
| [`corpus/` (Chinese)](corpus.md) | Version-controlled offline download and statistics import tools, with dependency manifests |
| [`docs/dev/`](README.md) | Version-controlled development guides, architecture, APIs, design guidelines, and issue records |
| `dev/datasets/` | Raw Parquet, download verification, and intermediate offline statistics |
| `dev/runtime/frontend/`, `dev/runtime/importer/` | Frontend development dependencies and offline import environment |
| `dev/cache/`, `dev/tmp/`, `dev/build/` | Development caches, temporary files, and portable build workspace |
| `dev/verification/` | Isolated validation instances, screenshots, and reports |
| `dev/maintenance/` | Local maintenance scripts and execution records |
| `dev/designs/`, `dev/previews/` | Design assets and historical screenshots |
| `dev/legacy/` | Retired library directories, model download caches, and historical temporary materials |
| `releases/` | Portable release directories, ZIP files, and build reports |

Source and portable deployments use the same runtime data responsibilities and relative paths. The source startup environment is data/runtime/venv; the portable program and dependencies are under data/runtime/pictide. Paths in historical reports reflect their location at the time; see dev/maintenance for the current mapping. ComfyUI manages its own models, environment, and output.

## Data Lifecycle

- Each backend save creates an immutable revision; existing tasks reference their submission-time snapshot. Workflow versions are backed up before editing.
- Liked images are retained across sections. Cleaning up unliked images reclaims images and prompt JSON files while retaining task history.
- Time-based cleanup and roam history count cleanup run at startup and operation entry points. See [Settings and Cleanup](../guides/settings.md#historical-image-cleanup).
- Feedback and pending learning records are persisted in one transaction; recommendation processes them in the background. Historical records are interpreted using generation-time snapshots.

See the [User Guide](../guides/backup.md#backup-and-recovery) for backup and recovery. To retain local development environments, raw data, or release artifacts, separately back up `dev/` and `releases/` at the project root.
