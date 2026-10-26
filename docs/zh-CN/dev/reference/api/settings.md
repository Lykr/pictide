# 应用与 LLM 设置

[English](../../../../dev/reference/api/settings.md)

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

通用设置支持部分更新，未传字段保留。历史清理作用于未喜欢图片，包括未评价和不喜欢；喜欢图片保留。`cleanup` 为清理统计，详情见[数据目录](../../data-layout.md)。

## 本地 ComfyUI 生命周期

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/settings/local-generation` | 无 | localhost 返回 `{can_configure,config,choices,status,restart_required}`，其他地址返回 `{can_configure:false}` |
| PUT | `/api/settings/local-generation` | 至少一个配置字段 | 校验并原子保存后，返回与 GET 相同的对象 |
| POST | `/api/settings/local-generation/detect` | `{backend_id,install_dir?}` | `{candidates:[{install_dir,python,entry,cwd,args,source}]}` |

配置包括 `enabled`（布尔值）、`backend_id,install_dir,python,entry,cwd`（字符串）与 `args`（分别保存每项参数的字符串数组）。PUT 支持部分更新，拒绝未知字段。启用时，必须关联已保存的 ComfyUI 连接，其地址为直接访问回环地址的 HTTP URL，并有有效的本地 Python、`main.py` 和工作目录。可识别的便携或虚拟环境可补齐未填写的启动路径；只有一个候选时可自动补齐安装位置。路径或关联连接已丢失时仍可关闭启停功能。参数数组最多 256 项、总计 32768 字符；路径与参数不接受 NUL 或换行。

`choices` 只公开可用连接的 ID、名称和地址，不包含 API Key。`status` 包括 `phase`（`disabled / starting / running / external / failed / stopped`）、`owned,url,error,log_path`，描述本次 Pictide 会话；`restart_required` 对比已保存设置与本次启动配置。保存通过现有 SSE change 事件发布 `local_generation` 主题，下次进程启动时生效，不启动 ComfyUI 或图片任务。识别过程只读；存在多个候选时需用户选择。启动时，关联 API 的地址与端口优先于 ComfyUI 参数中冲突的监听地址和端口。

读取启动配置、保存和识别都要求请求来自回环地址，且 Host 为 localhost；在现有同源保护之外，其他来源的写入或识别请求返回 403。LAN 调用 GET 不会得到本地路径。正常启动复用已经就绪的服务，不取得其所有权；退出时只停止本次会话启动的子进程树。启动失败后仍开放 HTTP/bootstrap，便于在设置中修复配置。

## 提示词 LLM API

`GET /api/llm-apis` 返回 `{id,name,kind,base_url,model,revision,has_api_key,account}` 记录列表。`kind` 为 `openai`（OpenAI-compatible Chat Completions）或 `chatgpt`（使用账号套餐授权的官方 Responses）。`account` 仅包含邮箱、连接与套餐状态，以及首次使用确认状态，不返回凭据。

`PUT /api/llm-apis/{id}` 保存 `{name,kind,base_url,model,api_key}`，返回连接列表。ID 为 1–80 位字母、数字、下划线或横线，名称为 1–100 字符。OpenAI-compatible 配置要求 HTTP(S) URL，不含凭据、查询或片段，且模型 ID 非空。省略密钥保留原值，空串清除。已保存连接的类型不可变，需新建记录来切换类型。ChatGPT 记录可先不填模型，以便登录后发现。保存不提交推理请求。

`DELETE /api/llm-apis/{id}` 拒绝删除被自然语言生图 API 引用的连接；其他连接删除配置并断开可续期会话，返回 `{connections,revoked}`。远端撤销未获确认时会报告，本地令牌仍会移除。

ChatGPT 操作使用 `POST /api/llm-apis/{id}/{operation}`，发送空 JSON 对象：

| 操作 | 结果 |
| --- | --- |
| `sign-in` | `{authorization_url}`；要求回环来源与 localhost Host |
| `cancel` | 取消待完成登录并关闭回调监听 |
| `models` | 账号模型目录中的 `{models:[{value,label}]}` |
| `disconnect` | `{revoked}`；清除本地令牌，保留注册身份 |
| `welcome` | 确认首次使用套餐说明 |

`GET /api/llm-apis/{id}/status` 返回 `idle / pending / exchanging / connected / failed / cancelled / expired`，按需附安全的错误信息。登录十分钟后过期；回调绑定 PKCE、state、nonce 和已签发客户端 ID，校验签名身份，不会激活与原账号不匹配的返回账号。

旧 `GET/PUT /api/settings/prompting` 保留为迁移后的 `legacy-prompt-api` 别名，仍返回 `{base_url,model,revision,has_api_key}`。缺少 `llm_id` 的旧自然语言生图配置只使用此旧 ID。新配置必须明确选择连接，不任意采用首个连接，也不自动切换计费方式。

保存会创建修订并使已有准备失效。转换使用生图 API 选中的连接，文本服务凭据不进入图片任务。主动自然语言预览会调用文本服务，消耗其套餐额度或 API 用量。

ChatGPT 转换使用流式 Responses，以严格 JSON Schema 返回 `positive` 和 `negative` 字符串。完整文本可能先通过 output text/item 事件到达；Pictide 保留这些片段，但仅在收到状态为 completed 的 `response.completed` 后接受结果。请求参数错误会停止转换，不自动重试或退出登录。错误保留 HTTP 状态和长度受限的错误代码、参数名；服务商提供请求 ID 时也会记入日志。服务商 message/detail 正文可能回显提示词或凭据，因此省略。普通 HTTP 400 应检查模型和请求格式，仅在确认会话过期或已撤销时重新登录。
