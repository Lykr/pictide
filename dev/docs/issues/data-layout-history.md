# 数据部署历史记录

[需求目录](README.md)。下文是旧版本部署时的原记录，按当时语境保留，不适用于当前安装步骤。其中“只保留喜欢”的旧状态后来已由正负反馈恢复；现行表和备份方式见[存储参考](../reference/storage.md)与[数据目录](../data-layout.md)。不要据此重复运行旧转换命令。

## 喜欢状态升级

图片只有喜欢或未评价两种状态：`feedback` 表仅保存 `value=1` 的记录，撤回喜欢删除对应记录。升级首次启动时，在 SQLite 事务中重建旧反馈表，保留所有用户的喜欢记录及其时间；旧 `-1` 标记移除并按未评价处理，不删除对应图片、提示词、任务或候选快照。再次启动不会重复迁移。正负提示词属于生图文本，与此变更无关。

部署升级前先停止应用并备份 SQLite，保留可恢复的原反馈数据；日常完整备份仍按上述数据目录备份方式执行。未标记喜欢的图片继续遵循既有历史清理期限。

## 正负反馈表更新

不喜欢反馈发布前先停止应用并备份 `pictide.sqlite3`，再执行 `python -m backend.store.feedback_upgrade <数据库绝对路径>`。这是针对当前安装的一次性离线转换，将推荐事件与证据的 `liked` 转为 `value`（喜欢 1、撤回 null），并允许图片反馈 -1；保留已有点赞、策略参数、向量缓存、修订与重置分界。不在应用启动时执行。转换后使用对应新版代码启动；需要回退时恢复完整数据库备份与旧代码。见 [不喜欢反馈](dislike-feedback.md)。

## 喜欢图片标签范围

`roam_settings.liked_tags_only` 为 0/1，默认 0；播放间隔与该开关复用同一设置行。当前安装发布前停止应用、备份主数据库，再离线执行 `ALTER TABLE roam_settings ADD COLUMN liked_tags_only INTEGER NOT NULL DEFAULT 0 CHECK(liked_tags_only IN (0,1))`。新建数据库直接包含该字段，不在启动时迁移；回退需恢复备份数据库与对应旧代码。喜欢图片的标签池按实际正向文本即时解析，不另存派生词库。接口与空池行为见 [喜欢图片标签漫游](roam-liked-tags.md)。

## 漫游方式与预取失效

发布前停止应用并备份主库，离线增加 `roam_settings.prompt_mode TEXT NOT NULL DEFAULT 'random' CHECK(prompt_mode IN ('random','along','stay'))` 和 `roam_jobs.discarded_at TEXT`；新库直接包含，不在启动时迁移。前者保存漫游方式，后者保存未完成旧任务的失效时间。切换设置事务复用 `roam_hidden_at` 隐藏当前图之后的旧缓存，喜欢和图片文件保留；迟到产物入库时直接隐藏。顺流与停泊参考来自既有任务快照和观看位置，不新增状态表。完整接口见 [漫游方式](roam-modes.md)。
