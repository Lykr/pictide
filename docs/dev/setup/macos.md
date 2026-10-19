# macOS 开发与构建

[开发文档](../README.md) · [macOS 安装与启动](../../guides/setup/macos.md)

以下命令在项目根目录执行。

## 从源码准备

首次检出源码时，先准备[开发环境要求](../development.md#首次准备检出目录)中的 Node.js 和 pnpm，再构建前端：

```bash
project_dev="$PWD/dev"
mkdir -p "$project_dev/tmp"
export TMPDIR="$project_dev/tmp" TEMP="$project_dev/tmp" TMP="$project_dev/tmp"
(cd web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build)
chmod +x start.sh start.command
./start.command
```

启动时自动准备 Python 环境，无需在系统 Python 中安装应用依赖。


## 构建便携包

构建 `.app` 需要 Xcode Command Line Tools 提供的 Swift 编译器与 AppKit SDK；先用 `xcrun --find swiftc` 确认可用。GitHub macOS runner 已提供这些构建工具，发行包使用系统框架运行。

先安装 Xcode Command Line Tools（`xcode-select --install`），供构建时 `swiftc` 编译系统 AppKit 原生入口；运行包复用系统框架，无需安装 Swift 或第三方 GUI 环境。

一次准备[开发环境要求](../development.md#首次准备检出目录)中的 Python、Node.js 和 pnpm，并在本机项目根目录创建独立构建环境。构建使用 Python 3.11+（推荐 3.12，PyArrow 26 要求 3.11+）；应用运行仍支持 Python 3.10+：

```bash
python3.12 -m venv dev/runtime/builder
./dev/runtime/builder/bin/python -m pip install -r backend/requirements-release.txt
./dev/runtime/builder/bin/python -m pip install -r corpus/requirements.txt
```

此后每次构建只需执行：

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py
```

脚本自动按锁文件安装前端依赖、运行类型检查并将前端构建到 `dev/build/` 下的临时目录，然后准备资源、执行 PyInstaller 目录式打包并生成 ZIP。运行中的 `web/dist/` 保留原有内容。

原始数据默认长期保存在 `dev/datasets/danbooru-2026/`，可重建的词库与统计缓存放在 `dev/cache/portable/`。缺少资源时自动补充下载并按 `corpus/profiles/compact.json` 处理词库；有效词库缓存可离线准备发行资源。清理构建缓存保留原始数据，可直接本地重新统计。构建独立于应用运行目录 `data/`。MiniLM 文件不参与构建，用户启动时完成[推荐依赖准备](../../guides/getting-started.zh-CN.md#推荐依赖准备)后才进入应用；推理依赖仍随包交付。

已有[预构建词库](../corpus.zh-CN.md#预构建词库)时，可省略安装 `corpus/requirements.txt`，改用以下命令；`PREBUILT_DIR` 包含 `vocabulary.sqlite3` 与 `report.json`，校验失败即终止：

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py --prebuilt-library PREBUILT_DIR
```

GitHub 多平台自动构建、资源上传与版本标签步骤见 [GitHub Actions 发版](../development.md#github-actions-发版)。

需要换磁盘、复用已有原始数据或调整规格时，可指定目录和配置：

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py --dataset-dir DATASET_PATH --cache-dir CACHE_PATH --profile corpus/profiles/compact.json
```

`DATASET_PATH` 使用含 `raw/` 与 `download.sqlite3` 的数据集根目录。默认将最终 `pictide-版本-平台-架构.zip` 放入 `releases/`，无需手工创建目录，文件名不含日期。`--output-dir DIR` 可指定已有的最终包收集目录；本地重复构建在归档检查完成后原子替换同名 ZIP，保留其他版本，失败时保留已有最终包。临时构建与展开目录在成功或失败后自动回收，报告保存在 `dev/verification/portable/版本-平台-架构/build-report.json`，失败时也保留。ZIP 直接包含 `Pictide.app`，用户拖入「应用程序」后启动。`Contents/MacOS/Pictide` 是原生 AppKit 入口，`PictideService` 是目录式 Python 引擎；CLI 可执行 `/Applications/Pictide.app/Contents/MacOS/Pictide --cli`。构建采用 ad-hoc 签名，暂不接入 Developer ID 或 Apple 公证。默认个人数据位于 `~/Library/Application Support/Pictide/`，替换应用保留数据。缓存校验与恢复规则见[发行资源准备](../issues/portable-build-cache.md)，各平台历史验证范围见[发行记录](../issues/automatic-startup.md)。

旧版 macOS ARM64 和 Intel 目录包已通过原生 CI 构建和启动冒烟，见[多平台验证记录](../issues/github-releases.md#2026-10-19-多平台验证)。新 `.app` 的原生构建、菜单、首次打开和退出仍需 Mac 验证；v0.4.0 用户端 Python 加载错误尚未查明，不能据包装变化视为已修复。当前验证状态见[桌面分发](../issues/desktop-distribution.md)。
