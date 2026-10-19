# Git 开发流程

包含 `README.md`、`backend/`、`web/` 与启动脚本的目录是仓库根目录，独立管理 Pictide 源码、测试、文档和工作流模板。`main` 保存验证后的集成结果；远程 `origin` 为 `git@github.com:Lykr/pictide.git`。

按步骤阅读：[开始任务](#开始任务) → [准备环境](#首次准备检出目录) → [验证提交](#验证与提交) → [集成发布](#集成与发布)。接口、架构和界面规则分别见[文档导航](README.md)。

## 开始任务

先检查当前工作，不覆盖用户或其他任务的改动：

```shell
git status --short --branch
git diff
```

实现任务使用 `feat/<topic>`、`fix/<topic>` 或 `chore/<topic>` 分支。运行中的主目录用于集成和服务，开发与并行 agent 优先在独立 worktree 工作：

```shell
git worktree add ../pictide-example -b feat/example main
cd ../pictide-example
```

分支名和目录名按实际任务替换，开始前核对是否已存在。无需复制整个生产目录；Git 管理源码，忽略的 `data/` 和依赖不会自动复制。独立任务交给 subagent 时明确 worktree、分支、文件边界和交付要求，共享接口由主管协调。简单文档修改可直接在干净工作区完成。

## 首次准备检出目录

源码环境由开发者按本节准备。[便携发行包设计](issues/automatic-startup.md)将运行环境、前端成品、词库和推荐模型统一纳入构建发布流程，Windows 目录式产物已验证，Linux/macOS 原生验证待完成。

需要 Git、Python 3.10+、Node.js 20.19+（或 22.12+）和 `web/package.json` 指定的 pnpm。Python 运行依赖放在 `backend/requirements.txt`，离线数据处理工具与依赖集中在 [`corpus/`](corpus.md)；前端依赖由 `web/package.json` 管理。依赖安装遵循锁文件，不复制或提交 `node_modules`。

按当前系统准备环境和构建前端：

- [Windows：从源码准备](setup/windows.md#从源码准备)
- [Linux：从源码准备](setup/linux.md#从源码准备)
- [macOS：从源码准备](setup/macos.md#从源码准备)

`web/dist/` 不提交，首次构建后才能使用页面和静态资源测试。运行数据与启动环境放在各自检出目录的 `data/`；开发依赖、缓存、临时文件与验证材料放在根目录 `dev/`。

浏览器验证按各系统页面的「端口与数据目录」步骤使用独立实例。每个并行实例使用不同端口，不共用主实例的 SQLite、词库或图片目录。默认使用模拟后端与中性样例；真实 ComfyUI 接入先只读检查，不为普通回归测试提交 GPU 任务。新启动脚本的 Git 执行位与换行约定见仓库属性；POSIX 启动脚本通过 `exec` 交接应用进程。

## 构建便携发行包

完成当前检出的前端构建后，按本机系统阅读：[Windows](setup/windows.md#构建便携包) · [Linux](setup/linux.md#构建便携包) · [macOS](setup/macos.md#构建便携包)。构建工具为 `scripts/build_portable.py`，仅从指定数据目录导出所选统计词库与编码器所需模型，个人后端、图片、预设与偏好留在本地。

构建与验证材料归入根目录 `dev/`，发行产物归入根目录 `releases/`，启动环境保留在 `data/runtime/`。省略 --output-dir 时自动在 releases 下按版本、平台与时间创建新目录；也可指定新目录。产物包括 Pictide 目录、ZIP 和 build-report.json。默认词库由源数据目录的选择决定；正式发布优先选择精简词库。构建阶段安装 `backend/requirements-release.txt`，用户直接启动已构建产物。

## 验证与提交

遵循 [项目协作约定](../../AGENTS.md#验证与发布) 的概念验证原则，只选少数冒烟场景确认本次主要路径，不运行完整回归。后端改动可针对具体接口或用例验证；前端改动执行类型检查和构建，再检查受影响的页面交互与资源加载。复用已有测试时只运行相关的少数用例，不以整套测试数量作为交付目标。

纯文档与 Git 规则修改只需检查内容、链接、忽略规则和差异。报告实际通过、失败和未验证的范围；行为变化同步更新所属文档。需求设计、功能变更及交付记录放入 `docs/dev/issues/`；当前说明按指南、架构和参考主题维护；入口见[文档导航](README.md#文档维护)。

提交前运行 `git diff --check`，核对 `git diff`，按明确路径暂存本任务文件，再核对 `git diff --cached` 后提交。不要把运行数据、密钥、依赖、构建结果或其他任务的文件带入提交。

### Commit 规范

- 格式为 `type: 简短中文说明`；需要标明模块时使用 `type(scope): 简短中文说明`，如 `fix(roam): 修复切换锚点后的预取时机`。
- 类型使用 `feat`（功能）、`fix`（修复）、`docs`（文档）、`refactor`（重构）、`perf`（性能）、`test`（测试）、`chore`（工具与依赖）或 `revert`（回退）。
- 一次提交围绕一个完整目的，标题说明具体变化；复杂变更可在正文补充原因与验证结果。既有历史保留原样。
- 任务交付前将新提交推送到 `origin`。已集成的任务推送 `main`；尚未集成的任务推送对应任务分支，首次使用 `git push -u origin <分支名>` 建立跟踪。
- 推送失败时保留本地提交，报告原因与待推送分支；通过合并处理远程分歧，不强制推送。交付时区分已提交、已推送与已发布。

## 集成与发布

任务交付包含分支、提交、关键变更及验证结果。主管确认主工作区无待保护的改动后统一集成：

```shell
git switch main
git merge --ff-only feat/example
git push origin main
```

如果主分支已前进，在任务 worktree 合并最新 `main`，解决冲突并补做受影响验证，再回主目录快进合并。不要用 reset、强制覆盖或未经授权的历史改写处理分歧。

前端发布使用对应提交验证后的构建产物。运行中的实例先备份旧 `web/dist/` 到 `data/backups/`，先复制新 chunks 和其他资源，再替换入口，保留旧 chunks 供未刷新的标签页使用。不要在正在提供页面的目录直接执行会清空 `dist/` 的构建。后端变化需在核对进程和任务状态后提前说明重启，保留草稿与运行任务；发布不覆盖生产 `data/`。未运行的检出目录可直接执行常规构建。

任务完成后关闭自己的验证实例和标签页。确认 worktree 的工作已合并、没有未提交改动或需要保留的忽略文件，再执行 `git worktree remove <路径>`；保留必要数据后才清理，不能用强制移除跳过检查。分支是否删除按实际后续需要处理。

## 版本管理范围

跟踪源码、测试样例、文档、锁文件、图标素材及手工维护的工作流模板。`docs/dev/` 纳入版本管理；`.gitignore` 排除 `data/`、`dev/`、`releases/`、虚拟环境与依赖、构建产物、缓存与测试报告、日志与临时文件、环境密钥、SQLite 及辅助文件、模型权重和原始 Parquet 数据。保留 `.env.example` / `.env.template`（含分环境示例）及 VS Code 的共享 settings / extensions / tasks / launch 配置，示例中只填占位值；不要按图片、JSON 或锁文件扩展名整体忽略。新增规则不会自动停止跟踪已有文件，调整时用 `git ls-files -ci --exclude-standard` 核对。下载素材按现有脚本恢复，不把 Git 当作用户数据备份。换行由 `.gitattributes` 统一：源码使用 LF，Windows 启动脚本使用 CRLF。

本地初始化时保留现有文件并建立源码快照；日常提交与推送按上述流程执行，托管 CI 按需配置。
