# 数据目录与备份

[文档导航](README.md)。本页说明当前数据布局与备份；表结构见[SQLite 存储参考](reference/storage.md)，本次整理记录见[数据目录整理](issues/data-directory-organization.md)。

## 数据位置

数据目录按「启动参数 → PICTIDE_DATA_DIR → 旧 PICTIDE_WEB_DATA_DIR → 默认 data」选择。源码版默认使用项目内 data；便携版默认使用发行目录中的 data。移动整个便携目录后，个人数据与程序一起保留。

自定义目录按系统查阅：[Windows](guides/setup/windows.md#端口与数据目录) · [Linux](guides/setup/linux.md#端口与数据目录) · [macOS](guides/setup/macos.md#端口与数据目录)。相对路径按运行命令时所在目录解析。

## 运行数据

以下路径相对于所选 data：

| 路径 | 内容 |
| --- | --- |
| `db/pictide.sqlite3` | 图片、任务、反馈、后端、设置和推荐学习；运行时可能存在 WAL/SHM |
| `db/candidate.sqlite3` | 个人提示词预设、固定词与当前词库选择 |
| `libraries/*.sqlite3` | 可选择的只读统计词库 |
| `models/minilm/` | 离线推荐模型，包含 model.onnx、tokenizer.json、config.json、tokenizer_config.json、special_tokens_map.json |
| `images/` | 图片及同名提示词 JSON，仅含 positive / negative |
| `workflows/` | API 工作流；.backups 保存更新或删除前的版本 |
| `history-cleanup.json` | 历史图片保留天数，缺省 1 天 |
| `runtime/` | 程序与依赖：源码版 venv、前端开发依赖；便携版 pictide 程序及随包资源 |
| `cache/` | Python、pip、pnpm、Vite 等可重新生成的缓存 |
| `tmp/` | 运行临时文件 |
| `logs/` | 运行日志 |
| `backups/` | 数据备份 |

词库添加与选择见[提示词指南](guides/prompts.md#添加与切换词库)。MiniLM 是推荐运行所需资源，独立放在 models，日常缓存清理保留该目录。前端构建成品由程序提供，源码中的 web/node_modules 可以是指向 runtime/frontend/node_modules 的链接。

## 开发材料

主项目的开发内容统一归入 data/dev；普通便携运行会按需创建运行目录。

| 路径 | 内容 |
| --- | --- |
| `dev/datasets/` | 原始 Parquet、下载校验与离线统计中间文件 |
| `dev/releases/` | 便携发行目录、ZIP 和构建报告 |
| `dev/verification/` | 独立验证实例、截图和报告 |
| `dev/maintenance/` | 本机维护脚本和执行记录 |
| `dev/designs/`、`dev/previews/` | 设计素材及历史截图 |
| `dev/legacy/` | 退役的词库目录、模型下载缓存与历史临时材料 |

开发材料与运行数据分别管理；历史文件的原路径以当时报告为准，整理后的对应位置见维护记录。ComfyUI 的模型、环境与输出由 ComfyUI 管理。

## 备份与恢复

1. 停止 Pictide，备份 db、images、workflows 和 history-cleanup.json；同时保存 libraries、models，便于完整离线恢复。需要保留开发材料时另备份 dev。
2. 数据库包含后端密钥与历史修订，按含密钥文件保管。删除当前后端配置后，历史快照继续保留。
3. 恢复前保留当前数据备份，再恢复相应文件。跨机器使用时重新准备源码虚拟环境，或使用对应系统的便携包。
4. 单独恢复工作流时，将 workflows/.backups 中目标版本复制回原工作流文件，并在后端设置中重新选择、保存。

图片、任务与反馈应使用同一备份时点。保留 db 下运行时的 SQLite 辅助文件，停止服务后再进行文件级备份和整理。

## 数据生命周期

- 后端保存产生不可变修订，已有任务引用提交时快照；工作流编辑前保留版本备份。
- 喜欢图片跨栏目保留。清理未喜欢图片会回收图片与提示词 JSON，任务历史继续保存。
- 时间清理和漫游历史数量清理在启动与操作入口执行，说明见[设置与清理](guides/settings.md#历史图片清理)。
- 反馈与待学习记录同事务落库，推荐在后台处理；历史记录按生成时快照解释。

继续查阅：[存储表与快照](reference/storage.md) · [设置接口](reference/api/settings.md)
