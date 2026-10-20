# Git 开发流程

包含 `README.md`、`backend/`、`web/` 与启动脚本的目录是仓库根目录，独立管理 Pictide 源码、测试、文档和工作流模板。`main` 保存验证后的集成结果；远程 `origin` 为 `git@github.com:Lykr/pictide.git`。

按步骤阅读：[开始任务](#开始任务) → [准备环境](#首次准备检出目录) → [验证提交](#验证与提交) → [集成发布](#集成与发布)。接口、架构和界面规则分别见[文档导航](../../dev/README.md)。

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

源码环境由开发者按本节准备。便携发行流程交付运行环境、前端成品和词库，MiniLM 按[启动前模型准备设计](issues/minilm-startup-download.md)在用户启动时下载并校验完成后再启动服务。旧版 Windows x64、Linux x64、macOS ARM64/Intel 目录包已通过原生 CI 构建及隔离启动冒烟，见[多平台验证记录](issues/github-releases.md#2026-10-19-多平台验证)。新 Windows EXE 与 macOS `.app` 分发的实现、验证及未验证项单独记录在[桌面分发](issues/desktop-distribution.md)。

需要 Git、Python 3.10+、Node.js 20.19+（或 22.12+）和 `web/package.json` 指定的 pnpm。Python 运行依赖放在 `backend/requirements.txt`，离线数据处理工具与依赖集中在 [`corpus/`](corpus.md)；前端依赖由 `web/package.json` 管理。依赖安装遵循锁文件，不复制或提交 `node_modules`。

按当前系统准备环境和构建前端：

- [Windows：从源码准备](setup/windows.md#从源码准备)
- [Linux：从源码准备](setup/linux.md#从源码准备)
- [macOS：从源码准备](setup/macos.md#从源码准备)

`web/dist/` 不提交，首次构建后才能使用页面和静态资源测试。运行数据与启动环境放在各自检出目录的 `data/`；开发依赖、缓存、临时文件与验证材料放在根目录 `dev/`。

浏览器验证按各系统页面的「端口与数据目录」步骤使用独立实例。每个并行实例使用不同端口，不共用主实例的 SQLite、词库或图片目录。默认使用模拟后端与中性样例；真实 ComfyUI 接入先只读检查，不为普通回归测试提交 GPU 任务。新启动脚本的 Git 执行位与换行约定见仓库属性；POSIX 启动脚本通过 `exec` 交接应用进程。

## 构建便携发行包

按本机系统一次准备 Python、Node.js、pnpm 与独立构建环境：[Windows](setup/windows.md#构建便携包) · [Linux](setup/linux.md#构建便携包) · [macOS](setup/macos.md#构建便携包)。推荐使用 Python 3.12，应用运行要求仍为 Python 3.10+。独立的 `dev/runtime/builder/` 环境安装 `backend/requirements-release.txt`；本地需要处理原始数据时另装 `corpus/requirements.txt`（Python 3.11+）。此后只需使用该环境执行 `scripts/build_portable.py`，自动运行 `pnpm install --frozen-lockfile`、类型检查和前端构建，再准备资源、完成 PyInstaller 目录式打包与 ZIP 归档。前端构建输出到 `dev/build/` 下的临时目录，保留运行中的 `web/dist/`。准备发行包无需先启动应用，也不读写开发运行目录 `data/`。

构建默认按 `corpus/profiles/compact.json` 准备词库，仅携带 `backend/recommand/model.json` 固定模型清单，保留 FastEmbed、ONNX Runtime、tokenizers 等推理依赖。构建不下载或打包 MiniLM。原始分片和下载清单长期保存在 `dev/datasets/danbooru-2026/`；统计中间结果与成品词库放在 `dev/cache/portable/`。有效词库缓存可离线准备发行资源；缺失时补充下载并处理。清理构建缓存保留原始数据，直接本地重新统计。指纹、校验和恢复规则见[独立发行资源与构建缓存](issues/portable-build-cache.md)。

通过 `--dataset-dir`、`--cache-dir` 和 `--profile` 可分别指定原始数据目录、缓存目录与处理配置。指定 `--prebuilt-library DIR` 时，`DIR` 必须包含匹配当前源数据版本、配置和处理代码的 `vocabulary.sqlite3` 与 `report.json`；校验失败即终止，不回退到原始数据处理。该路径无需安装 PyArrow、SciPy 等离线处理依赖。源码和便携启动共用 `prepare_startup`，在创建 HTTP 服务、打开页面前校验并补齐所选数据目录下的 MiniLM；失败终止启动，重启后续传。词库导出、清单与指纹规则见[预构建词库](corpus.md#预构建词库)。

便携构建默认只向 `releases/` 输出最终 `pictide-版本-平台-架构.zip`，无需手工创建输出目录，文件名不含日期。`--output-dir DIR` 可指定已有的最终包收集目录。本地重复构建在归档检查完成后原子替换同名 ZIP，保留其他版本，失败时保留已有最终包。`dev/build/` 下的临时前端、PyInstaller 工作区与展开目录在成功或失败后自动回收；构建报告保存到 `dev/verification/portable/版本-平台-架构/build-report.json`，失败时也保留。运行用户解压 ZIP 后启动 Pictide，词库初始化沿用[便携发行方案](issues/automatic-startup.md)，模型下载与离线准备见[安装与接入](../guides/getting-started.md#推荐依赖准备)。

#Windows 新构建包解压后以最外层 `Pictide.exe` 启动，依赖置于 `_internal/`，个人数据置于 `data/`。macOS 构建需要 Xcode Command Line Tools，编译系统 AppKit 原生入口并封装 `Pictide.app`；默认数据在用户 Application Support，构建采用 ad-hoc 签名，不接入 Developer ID 或公证。Linux 保持 ZIP 与 `start.sh` 终端入口。具体职责与验证状态见[桌面分发](issues/desktop-distribution.md)。

## GitHub Actions 发版

`.github/workflows/release.yml` 在推送 `v*` 标签时构建 Windows x64、Linux x64、macOS ARM64 和 macOS Intel 便携包。各平台使用原生 runner、Python 3.12 与 Node.js 22，标签去掉 `v` 后必须与 `backend/__init__.py` 和 `web/package.json` 中的版本一致。Linux/macOS 的实际兼容范围以对应平台的构建和启动冒烟结果为准。

每次发版按以下顺序操作：

1. 本地按[预构建词库步骤](corpus.md#预构建词库)生成资源，上传到 `corpus-<fingerprint>` 资源 Release。该标签避开应用的 `v*` 触发规则；已有资源保持不变。
2. 将生成的 `corpus/prebuilt.json` 资源锁与版本变更一起提交、推送。源数据、精简配置或处理代码发生变化时，先重新准备并上传匹配的词库。
3. 确认标签所指提交包含工作流与资源锁，再推送版本标签。例如源码版本均为 `0.4.0` 时：

```shell
git tag v0.4.0
git push origin v0.4.0
```

工作流从资源锁指定的 Release 下载词库并校验文件大小、SHA-256、报告与数据库；始终显式使用 `--prebuilt-library`，不在 runner 下载原始数据或进行统计。CI 准备构建环境后执行同一个 `scripts/build_portable.py` 入口，再独立自动执行隔离启动冒烟。所有平台构建并通过冒烟后，统一发布 ZIP、`SHA256SUMS` 和构建报告。带预发布后缀的版本发布为 prerelease；已发布版本和资源不覆盖。

工作流只在推送 `v*` 版本标签时触发；日常分支与 commit 推送使用本地验证。资源 Release 保存固定词库，应用 Release 保存用户下载的便携包；Actions cache 只用于加速，资源可用性由资源锁和 Release 保证。

需要在 Mac 实机验证当前源码时，可手动运行 `.github/workflows/macos-validation.yml` 并选择 Intel 或 Apple Silicon。它复用发行构建与隔离冒烟，只保存 ZIP、校验和、源码版本和报告到保留 7 天的 Actions artifact，不创建 Release；日常推送不会触发。将同一 ZIP 传到目标 Mac、核对 SHA-256 后运行，详见 [macOS 实机验证](issues/macos-native-validation.md)。

## 验证与提交

遵循 [项目协作约定](../../../AGENTS.md#验证与发布) 的概念验证原则，只选少数冒烟场景确认本次主要路径，不运行完整回归。后端改动可针对具体接口或用例验证；前端改动执行类型检查和构建，再检查受影响的页面交互与资源加载。复用已有测试时只运行相关的少数用例，不以整套测试数量作为交付目标。

统一入口为 `python scripts/check.py core|ui|corpus|browser`，按改动选择一个分组；`--list` 查看清单。环境要求、浏览器准备和标签发版门禁见[分组冒烟检查](testing.md)。发行流程在原生构建前运行核心业务、界面逻辑与浏览器检查，日常推送保持不触发 Actions。

纯文档与 Git 规则修改只需检查内容、链接、忽略规则和差异。报告实际通过、失败和未验证的范围；行为变化同步更新所属文档。需求设计、功能变更及交付记录放入 `docs/zh-CN/dev/issues/`；当前说明按指南、架构和参考主题维护；入口见[文档导航](../../dev/README.md#documentation-maintenance)。

提交前运行 `git diff --check`，核对 `git diff`，按明确路径暂存本任务文件，再核对 `git diff --cached` 后提交。不要把运行数据、密钥、依赖、构建结果或其他任务的文件带入提交。

### Commit 规范

- 提交标题与正文统一使用英文。格式为 `type: short summary`；需要标明模块时使用 `type(scope): short summary`，如 `fix(roam): defer prefetch after anchor changes`。
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
