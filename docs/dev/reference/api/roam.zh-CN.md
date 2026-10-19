# 漫游

[English](roam.md)

[API 索引](../../api.zh-CN.md) · [通用约定与错误](../../api.zh-CN.md#通用约定)

## 漫游

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/settings/roam` | 无 | 漫游配置与状态，见下表 |
| PUT | `/api/settings/roam` | 配置字段，见更新规则 | 保存后的配置与状态 |
| GET | `/api/roam/view` | 无 | `{artifact_id,viewed_at}` |
| PUT | `/api/roam/view` | `{artifact_id,viewed_at}` | 实际保存并解析后的观看位置 |
| POST | `/api/roam/ensure` | `{anchor_id:null或图片ID,demand:false}`；两项均可省略 | 预取状态，可能包含新建的 `job` |

### 配置

| 字段 | 类型及范围 | 默认 |
| --- | --- | --- |
| `prefetch_count` | 整数 0–20；0 关闭自动预取 | 2 |
| `max_history_images` | 整数 0–100000；0 关闭数量清理 | 20 |
| `backend_id` / `preset_id` | 字符串；空串自动选择 | 空串 |
| `playback_interval_seconds` | 整数 1–600 | 8 |
| `liked_tags_only` | 布尔值；喜欢范围 / 全部范围 | `false` |
| `prompt_mode` | `random` 漂流 / `along` 顺流 / `stay` 停泊 | `random` |
| `candidate_count` | 整数 1–20 | 10 |
| `recommendation_strength` | `standard / strong` | `standard` |
| `strong_candidate_multiplier` | 整数 1–5 | 2 |
| `pinned_positive` | 非空完整词项的字符串数组 | `[]` |
| `preset_base_positive` | 只读，当前预设的固定正向词 | `[]` |

响应还包含 `artifact_revision,paused,preference_learning`，暂停时可附 `error`。`epoch` 为内部状态，不作为 HTTP 字段提交。

PUT 可单独更新以下任意一项或组合：`playback_interval_seconds,liked_tags_only,prompt_mode,candidate_count,recommendation_strength,strong_candidate_multiplier,pinned_positive`。更新预取数量、历史数量、后端或预设时须携带 `prefetch_count`，其他未传项保留。切换到另一云端后端时，本次保存强制 `prefetch_count=0`；同一后端之后再次明确保存可开启。创建首个云端后端或将当前后端改为云端时也关闭自动预取。云端生成要求预设负向提示词为空。

切换范围、方式、后端、预设或锚点会保留当前图并使后续旧预取失效；执行中的旧结果完成后隐藏。只改播放间隔、候选数量、推荐力度保留已有预取。预设固定词优先，与之重复的锚点会被移除；停泊时不能修改锚点。数量清理仅统计当前图之前的漫游图片，超限未喜欢图清理，喜欢图仅从漫游隐藏。

### 观看位置与预取

`artifact_id` 可为 null；非空时必须是可见漫游图片。`viewed_at` 为非负安全整数，仅严格较新的时间戳更新。原图已隐藏或清理时 GET 可解析到邻近图。

Ensure 响应包括 `enabled,prefetch_count,target,waiting_for_liked_tags,preference_learning,ready,pending,roam_pending,paused`，按实际情况附 `job,error,recommendation_error,backend_id,preset_id`。`ready` 为锚点之后可看图片数，`pending` 为全应用未完成任务数，`roam_pending` 为未失效的漫游未完成任务数。

一次调用最多创建一个漫游任务，不等待图片生成完成；`demand:true` 在关闭预取时仍可主动请求下一张。喜欢范围空池时返回 `waiting_for_liked_tags:true`，不回退全词库。自动播放计时在浏览器中处理，Ensure 不启动定时投喂循环。详情见[漫游预取](../../issues/roam-pipeline.md)和[漫游方式](../../issues/roam-modes.md)。
