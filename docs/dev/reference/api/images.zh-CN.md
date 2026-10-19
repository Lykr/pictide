# 图片、反馈与偏好评分

[English](images.md)

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

## 图片与反馈

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/artifacts` | 图片列表查询参数 | 图片窗口，见下文 |
| GET | `/api/artifacts/{id}/image` | 无 | 图片文件二进制 |
| GET | `/api/artifacts/{id}/prompts` | 无 | 下载 JSON：`{positive,negative}` |
| PUT | `/api/artifacts/{id}/feedback` | `{value:1或-1或null}` | `{artifact,artifact_revision}` |
| DELETE | `/api/generated` | `{}` | `{removed,hidden,revision,pending_files}` |
| DELETE | `/api/generated/{id}` | `{}` | 同上，仅一张生成页图片 |

### 图片查询

| 参数 | 说明 |
| --- | --- |
| `liked` | `1` 仅喜欢图片，否则全部评价状态 |
| `limit` | 1–200，默认 200；喜欢页客户端使用 100 |
| `before` | 上一窗口的 `next_cursor`，继续读取更早图片 |
| `source` | `all / roam / generate`，默认 all |
| `around` | 漫游窗口中心图片 ID；仅 source=roam，不能与 before 或 liked=1 同用 |
| `tag` | 可重复，如 `?liked=1&tag=smile&tag=long%20hair`；仅喜欢筛选，多个条件为 AND |

响应为 `{artifacts,has_more,has_newer,anchor_id,next_cursor,total,counts,source,revision}`。通常按时间和 ID 从新到旧排列。`counts` 包含 `artifacts,roam,generate,liked`，是全局计数；`total` 为本次筛选总数。`next_cursor` 在还有更早图片时为末项 ID，否则 null。

### Artifact

主要字段：`id,job_id,node_id,output_index,created_at,local_path,content_type,deleted_at,generated_hidden_at,roam_hidden_at,positive,negative,seed,feedback,source,seed_applied,image_url`。`image_url` 指向同源图片接口；`seed` 是图像种子，是否实际绑定到工作流看 `seed_applied`。词项信息以生成时实际文本为准。

反馈 `1` 喜欢、`-1` 不喜欢、`null` 撤回为未评价。反馈落库后返回，偏好学习及本次反馈触发的清理由编排层后台处理；评分可能暂时使用上一版偏好。重复设置同一状态不重复计入学习。

生成图片清理：未喜欢图清除图片记录的可见状态并回收本地图片及提示词 JSON；喜欢图只从生成页隐藏，喜欢页保留；任务历史保留。不能用该接口清理漫游图。

## 喜欢筛选与图片偏好评分

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/liked/tags` | 无 | `{tags:[{text,count}],revision}` |
| GET | `/api/liked/ranked` | 可重复 `tag`，同喜欢图片筛选 | `{artifacts,revision,state_revision,score_min,score_max,scoring_available,error,refreshed_at}` |
| POST | `/api/liked/ranked/refresh` | `{tags:[]}`，或当前筛选词数组 | 同 ranked，主动重算该范围 |
| GET | `/api/artifacts/{id}/preference-score` | 无 | 图片偏好评分，见下文 |

标签计数为所有喜欢图中包含该正向词项的图片数，同图同词只计一次；列表默认字典序。Ranked 返回当前筛选范围的全部图片，客户端以每页 100 张分页；按原始偏好分数降序，同分按时间和 ID 降序，无评分图置后。

单图评分返回 `{status,score,love_score,score_min,score_max,state_revision,feature_version,reason}`：

- `status`：`scored / missing_snapshot / unavailable`。
- `score`：确定性后验均值分数，原始数值，不是抽样选择分，也不是百分比。
- `love_score`：按历史评分范围转换的 0–100 相对值：`100 × (score-score_min)/(score_max-score_min)`；范围不可用或相等时为 null，不代表喜欢概率。
- `state_revision,feature_version`：该缓存分数的学习状态与特征版本；无法评分时相关字段为 null，`reason` 提供说明。

分数持久缓存到图片信息；普通读取只补缺失缓存，不因每次学习而重算历史图片。主动 refresh 重算所选范围，更新 `refreshed_at`；普通读取不更新该时间。重置偏好会清除评分缓存。推荐暂不可用时仍可能展示已有缓存；刷新失败保留旧缓存，检查 `scoring_available,error`。详情见[评分缓存](../../issues/image-score-cache.md)。
