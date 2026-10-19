# 生图后端与工作流

[English](backends.md)

[API 索引](../../api.zh-CN.md) · [通用约定与错误](../../api.zh-CN.md#通用约定)

## 生图后端

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| PUT | `/api/backends/{id}` | 后端配置草稿 | 保存的公开配置 |
| DELETE | `/api/backends/{id}` | `{}` | `{deleted:true,id}` |
| POST | `/api/backends/{id}/check` | 后端配置草稿 | `{ok,message}`，只读预检 |
| POST | `/api/backends/{id}/models` | 后端配置草稿 | `{models:[名称],selected:名称或null}` |
| POST | `/api/backends/{id}/template` | 后端配置草稿 | 默认工作流配置及可用 `input_options` |

后端列表由 Bootstrap 的 `backends` 提供，没有单独的 GET 列表路由。路径 ID 为 1–80 位字母、数字、下划线或横线；检查、模型发现和模板请求不保存配置。

| 草稿字段 | 说明 |
| --- | --- |
| `name` | 后端名称 |
| `kind` | 当前支持 `comfyui`，省略时同值 |
| `base_url` | 生图服务 HTTP(S) 地址 |
| `api_key` | 可选；已有配置省略时保留，空串清除；不会返回明文 |
| `workflow_mode` | `default / custom`；未提供工作流时使用默认文生图 |
| `default_checkpoint` | 默认模式的模型名称；空串选择首个可用模型 |
| `workflow` | 自定义 ComfyUI API 节点对象，不是界面的 `nodes` 数组 |
| `bindings` | 自定义正负文本绑定，及可选图像种子绑定 |
| `output_nodes` | 要采集结果的工作流节点 ID 数组 |
| `workflow_name` | 通过保存后端同时保存自定义工作流时使用 |
| `workflow_id` / `workflow_revision` | 修改已保存模板时一起提交，保持原 ID |
| `extra` | 可选适配器扩展对象 |

绑定示例：`{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}}`。当前自定义配置要求正负文本绑定，且不能指向同一输入；种子绑定可省略。节点参数直接在 `workflow` 内编辑。

公开配置包含 `has_api_key`，不含 `api_key`。默认模式解析已安装模型后生成工作流；新任务保存后端快照。删除后端不删除历史任务和图片。保存当前漫游后端后，可恢复因旧错误暂停的预取；不自动重试旧失败任务或恢复播放。

## 工作流库

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/workflows` | 无 | `{workflows:[{id,name,revision}]}` |
| GET | `/api/workflows/{id}` | 无 | 完整工作流记录 |
| POST | `/api/workflows` | `{name,workflow,bindings,output_nodes}` | `201`，新记录 |
| DELETE | `/api/workflows/{id}` | `{revision}` | `{deleted:true,id,detached_backends}` |

完整记录为 `{id,name,workflow,bindings,output_nodes,revision}`。独立 POST 只创建新工作流，名称重复返回 409；更新、重命名并应用已有工作流通过 `PUT /api/backends/{id}` 提交 `workflow_id,workflow_revision,workflow_name`。

`revision` 是工作流文件内容的 SHA-256。删除或更新时须使用读取到的最新值，冲突返回 409。删除保留备份，并解除当前后端的模板引用；后端和历史任务的实际工作流快照保留。
