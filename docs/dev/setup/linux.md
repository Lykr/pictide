# Linux 开发与构建

[开发文档](../README.md) · [Linux 安装与启动](../../guides/setup/linux.md)

以下命令在项目根目录执行。

## 从源码准备

首次检出源码时，先准备[开发环境要求](../development.md#首次准备检出目录)中的 Node.js 和 pnpm，再构建前端：

```bash
project_dev="$PWD/dev"
mkdir -p "$project_dev/tmp"
export TMPDIR="$project_dev/tmp" TEMP="$project_dev/tmp" TMP="$project_dev/tmp"
(cd web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build)
bash start.sh
```

启动时自动准备 Python 环境，无需在系统 Python 中安装应用依赖。


## 构建便携包

先完成本页「从源码准备」中的前端安装、类型检查和构建；打包无需执行启动命令。构建使用 Python 3.11+（推荐 3.12，PyArrow 26 要求 3.11+）；应用运行仍支持 Python 3.10+。在本机项目根目录创建独立构建环境：

```bash
python3.12 -m venv dev/runtime/builder
./dev/runtime/builder/bin/python -m pip install -r backend/requirements-release.txt
./dev/runtime/builder/bin/python -m pip install -r corpus/requirements.txt
./dev/runtime/builder/bin/python scripts/build_portable.py
```

原始数据默认长期保存在 `dev/datasets/danbooru-2026/`，可重建的词库与统计缓存放在 `dev/cache/portable/`。缺少资源时自动补充下载并按 `corpus/profiles/compact.json` 处理词库；有效词库缓存可离线准备发行资源。清理构建缓存保留原始数据，可直接本地重新统计。构建独立于应用运行目录 `data/`。MiniLM 文件不参与构建，用户启动时完成[模型准备](../../guides/getting-started.zh-CN.md#推荐模型启动准备)后才进入应用；推理依赖仍随包交付。

已有[预构建词库](../corpus.zh-CN.md#预构建词库)时，可省略安装 `corpus/requirements.txt`，改用以下命令；`PREBUILT_DIR` 包含 `vocabulary.sqlite3` 与 `report.json`，校验失败即终止：

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py --prebuilt-library PREBUILT_DIR
```

GitHub 多平台自动构建、资源上传与版本标签步骤见 [GitHub Actions 发版](../development.md#github-actions-发版)。

需要换磁盘、复用已有原始数据或调整规格时，可指定目录和配置：

```bash
./dev/runtime/builder/bin/python scripts/build_portable.py --dataset-dir DATASET_PATH --cache-dir CACHE_PATH --profile corpus/profiles/compact.json --output-dir releases/linux-portable
```

`DATASET_PATH` 使用含 `raw/` 与 `download.sqlite3` 的数据集根目录。输出目录使用新目录；省略 `--output-dir` 时自动在 `releases/` 下创建带版本、平台和时间的新目录。构建完成后使用其中的 Pictide 目录或 ZIP。缓存校验与恢复规则见[发行资源准备](../issues/portable-build-cache.md)，各平台历史验证范围见[发行记录](../issues/automatic-startup.md)。

Linux/macOS 原生 CI 构建与启动验证待实际运行。
