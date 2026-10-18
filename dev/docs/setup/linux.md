# Linux 开发与构建

[开发文档](../README.md) · [Linux 安装与启动](../../../docs/guides/setup/linux.md)

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

先完成本页「从源码准备」，在本机项目根目录执行：

```bash
./data/runtime/venv/bin/python -m pip install -r backend/requirements-release.txt
./data/runtime/venv/bin/python scripts/build_portable.py --source-data-dir ./data --output-dir ./releases/linux-portable
```

指定的数据目录提供当前所选词库和 MiniLM；输出目录使用新目录。构建完成后使用其中的 Pictide 目录或 ZIP。详情见[发行记录](../issues/automatic-startup.md)。
