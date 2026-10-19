# 初始化与实时事件

[English](events.md)

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

## 初始化与实时事件

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/bootstrap` | 无 | 初始化数据，字段见下文 |
| GET | `/api/events` | SSE 长连接 | `event: change`，data 为 `{revision,topic}` |

Bootstrap 包括：`name,module,version,database_path,data_directory,backend_types,backends,jobs,artifacts,roam_view,roam_settings,artifact_revision,counts,artifact_page,recommendation,capabilities`。后端配置隐藏 API Key；`jobs` 为最近 100 条，`artifacts` 为保存观看位置附近的漫游窗口。通用、历史设置另行读取各自接口。

`recommendation` 包括 `available,model_version,feature_version,policy_version,error`。`capabilities` 包括 `generation,feedback,preference_learning,cooccurrence_prompts,prompt_sequences,events,roam_prefetch`。

SSE 首条主题为 `ready`，之后可能为 `jobs,feedback,artifacts,backends,workflows,candidate,settings,roam_settings,general_settings,recommendation`；约 20 秒无变化发送注释心跳。它是刷新通知，客户端收到后重读有关资源。`revision` 为进程内递增值，重启归零；没有历史事件重放，慢客户端可能只收到最近通知。
