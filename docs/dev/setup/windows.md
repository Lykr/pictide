# Windows development setup

[简体中文](../../zh-CN/dev/setup/windows.md)

[Development workflow](../development.md) · [Windows user guide](../../guides/setup/windows.md)

Run commands from the repository root. Install Git, Python, Node.js, and the pnpm version declared in `web/package.json`; see [requirements](../development.md#prepare-a-checkout).

## Prepare from source

Keep development temporary files in the checkout, install locked frontend dependencies, and build the page:

```powershell
$projectDev = Join-Path (Get-Location) 'dev'
New-Item -ItemType Directory -Path "$projectDev\tmp" -Force | Out-Null
$env:TEMP = "$projectDev\tmp"
$env:TMP = $env:TEMP
Push-Location web
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run build
Pop-Location
.\start.cmd
```

The source launcher prepares its runtime environment under `data/`. First startup prepares the recommendation dependency before opening the page. Desktop startup shows temporary progress, then runs through the system tray; startup errors remain visible. Tray actions open the page, view the application log, or exit. Startup and tray text follow the system language, using Simplified Chinese or English.

The interactive first-run flow confirms the data location, then offers an existing API, local ComfyUI preparation, or later configuration. A prepared model includes its complete default workflow, saved before browser bootstrap so Roam and Generate can use it immediately. NVIDIA local preparation has real hardware verification; AMD, Intel, and CPU paths have configuration and simulated coverage. See the [user guide](../../guides/setup/windows.md) for setup and model requirements.

## Ports and data directories

Use a separate port and data directory for verification:

```powershell
.\start.cmd -Cli -Lan -Port 8191 -DataDir dev/verification/windows/data
```

Source flags use PowerShell names such as `-Cli`, `-Lan`, `-Port`, and `-DataDir`. Portable executables use `--cli`, `--lan`, `--port`, and `--data-dir`:

```powershell
.\Pictide.exe --cli --lan --port 8191 --data-dir dev/verification/windows/data
```

CLI and no-browser startup are noninteractive by default; add `--setup` explicitly when using the portable executable to reopen preparation. Keep temporary instances separate from personal SQLite, vocabulary, and images.

## Build a portable package

Prepare a separate native builder once:

```powershell
py -3.12 -m venv dev/runtime/builder
.\dev\runtime\builder\Scripts\python.exe -m pip install -r backend/requirements-release.txt
```

Build with that interpreter:

```powershell
.\dev\runtime\builder\Scripts\python.exe scripts/build_portable.py
```

The builder handles locked frontend installation, type checking, temporary asset generation, packaging, and archive verification. Vocabulary and MiniLM files are downloaded on first application startup. See [portable builds](../development.md#build-portable-packages) for caching, output, and cleanup rules.

The final ZIP appears in `releases/`; reports stay under `dev/verification/portable/`. Extract it and launch the top-level `Pictide.exe`, keeping `_internal/` beside it. MiniLM downloads on first application startup, rather than during packaging. Run relevant [smoke checks](../testing.md) before delivery; simulated generation does not verify a GPU backend.
