# 通用与历史设置

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

## 通用与历史设置

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/settings/general` | 无 | `{theme,language,image_transitions}` |
| PUT | `/api/settings/general` | 至少一项通用设置 | 保存后的完整通用设置 |
| GET | `/api/settings/history` | 无 | `{unliked_retention_days,cleanup,artifact_revision}` |
| PUT | `/api/settings/history` | `{unliked_retention_days}` | 同 GET，并触发懒清理检查 |

| 字段 | 类型及范围 | 默认 |
| --- | --- | --- |
| `theme` | `system / light / dark` | `system` |
| `language` | `system / zh-CN / en` | `system` |
| `image_transitions` | 布尔值 | `true` |
| `unliked_retention_days` | 整数 0–3650；0 关闭时间清理 | 1 |

通用设置支持部分更新，未传字段保留。历史清理作用于未喜欢图片，包括未评价和不喜欢；喜欢图片保留。`cleanup` 为清理统计，详情见[数据目录](../../../../docs/data-layout.md)。
