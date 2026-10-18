# Git 开发流程

仓库根目录为 `E:\Code\pictide`，独立管理 Pictide 源码、测试、文档和工作流模板。`main` 保存验证后的集成结果；当前仅有本地仓库，未配置远程服务。

按步骤阅读：[开始任务](#开始任务) → [准备环境](#首次准备检出目录) → [验证提交](#验证与提交) → [集成发布](#集成与发布)。接口、架构和界面规则分别见[文档导航](README.md)。

## 开始任务

先检查当前工作，不覆盖用户或其他任务的改动：

```powershell
git status --short --branch
git diff
```

实现任务使用 `feat/<topic>`、`fix/<topic>` 或 `chore/<topic>` 分支。运行中的主目录用于集成和服务，开发与并行 agent 优先在独立 worktree 工作：

```powershell
git worktree add ..\pictide-example -b feat/example main
Set-Location ..\pictide-example
```

分支名和目录名按实际任务替换，开始前核对是否已存在。无需复制整个生产目录；Git 管理源码，忽略的 `data/` 和依赖不会自动复制。独立任务交给 subagent 时明确 worktree、分支、文件边界和交付要求，共享接口由主管协调。简单文档修改可直接在干净工作区完成。

## 首次准备检出目录

需要 Git、Python 3.10+、Node.js 20.19+（或 22.12+）和 `web/package.json` 指定的 pnpm。Python 运行依赖放在 `backend/requirements.txt`，离线导入依赖放在 `backend/requirements-import.txt`；前端依赖由 `web/package.json` 管理。依赖安装遵循锁文件，不复制或提交 `node_modules`。

在仓库根目录执行以下 PowerShell 命令；运行环境、包缓存和临时文件都放入该检出目录的 `data/`：

```powershell
$projectData = Join-Path (Get-Location) 'data'
New-Item -ItemType Directory -Path "$projectData\tmp", "$projectData\cache\pip" -Force | Out-Null
$env:TEMP = "$projectData\tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = "$projectData\cache\pip"
$env:PYTHONPYCACHEPREFIX = "$projectData\cache\python"
python -m venv "$projectData\runtime\venv"
& "$projectData\runtime\venv\Scripts\python.exe" -m pip install -r backend/requirements.txt
Push-Location web
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm run build
Pop-Location
```

Linux / macOS 在仓库根目录执行对应命令（系统需先提供 Python 3.10+、Node.js 和指定版本的 pnpm）：

```bash
project_data="$PWD/data"
mkdir -p "$project_data/tmp" "$project_data/cache/pip" "$project_data/cache/python"
export TMPDIR="$project_data/tmp" TEMP="$project_data/tmp" TMP="$project_data/tmp"
export PIP_CACHE_DIR="$project_data/cache/pip" PYTHONPYCACHEPREFIX="$project_data/cache/python"
python3 -m venv "$project_data/runtime/venv"
"$project_data/runtime/venv/bin/python" -m pip install -r backend/requirements.txt
(cd web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm run build)
bash start.sh
```

`web/dist/` 不提交，首次构建后才能使用页面和静态资源测试。现有主目录的构建与运行数据保持原样。使用自定义数据目录时，也不要将它放入其他源码路径或加入 Git。

需要浏览器验证时，在 worktree 根目录启动独立实例：

```powershell
& .\start.ps1 -Port 8191 -DataDir .\data
```

Linux / macOS 对应 `bash start.sh --port 8191 --data-dir ./data`；macOS 双击入口为 `start.command`，两种脚本均使用 `exec` 交接 Python 进程，Ctrl+C / SIGTERM 可直接到达应用。Shell 语法兼容 macOS 系统 Bash 3.2，Git 记录脚本执行位与 LF 换行。

每个并行实例使用不同端口；不要共用主实例的 SQLite、词库或图片目录。默认使用模拟后端与中性样例；真实 ComfyUI 接入先只读检查，不为普通回归测试提交 GPU 任务。

## 验证与提交

遵循 [项目协作约定](../AGENTS.md#验证与发布) 的概念验证原则，只选少数冒烟场景确认本次主要路径，不运行完整回归。后端改动可针对具体接口或用例验证；前端改动执行类型检查和构建，再检查受影响的页面交互与资源加载。复用已有测试时只运行相关的少数用例，不以整套测试数量作为交付目标。

纯文档与 Git 规则修改只需检查内容、链接、忽略规则和差异。报告实际通过、失败和未验证的范围；行为变化同步更新所属文档。需求设计、功能变更及交付记录放入 `docs/issues/`；当前说明按指南、架构和参考主题维护；入口见[文档导航](README.md#文档维护)。

提交前运行 `git diff --check`，核对 `git diff`，按明确路径暂存本任务文件，再核对 `git diff --cached` 后提交。不要把运行数据、密钥、依赖、构建结果或其他任务的文件带入提交。提交信息简短说明具体变化，不能把“已提交”当作“已发布”。

## 集成与发布

任务交付包含分支、提交、关键变更及验证结果。主管确认主工作区无待保护的改动后统一集成：

```powershell
git switch main
git merge --ff-only feat/example
```

如果主分支已前进，在任务 worktree 合并最新 `main`，解决冲突并补做受影响验证，再回主目录快进合并。不要用 reset、强制覆盖或未经授权的历史改写处理分歧。

前端发布使用对应提交验证后的构建产物。运行中的实例先备份旧 `web/dist/` 到 `data/backups/`，先复制新 chunks 和其他资源，再替换入口，保留旧 chunks 供未刷新的标签页使用。不要在正在提供页面的目录直接执行会清空 `dist/` 的构建。后端变化需在核对进程和任务状态后提前说明重启，保留草稿与运行任务；发布不覆盖生产 `data/`。未运行的检出目录可直接执行常规构建。

任务完成后关闭自己的验证实例和标签页。确认 worktree 的工作已合并、没有未提交改动或需要保留的忽略文件，再执行 `git worktree remove <路径>`；保留必要数据后才清理，不能用强制移除跳过检查。分支是否删除按实际后续需要处理。

## 版本管理范围

跟踪源码、测试样例、文档、锁文件、图标素材及手工维护的工作流模板。`.gitignore` 排除 `data/`、虚拟环境与依赖、构建产物、缓存与测试报告、日志与临时文件、环境密钥、SQLite 及辅助文件、模型权重和原始 Parquet 数据。保留 `.env.example` / `.env.template`（含分环境示例）及 VS Code 的共享 settings / extensions / tasks / launch 配置，示例中只填占位值；不要按图片、JSON 或锁文件扩展名整体忽略。新增规则不会自动停止跟踪已有文件，调整时用 `git ls-files -ci --exclude-standard` 核对。下载素材按现有脚本恢复，不把 Git 当作用户数据备份。换行由 `.gitattributes` 统一：源码使用 LF，Windows 启动脚本使用 CRLF。

初始化时保留现有本地文件，并创建 `main` 上的首个源码快照；远程仓库、推送与托管 CI 按需另行配置。
