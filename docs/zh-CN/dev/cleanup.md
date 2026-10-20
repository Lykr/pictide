# 项目目录清理

[English](../../dev/cleanup.md)

[数据目录](data-layout.md) · [开发流程](development.md)

使用 `scripts/clean_project.py` 审核可清理的开发文件，再按确认的清单删除。需要 Python 3.10+ 和 Git，无额外依赖。以下命令在项目根目录使用自己的 Python 解释器执行。

## 预览并审核

```shell
python scripts/clean_project.py
```

脚本在 `dev/maintenance/` 创建新的 JSON 清单，显示候选路径、大小和修改时间，默认保留最近七天修改过的内容。要将近期文件也纳入预览：

```shell
python scripts/clean_project.py --older-than-days 0
```

| 分组 | 清理范围 |
| --- | --- |
| `caches` | `dev/cache/`、`dev/build/`、`dev/tmp/` 的子项，包括可重新构建的词库统计和导出缓存 |
| `backups` | `data/backups/` 下独立的前端备份：子项只包含有 `index.html` 的 `dist/` |
| `verification` | `dev/verification/` 下可丢弃的报告、截图、隔离测试数据等子项 |

默认预览三个分组。可用 `--groups caches verification` 选择分组，或用 `--plan dev/maintenance/my-cleanup.json` 指定新的清单文件名，已有清单不会覆盖。

检查清单中的 `entries`，移除希望保留的条目。`skipped` 记录保留原因。候选项中存在模型、原始数据文件、环境、仓库、Git 跟踪文件、符号链接或 Windows junction 时，整项保留；个人数据库、图片和工作流备份也保留。其余 `data/` 内容，以及 `dev/datasets/`、`dev/models/`、`dev/runtime/`、`dev/maintenance/`、`releases/` 均在清理范围之外。

## 执行审核后的清单

先结束构建，关闭使用清单目录的验证实例，再传入刚审核的清单路径：

```shell
python scripts/clean_project.py --apply dev/maintenance/my-cleanup.json
```

这会永久删除清单中的条目。删除前重新检查项目根目录、允许路径、Git 跟踪状态、链接、文件大小和修改时间；预览后有变化时，重新生成并审核清单。指纹覆盖文件和目录元数据，不读取文件内容计算哈希。执行中遇到文件变动或占用而中途停止时，终端会列出已完成的删除；为剩余内容重新生成清单即可。

含模型的验证目录和个人备份如需删除，应单独审核。删除便携词库缓存后，重新构建可复用保留的原始数据，或显式指定已发布的预构建词库。应用历史和图片清理仍通过[设置](../guides/settings.md#历史图片清理)操作。
