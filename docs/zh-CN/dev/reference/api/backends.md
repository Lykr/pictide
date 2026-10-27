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
| `prompt_type` | `danbooru / natural_language`，省略时为 `danbooru`；自然语言模式使用独立的[提示词服务](settings.md#提示词-llm-api) |
| `canvas_pool_id` | 可选，已保存的像素画幅池 ID；空串使用 API 固定尺寸。漫游开启画幅池时从中抽取，生成页可为整批指定一组像素宽高，省略时保留固定设置 |
| `llm_id` | 自然语言转换使用的已保存 LLM API ID；新配置必须选择已有连接，缺少此字段的旧配置使用 `legacy-prompt-api` |
| `base_url` | 生图服务 HTTP(S) 根地址；云端包含版本路径，如 `https://api.openai.com/v1` 或 `https://generativelanguage.googleapis.com/v1beta` |
| `api_key` | 可选；同类型配置省略时保留已有密钥，切换类型或传入空串时清除；不会返回明文 |
| `model` | `openai` 与 `gemini` 必填模型 ID，手动输入 |
| `size` / `quality` | OpenAI 可选图片参数；留空使用服务默认值 |
| `aspect_ratio` / `image_size` | Gemini 可选图片参数；留空使用服务默认值 |
| `workflow_mode` | `default / custom`；未提供工作流时使用默认文生图 |
| `default_checkpoint` | 默认模式的模型名称；空串选择首个可用模型 |
| `workflow` | 自定义 ComfyUI API 节点对象，不是界面的 `nodes` 数组 |
| `bindings` | 自定义正负文本绑定，及可选图像种子和成对的整数宽高绑定 |
| `output_nodes` | 要采集结果的工作流节点 ID 数组 |
| `workflow_name` | 通过保存后端同时保存自定义工作流时使用 |
| `workflow_id` / `workflow_revision` | 修改已保存模板时一起提交，保持原 ID |
| `extra` | 可选适配器扩展对象 |

绑定示例：`{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}}`。当前自定义配置要求正负文本绑定，且不能指向同一输入；种子绑定可省略。可选 `width`、`height` 沿用 `{node_id,input}` 格式，须同时提供并指向不同的整数输入；默认工作流自动绑定两项。固定节点参数在 `workflow` 内编辑；漫游使用画幅池时只覆盖明确绑定的尺寸输入。

工作流字段、checkpoint 发现及模板路由归 ComfyUI 使用。云端 `/models` 返回已配置的模型，不发现模型目录；`/check` 只读查询所选模型，不提交生图，也不能证明账号具有图片输出权限或验证生成质量。

公开配置包含 `capabilities`，字段为 `negative_prompt`、`seed`、`dimensions`、`models`、`events`、`cancel`、`recovery` 和 `cloud`。本次 OpenAI Images 与 Gemini 接入不支持负向提示词通道、指定图像种子、远端事件、取消或恢复。Danbooru 模式拒绝非空负向提示词，包括候选预设输出；自然语言准备则要求 LLM 把规避要求融入正向描述，并返回空的负向字符串。指定图像种子仍会拒绝，候选种子只在本地控制抽词。界面按能力显示可用控件。

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

## 画幅池

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/canvas-pools` | 无 | `[{id,name,sizes,revision}]` |
| PUT | `/api/canvas-pools/{id}` | `{name,sizes:[{width,height}]}` | 保存后的完整画幅池列表 |
| DELETE | `/api/canvas-pools/{id}` | `{}` | 剩余画幅池列表 |

ID 格式与后端 ID 相同，去除两端空格后的名称为 1–100 字符。一个池包含 1–64 组不重复尺寸，宽高均为 1–16384 的整数。只保存精确像素，不设比例、像素预算或权重字段。PUT 整体替换画幅池并创建修订；仍被当前生图 API 引用时，删除返回 `400`。

`capabilities.dimensions` 标识支持像素计划的适配器：OpenAI Images，以及同时绑定宽高的 ComfyUI 工作流。ComfyUI 过滤非 8 倍数的尺寸，保存时须为每个关联 API 至少保留一组可用值。OpenAI 服务或模型可有额外尺寸限制，由服务在生图时检查。Gemini 不支持像素计划，拒绝非空 `canvas_pool_id`。

App 对画幅池修改、生图 API 引用保存和漫游入队串行处理。画幅池模式下，修改当前池的尺寸会使后续预取失效；未使用的池和仅改名称不影响预取。共享列表参与普通资源刷新及断线轮询，不依赖 SSE 必须保留某个主题。刷新保留未保存草稿，修订未变时保持当前编辑器；已有任务的宽高不受之后的画幅池修改影响。
