# 用户偏好

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

## 用户偏好

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/recommendation/preferences` | `page` 默认 1；`all` 为 0 或 1，默认 0 | 偏好报告 |
| POST | `/api/recommendation/preferences/reset` | `{request_id,expected_reset_revision}` | `{request_id,reset_revision,reset_at}` |

报告字段：`available,error,feature_version,state_revision,reset_revision,reset_at,evidence_count,term_count,page,page_size,total_pages,terms`。每项 term 为 `{text,channel,weight,evidence_count}`；方向为 `positive / negative`，权重表示模型参数，不是概率。

默认每页 15 条；`all=1` 返回全部已学习词项，供前端导出 JSON，沿用同一接口。查看和导出不触发学习，不包含完整学习矩阵，无法用于恢复训练状态。只接受 page、all 查询参数。

重置 `request_id` 为 1–128 位字母、数字、下划线或横线，`expected_reset_revision` 使用最新报告值。重复请求可安全重试，修订冲突返回 409。重置清除学习状态及评分缓存，保留图片和评价，不把重置前的反馈自动重放为新学习。详见[用户偏好](../../issues/recommendation-preferences.md)和[导出](../../issues/preference-export.md)。
