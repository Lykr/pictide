# 数据目录与备份

[文档导航](README.md)。本页说明数据放在哪里、如何保管和恢复；具体表及关联见[SQLite 存储参考](reference/storage.md)，旧部署步骤留在[历史记录](issues/data-layout-history.md)。

## 数据位置

数据目录按「启动参数 → `PICTIDE_DATA_DIR` → 旧 `PICTIDE_WEB_DATA_DIR` → 项目内 `data/`」选择。选择的是整个目录，不是单个数据库文件。便携版默认使用发行目录中的 data，移动整个发行目录后仍能定位个人数据。

自定义目录的命令按系统查阅：[Windows](guides/setup/windows.md#端口与数据目录) · [Linux](guides/setup/linux.md#端口与数据目录) · [macOS](guides/setup/macos.md#端口与数据目录)。相对路径按运行命令时所在目录解析。

## 目录概览

| 路径（相对数据根目录） | 保存内容 |
| --- | --- |
| `pictide.sqlite3` | 后端快照、任务、图片、反馈、漫游设置、用户偏好与评分缓存；运行时可能存在 WAL/SHM |
| `candidate.sqlite3` | 个人预设、固定词与当前词库选择 |
| `libraries/*.sqlite3` | 可选择的只读原名词库、词频、PMI/共现次数及来源 |
| `images/` | 图片和同名提示词 JSON，仅含 positive / negative |
| `workflows/` | 命名 API 工作流；`.backups/` 保存更新或删除前的版本 |
| `history-cleanup.json` | 历史图片保留天数，缺省 1 天 |
| `datasets/`、`import/` | 原始 Parquet、下载校验和离线统计中间数据；在线生成不读取 |
| `cache/embeddings/` | 离线 MiniLM 模型，推荐运行必需，清理时保留 |
| `cache/` | Python、pip、pnpm、Vite 等缓存 |
| `runtime/venv/` | 源码版本 Python 运行环境 |
| `runtime/pictide/` | 便携版程序、随包依赖、前端和首次初始化种子资源 |
| `runtime/frontend/node_modules/` | 前端开发依赖实体 |
| `logs/`、`tmp/` | 日志和临时文件 |
| `previews/`、`verification/` | 预览与验证材料 |
| `backups/`、`maintenance/` | 备份及本机维护记录 |

旧 `prompts/` 可能仍在历史备份内，当前候选不读取。源码 `web/node_modules` 可为数据目录中依赖实体的 Junction，`web/dist/` 是前端构建产物；这些不属于用户图库。ComfyUI 的模型、环境、输入及 output/temp 由 ComfyUI 自行管理。

## 备份与恢复

1. 停止 Pictide，再备份整个选定数据目录；同时保留主库、个人预设库、整个 libraries 词库目录、图片、工作流及设置。
2. 数据库包含后端密钥及历史修订，按含密钥文件保管。删除当前后端配置并不擦除历史快照中的密钥。
3. 恢复时先保留当前数据备份，再使用相应备份整体恢复。迁往新目录或机器后重建 Python 虚拟环境，避免 Windows 绝对路径失效。
4. 需要恢复某个工作流版本时，将 `.backups/<id>-<revision>.json` 复制回 `workflows/<id>.json`；重新启动后在后端中重新选择并保存该模板。

启动脚本不会自动导入别处的数据库。历史素材按清单确认后再清理；运行数据不进入 Git。

## 数据生命周期

- 保存新后端生成不可变修订；已提交任务继续引用原配置。工作流编辑核对 revision，修改前保留文件备份。
- 生成区、漫游区通过任务来源关联区分；喜欢跨来源保留。清理喜欢图只隐藏所在栏目，清理未喜欢图会回收图片与同名 JSON，任务历史保留。
- 时间清理与漫游历史数量清理在启动和操作入口按需执行，没有定时清理任务；具体操作后果见[设置与清理](guides/settings.md#历史图片清理)。
- 反馈和待学习记录一起落库，推荐后台处理；图片旁 JSON 不增加配置或训练数据。

继续查阅：[存储表与快照](reference/storage.md) · [设置接口](reference/api/settings.md) · [部署历史](issues/data-layout-history.md)
