# 开发流程

[English](../../dev/development.md)

[开发文档](README.md) · [针对性检查](testing.md)

仓库根目录包含 `README.md`、`backend/`、`web/` 与启动脚本。`main` 保存已验证的集成结果，`origin` 为 `git@github.com:Lykr/pictide.git`。

按[开始任务](#开始任务) → [准备环境](#首次准备检出目录) → [验证](#验证与提交) → [集成](#集成与部署)推进。

## 开始任务

修改前检查现有工作：

```shell
git status --short --branch
git diff
```

使用独立任务分支。Codex 使用 `codex/<topic>`，其他贡献者可使用 `feat/`、`fix/` 或 `chore/`。并行任务或涉及运行实例的改动使用独立 worktree、数据目录与端口：

```shell
git worktree add ../pictide-example -b codex/example main
cd ../pictide-example
```

先确认分支和目录是否存在。Git 保存源码，忽略的数据与依赖分别准备。简单文档修改可直接使用干净检出。委派独立工作时，先明确文件归属、共享接口和交付要求。

## 设计确认与数据保护

改动架构、跨模块调用或数据流、公开模块接口前，说明这三方面的变化并取得用户确认。使用中文[设计模板](design-template.md)，重点解释改动。复用已批准边界不重复确认，UI 细节和内部实现自主推进。

保留无关修改与已有历史，未经授权不 reset、stash 或改写历史。只委派值得独立处理的任务，并明确文件归属及接口协作。

直接修改既有用户数据前先备份。历史数据删除应提供可审核清单并取得用户确认。保留图片、任务、喜欢和偏好记录，验证使用临时数据，遵循[数据目录](data-layout.md)与[备份步骤](../guides/backup.md)。

## 首次准备检出目录

源码开发需要 Git、Python 3.10+、Node.js 20.19+ 或 22.12+，以及 `web/package.json` 声明的 pnpm 版本。运行依赖在 `backend/requirements.txt`，离线处理依赖在 `corpus/requirements.txt`；前端按锁文件安装。

按系统准备环境：

- [Windows](setup/windows.md#从源码准备)
- [Linux](setup/linux.md#从源码准备)
- [macOS](setup/macos.md#从源码准备)

使用页面或静态资源检查前，先构建被 Git 忽略的 `web/dist/`。每个检出在自己的 `data/` 保存运行数据，开发依赖、数据集、缓存和验证结果放在 `dev/`，见[数据目录](data-layout.md)。

验证使用独立端口和临时数据，优先中性夹具及模拟生成服务。真实 ComfyUI 先做只读连接检查，再按明确范围执行 GPU 测试。模拟结果确认编排行为，不代表画面质量或 GPU 兼容性。

MiniLM 在 HTTP 服务启动前准备。便携包包含推理运行环境与固定模型清单，模型文件在首次启动下载，见[推荐依赖准备](../guides/getting-started.md#推荐依赖准备)。

## 构建便携包

按 [Windows](setup/windows.md#构建便携包)、[Linux](setup/linux.md#构建便携包) 或 [macOS](setup/macos.md#构建便携包) 准备原生构建环境，推荐 Python 3.12。在 `dev/runtime/builder/` 安装 `backend/requirements-release.txt`；本地处理原始元数据时另装 `corpus/requirements.txt`，此路径要求 Python 3.11+。

用该环境运行 `scripts/build_portable.py`，按锁文件安装前端依赖、检查类型、构建临时前端、准备资源、生成 PyInstaller 目录包并检查 ZIP。临时产物在 `dev/build/`，保留正在运行检出的 `web/dist/` 和应用 `data/`；无需先启动应用。

默认词库配置为 `corpus/profiles/compact.json`，原始分片和下载清单长期放在 `dev/datasets/danbooru-2026/`，中间统计与已验证词库在 `dev/cache/portable/`。有效缓存支持离线准备；缺失资源按需下载和处理。清理构建缓存保留原始数据。

通过 `--dataset-dir`、`--cache-dir` 和 `--profile` 选择目录及处理配置。`--prebuilt-library DIR` 使用与数据集修订、配置和处理代码匹配且已验证的 `vocabulary.sqlite3`、`report.json`。资源无效即停止，不回退原始统计，也不要求 PyArrow 或 SciPy，见[预构建词库](corpus.md#预构建词库)。

构建保留 FastEmbed、ONNX Runtime、tokenizers 和 `backend/recommendation/model.json`，不下载或打包 MiniLM 权重。启动在开放 HTTP 前校验所选数据目录的模型文件；失败停止启动，下次恢复保留的分段下载。

`releases/` 只放最终 `pictide-VERSION-PLATFORM-ARCH.zip`，`--output-dir DIR` 可选择其他已有目录。归档检查通过后，重复本地构建会原子替换同名 ZIP；其他版本及上次成功输出不受失败构建影响。临时前端、PyInstaller 和展开包在成功/失败时清理，报告保留在 `dev/verification/portable/VERSION-PLATFORM-ARCH/build-report.json`。

Windows 包在 `_internal/` 旁提供 `Pictide.exe`，默认数据位置为旁边的 `data/`。macOS 包含原生 AppKit 启动器 `Pictide.app`，默认使用用户 Application Support 目录，采用 ad-hoc 签名，不含 Developer ID 签名或公证。Linux ZIP 使用 `start.sh`。ComfyUI 与生图权重为可选运行时下载，独立于便携包。

## GitHub Actions 发版

`.github/workflows/release.yml` 在推送 `v*` 标签时运行，使用原生 runner 构建 Windows x64、Linux x64、macOS ARM64、macOS Intel 便携包，以及 Linux amd64/arm64 Docker 镜像。标签去掉 `v` 后必须与 `backend/__init__.py`、`web/package.json` 的版本一致。

1. 词库变化时，将[两版词库](../../dev/corpus.md#export-both-vocabulary-editions)发布为不可变的资源 Release。
2. 按发布的版本清单更新 `backend/setup/vocabularies.json`，保留 Release 标签、文件大小和 SHA-256，与应用版本变更一起提交。
3. 确认标签提交包含工作流、资源锁及一致版本，再创建并推送标签。例如两个源码版本均为 `0.5.0`：

```shell
git tag v0.5.0
git push origin v0.5.0
```

每次发行使用新版本，保留已有发布版本与资源。

工作流将标签解析为唯一 commit，所有构建均检出该 SHA。`scripts/release_artifacts.py` 将便携包哈希、经过测试的镜像摘要与源码版本绑定；缺少平台或来源不一致时停止发布。不能从更新后的 `main` 单独构建镜像，再与旧安装包放在同一版本下。

core、ui 和 browser 检查通过后开始打包；每个便携包再验证启动、真实 CPU 推理和旧版升级。词库及 MiniLM 不打进安装包，由隔离启动冒烟验证首次下载。Docker 在两种原生架构上验证 Compose 启动、CPU 推理和保留数据卷的离线重建，通过后暂存镜像。发布时按不可变摘要拉取暂存镜像，核对镜像 ID 和源码标签，不重新构建。

四份便携包和两种镜像全部通过后，统一发布多架构镜像、可下载镜像文件、固定版本的 `compose.yaml`、ZIP、`update.json`、`release.json`、校验值和报告，并验证两种架构均可匿名拉取。稳定镜像的 `latest` 别名在 GitHub Release 发布后更新；预发布不修改 `latest`。保留已有版本镜像和 Release。

发布任务需要 `contents: write` 和 `packages: write`。GHCR 首次创建的包默认为私有：第一次暂存上传后，在关联仓库的 `pictide` 包设置中将可见性改为公开，再进入匿名访问检查。后续发版复用公开的包。

日常分支推送使用本地验证，不触发 Actions。资源 Release 长期保存词库，Actions cache 仅加速构建；验证准备与覆盖限制见[发版检查](testing.md#发版检查)。

只修正 CI 后需要完整重跑时，从 `main` 手动触发 `release.yml`，传入已有 `release_tag`，将 `build_run`、`macos_run` 留空。验证、四平台便携包和两种 Docker 镜像均检出该标签解析出的 commit，沿用相同验证和发布门禁。HTTP 核心夹具检查前先准备空 `web/dist/`，浏览器检查使用完整编译的隔离产物；不覆盖已有 Release。

如果四平台便携包已通过，只有 Docker 或发布阶段失败，可传入原 `build_run`，将 `macos_run` 留空。恢复任务复用已验证的安装包，从同一个标签 commit 重建 Docker。镜像上传工具使用工作流版本，且不进入 Docker 构建上下文或便携包，因此修正 CI 无需改写标签。`release.json` 分别记录应用的 `commit` 和工具的 `tooling_commit`。

不发布的 Mac 验证使用 `.github/workflows/macos-validation.yml`，选择 Intel 或 Apple Silicon，复用发行构建与启动冒烟，保留 ZIP、校验值、修订元数据和报告为七天期 Actions artifact。传到目标 Mac 核对 SHA-256 后，单独记录实际启动器与启动行为，不能用 CI 结果替代。

可选 `source_ref` 指定已有分支或标签，来源记录保存实际检出提交；`previous_release` 固定旧版本，经认证的 GitHub CLI 下载，允许在不改标签的情况下验证升级。普通发行冒烟也使用工作流 token 查询 GitHub 元数据，避免共享 runner 匿名限额。令牌仅存在 CI，不随应用分发。

若一个 macOS 构建失败、其他三个发行构建成功，可用手动 Mac 工作流验证同标签的失败架构。两种 macOS 构建均静态链接从源码构建的 cryptography，避免包内 OpenSSL dylib 冲突。发行恢复接收 `release_tag`、原 `build_run` 与成功的 `macos_run`，在 GitHub 内收集三份原产物和匹配的 Mac 替代产物，核对应用源码提交及包哈希，沿用报告、清单和校验步骤后发布。工作流修正可运行在 `main`，`source_ref` 将应用固定在原标签；拒绝替换已有平台资源或 Release。此恢复必须明确触发，普通分支推送仍不启动工作流。

## 验证与提交

按影响范围选择少量有意义的检查，使用 `python scripts/check.py core|ui|corpus|browser`，`--list` 查看分组用例。前端变更还需类型检查、构建和针对性交互验证；环境、浏览器及模拟/真实生成的区别见[验证说明](testing.md)。

纯文档变更检查内容、链接与差异，准确报告已验证范围及限制。当前规则维护在所属主题；中文提案与交付记录留在 `docs/zh-CN/dev/issues/`，遵循[文档维护策略](README.md#文档维护)。

提交前运行 `git diff --check`、审查差异、按明确任务路径暂存，再审查 `git diff --cached`。保留无关修改，不提交运行数据、密钥、依赖或构建产物。

### Commit 规范

- 标题与正文使用英文，格式为 `type: short summary` 或 `type(scope): short summary`，如 `fix(roam): defer prefetch after anchor changes`。
- 类型为 `feat`、`fix`、`docs`、`refactor`、`perf`、`test`、`chore` 或 `revert`。
- 每次提交围绕一个完整目的，按需在正文解释原因和验证。
- 交付前推送任务提交到 `origin`，新分支用 `git push -u origin <分支名>`，集成结果推送 `origin/main`。
- 推送失败保留本地提交并报告待推送分支，通过合并解决分歧，保留历史；区分已提交、已推送与已发布。

## 集成与部署

确认主检出没有需要保护的修改，再集成已验证分支：

```shell
git switch main
git merge --ff-only codex/example
git push origin main
```

`main` 已前进时，先在任务分支合并它，解决冲突并重新验证受影响部分，再集成。

发布与源码对应的前端产物。运行中的实例先将旧 `web/dist/` 备份到 `data/backups/`，复制新 chunks 与资源，最后替换入口；保留旧 chunks 供未刷新的页面使用。服务运行期间在隔离输出目录构建。重启后端前检查进程与任务，提前说明，保留草稿和执行中工作；部署保留所选运行数据目录。

结束后关闭自己的验证实例和标签页。仅在工作已集成、受跟踪文件干净且必要忽略数据已保留时移除 worktree。

集成并成功推送 `origin/main` 后，删除已完成的本地任务分支及已发布的远端任务分支。先确认提交已包含在 `main`；cherry-pick 后还需检查补丁等价。先完成 worktree 清理再删分支，保留仍有工作或独立未合并变更的分支。`main` 保持集成分支，版本标签与 Release 独立于任务分支继续存在。

```shell
git branch -d codex/example
git push origin --delete codex/example
```

## 版本管理范围

跟踪源码、中性测试样例、文档、锁文件、图标和维护的工作流模板。忽略 `data/`、`dev/`、`releases/`、环境、依赖、构建产物、缓存、报告、日志、密钥、SQLite、模型权重与原始 Parquet。保留只含占位值的 `.env.example` / `.env.template` 及共享 VS Code 配置，不按 JSON、图片等扩展名整体忽略。修改忽略规则时用 `git ls-files -ci --exclude-standard` 检查已跟踪的忽略文件。

下载资源通过准备脚本恢复，换行由 `.gitattributes` 规定：源码 LF，Windows 启动脚本 CRLF。
