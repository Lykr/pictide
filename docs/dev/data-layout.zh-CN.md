# 数据目录与职责

[English](data-layout.md)

[开发文档](README.zh-CN.md)。本页维护运行数据、开发材料与发行产物的目录约定；表结构见[SQLite 存储参考](reference/storage.zh-CN.md)，整理记录见[开发与发行目录分离](issues/development-release-directories.md)。

## 数据位置

数据目录按「启动参数 → PICTIDE_DATA_DIR → 旧 PICTIDE_WEB_DATA_DIR → 默认 data」选择。源码版默认使用项目内 data；便携版默认使用发行目录中的 data。移动整个便携目录后，个人数据与程序一起保留。

自定义目录按系统查阅：[Windows](../guides/setup/windows.zh-CN.md#端口与数据目录) · [Linux](../guides/setup/linux.zh-CN.md#端口与数据目录) · [macOS](../guides/setup/macos.zh-CN.md#端口与数据目录)。相对路径按运行命令时所在目录解析。

## 运行数据

以下路径相对于所选 data：

| 路径 | 内容 |
| --- | --- |
| `db/pictide.sqlite3` | 图片、任务、反馈、后端、设置和推荐学习；运行时可能存在 WAL/SHM |
| `db/candidate.sqlite3` | 个人提示词预设、固定词与当前词库选择 |
| `libraries/*.sqlite3` | 可选择的只读统计词库 |
| `models/minilm/` | 启动前校验的推荐依赖，包含 model.onnx、tokenizer.json、config.json、tokenizer_config.json、special_tokens_map.json；中断下载保留 `.part` 文件 |
| `images/` | 图片及同名提示词 JSON，仅含 positive / negative |
| `workflows/` | API 工作流；.backups 保存更新或删除前的版本 |
| `history-cleanup.json` | 历史图片保留天数，缺省 1 天 |
| `runtime/` | 程序与依赖：源码版 venv；便携版 pictide 程序及随包资源 |
| `cache/` | Python、pip 等运行缓存，可重新生成 |
| `tmp/` | 运行临时文件 |
| `logs/` | 运行日志 |
| `backups/` | 数据备份 |

词库添加与选择见[提示词指南](../guides/prompts.zh-CN.md#添加与切换词库)。MiniLM 是推荐运行所需资源，独立放在 models，日常缓存清理保留该目录。源码与便携启动在提供页面前按固定清单补齐、校验文件，有效文件离线复用，详见[启动准备](../guides/getting-started.zh-CN.md#推荐依赖准备)。前端构建成品由程序提供，源码中的 web/node_modules 指向根目录 dev/runtime/frontend/node_modules。

## 开发材料

开发材料和发行产物相对于项目根目录组织，data 专用于程序运行：

| 路径 | 内容 |
| --- | --- |
| [`corpus/`](corpus.zh-CN.md) | 版本管理的离线下载、可配置统计处理工具和依赖清单 |
| [`docs/dev/`](README.zh-CN.md) | 开发指南、架构、接口、设计规范与需求记录，纳入版本管理 |
| `dev/datasets/` | 长期保留的原始 Parquet 与下载清单；手动离线处理产物 |
| `dev/runtime/frontend/`、`dev/runtime/importer/`、`dev/runtime/builder/` | 前端依赖、离线导入环境与独立便携构建环境 |
| `dev/models/` | 历史构建模型资源；当前构建不使用该目录，已有文件保留 |
| `dev/cache/portable/` | 可重建的便携统计状态、成品词库、报告与 `exports/<fingerprint>/` 下的预构建导出 |
| `dev/cache/`、`dev/tmp/`、`dev/build/` | 其他开发缓存、临时文件与便携构建工作区 |
| `dev/verification/` | 独立验证实例、截图和报告 |
| `dev/maintenance/` | 本机维护脚本和执行记录 |
| `dev/designs/`、`dev/previews/` | 设计素材及历史截图 |
| `dev/legacy/` | 退役的词库目录、模型下载缓存与历史临时材料 |
| `releases/` | 便携发行目录、ZIP、构建报告与 `vocabularies-<contentfingerprint12>/` 下的独立词库版本导出 |

便携构建独立于运行数据准备资源。[预构建发行词库](corpus.zh-CN.md#预构建词库)作为固定资源 Release 附件保存，由 Git 跟踪的 `corpus/prebuilt.json` 引用；SQLite 文件保留在 Git 之外。GitHub Actions 校验并打包这些文件，省去原始元数据处理。词库指纹、校验与原始数据保留规则见[构建资源记录](issues/portable-build-cache.md)。模型文件改为应用启动时准备到运行数据目录，由唯一固定清单 `backend/recommand/model.json` 定义；`corpus/resources.json` 仅记录原始数据集。详见[模型启动准备变更](issues/minilm-startup-download.md)。

源码版和便携版使用相同的运行数据职责与相对路径；源码版的启动环境是 data/runtime/venv，便携版的程序与依赖是 data/runtime/pictide。历史报告中的路径反映当时位置，当前映射见 dev/maintenance。ComfyUI 的模型、环境与输出由 ComfyUI 管理。

## 数据生命周期

开发缓存、前端备份和验证文件可使用[项目清理脚本](cleanup.zh-CN.md)生成审核清单，保留长期资源与个人数据。

- 后端保存产生不可变修订，已有任务引用提交时快照；工作流编辑前保留版本备份。
- 喜欢图片跨栏目保留。清理未喜欢图片会回收图片与提示词 JSON，任务历史继续保存。
- 时间清理和漫游历史数量清理在启动与操作入口执行，说明见[设置与清理](../guides/settings.zh-CN.md#历史图片清理)。
- 反馈与待学习记录同事务落库，推荐在后台处理；历史记录按生成时快照解释。

备份与恢复步骤见[用户指南](../guides/backup.zh-CN.md#备份与恢复)。需要保留本机开发环境、原始数据或发行产物时，另行备份根目录 `dev/` 与 `releases/`。
