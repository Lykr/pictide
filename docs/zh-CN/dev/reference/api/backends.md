# 生图后端与工作流

[English](../../../../dev/reference/api/backends.md)

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

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
| `kind` | `comfyui / openai / gemini`，省略时为 `comfyui` |
| `base_url` | 生图服务 HTTP(S) 根地址；云端包含版本路径，如 `https://api.openai.com/v1` 或 `https://generativelanguage.googleapis.com/v1beta` |
| `api_key` | 可选；同类型配置省略时保留已有密钥，切换类型或传入空串时清除；不会返回明文 |
| `model` | `openai` 与 `gemini` 必填模型 ID，手动输入 |
| `size` / `quality` | OpenAI 可选图片参数；留空使用服务默认值 |
| `aspect_ratio` / `image_size` | Gemini 可选图片参数；留空使用服务默认值 |
| `workflow_mode` | `default / custom`；未提供工作流时使用默认文生图 |
| `default_checkpoint` | 默认模式的模型名称；空串选择首个可用模型 |
| `workflow` | 自定义 ComfyUI API 节点对象，不是界面的 `nodes` 数组 |
| `bindings` | 自定义正负文本绑定，及可选图像种子绑定 |
| `output_nodes` | 要采集结果的工作流节点 ID 数组 |
| `workflow_name` | 通过保存后端同时保存自定义工作流时使用 |
| `workflow_id` / `workflow_revision` | 修改已保存模板时一起提交，保持原 ID |
| `extra` | 可选适配器扩展对象 |

绑定示例：`{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}}`。当前自定义配置要求正负文本绑定，且不能指向同一输入；种子绑定可省略。节点参数直接在 `workflow` 内编辑。

工作流字段、checkpoint 发现及模板路由归 ComfyUI 使用。云端 `/models` 返回已配置的模型，不发现模型目录；`/check` 只读查询所选模型，不提交生图，也不能证明账号具有图片输出权限或验证生成质量。

公开配置包含 `capabilities`，字段为 `negative_prompt`、`seed`、`models`、`events`、`cancel`、`recovery` 和 `cloud`。本次 OpenAI Images 与 Gemini 接入不支持负向提示词、指定图像种子、远端事件、取消或恢复；非空负向提示词（包括候选预设输出）与指定图像种子会明确拒绝，不静默丢弃。候选种子只在本地控制抽词。界面按能力显示可用控件。

OpenAI 在 Base URL 后追加 `/images/generations`，Gemini 追加 `/interactions`。Gemini 使用 `x-goog-api-key` 认证，发送 `model`、`input`、含图片输出选项的 `response_format` 和 `store:false`。这两个适配器只负责单轮文生图；`generateContent`、Imagen、图像编辑及第三方服务预设不在本次范围。成功结果可为 Base64 或图片 URL，先保存到本地再作为 Pictide 产物提供。API Key 由后端调用服务使用，浏览器不直接向服务商发请求。

云端提交等待完整响应；没有已记录结果的超时或中断使任务保持不确定，不自动重发。本地取消不能保证远端取消或免于计费。任务和图片暴露 `backend_kind`，用于区分历史服务语义；快照保留模型和实际请求参数，不将不支持的种子记录为已执行。云端接入用协议模拟服务验证，收费服务真实出图尚未验证。

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
