# Linux development setup

[简体中文](../../zh-CN/dev/setup/linux.md)

[Development workflow](../development.md) · [Linux user guide](../../guides/setup/linux.md)

Run commands from the repository root. Prepare Git, Python with venv support, Node.js, and the declared pnpm version; see [requirements](../development.md#prepare-a-checkout).

## Prepare from source

```bash
project_dev="$PWD/dev"
mkdir -p "$project_dev/tmp"
export TMPDIR="$project_dev/tmp" TEMP="$project_dev/tmp" TMP="$project_dev/tmp"
(cd web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build)
bash start.sh
```

The launcher prepares an isolated Python environment under `data/` and downloads the recommendation dependency before starting HTTP. It does not install application packages into system Python. Linux retains terminal operation; Ctrl+C stops the application.

## Ports and data directories

```bash
bash start.sh --lan --port 8191 --data-dir dev/verification/linux/data
```

Use a separate port and data directory for each verification instance. Avoid sharing personal databases, vocabulary files, or images with test instances. For direct Host invocation after preparing the source environment, see `python -m backend.host --help`.

## Build a portable package

Prepare a native builder once:

```bash
python3.12 -m venv dev/runtime/builder
./dev/runtime/builder/bin/python -m pip install -r backend/requirements-release.txt
```

Install offline dependencies if processing raw metadata locally:

```bash
./dev/runtime/builder/bin/python -m pip install -r corpus/requirements.txt
```

Then build:

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py
```

Or consume a verified [prebuilt vocabulary](../corpus.md#prebuilt-vocabulary) without the offline dependencies:

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py --prebuilt-library dev/resources/filtered
```

The builder installs locked frontend dependencies, checks types, builds isolated assets, prepares vocabulary resources, and verifies the ZIP. See [portable builds](../development.md#build-portable-packages) for `--dataset-dir`, `--cache-dir`, `--profile`, final output, reports, and cleanup.

Extract the final ZIP from `releases/` and run `./start.sh`. MiniLM is prepared at application startup. The native Linux x64 CI smoke checks isolated startup, vocabulary initialization, model preparation, and HTTP readiness; it does not establish real GPU generation compatibility. Use the relevant [smoke group](../testing.md) for source changes.
