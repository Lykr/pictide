# Windows 开发与构建

[开发文档](../README.md) · [Windows 安装与启动](../../guides/setup/windows.md)

以下命令在项目根目录执行。

## 从源码准备

首次检出源码时，先准备[开发环境要求](../development.md#首次准备检出目录)中的 Node.js 和 pnpm，再构建前端：

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

启动时自动准备 Python 环境，无需在系统 Python 中安装应用依赖。


## 构建便携包

先完成本页「从源码准备」中的前端安装、类型检查和构建；打包无需执行启动命令。构建使用 Python 3.11+（推荐 3.12，PyArrow 26 要求 3.11+）；应用运行仍支持 Python 3.10+。在本机项目根目录创建独立构建环境：

```powershell
py -3.12 -m venv dev/runtime/builder
.\dev\runtime\builder\Scripts\python.exe -m pip install -r backend/requirements-release.txt
.\dev\runtime\builder\Scripts\python.exe scripts/build_portable.py
```

原始数据默认长期保存在 `dev/datasets/danbooru-2026/`，固定 MiniLM 长期保存在 `dev/models/minilm/<model-revision>/`，可重建的词库与统计缓存放在 `dev/cache/portable/`。首次缺少资源时自动补充下载并按 `corpus/profiles/compact.json` 处理词库、准备固定版本 MiniLM；有效词库和模型齐备时无需网络。清理构建缓存保留原始数据和模型，可直接本地重新统计。构建独立于应用运行目录 `data/`。

需要换磁盘、复用已有原始数据或调整规格时，可指定目录和配置：

```powershell
.\dev\runtime\builder\Scripts\python.exe scripts/build_portable.py --dataset-dir DATASET_PATH --cache-dir CACHE_PATH --models-dir MODELS_PATH --profile corpus/profiles/compact.json --output-dir releases/windows-portable
```

`DATASET_PATH` 使用含 `raw/` 与 `download.sqlite3` 的数据集根目录；`MODELS_PATH` 是长期模型根目录，默认 `dev/models/`。输出目录使用新目录；省略 `--output-dir` 时自动在 `releases/` 下创建带版本、平台和时间的新目录。构建完成后使用其中的 Pictide 目录或 ZIP。缓存校验与恢复规则见[发行资源准备](../issues/portable-build-cache.md)，各平台历史验证范围见[发行记录](../issues/automatic-startup.md)。
