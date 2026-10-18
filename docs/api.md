# HTTP API 参考

本文集中整理 Pictide 当前已实现的浏览器端 HTTP API，按 [Host 路由](../backend/host.py)与[应用编排](../backend/application.py)核对。功能设计和交付记录仍在 [issues](README.md#需求与功能记录)；修改接口时同步更新本文。

## 通用约定

- 默认地址：`http://127.0.0.1:8189`；以下路径均相对此地址。局域网启动方式见[项目 README](../README.md#局域网访问)。当前没有账号认证，数据和偏好共用本地用户 `local`。
- 除图片、下载和 SSE 外，响应为 JSON。成功通常返回 `200`；提交任务为 `202`，单独新建工作流为 `201`。
- 所有非 GET/HEAD 的 `/api/` 请求，包括 DELETE，必须携带 `Content-Type: application/json`；无参数时发送 `{}`。请求体须为 JSON 对象，不允许重复字段或 NaN/Infinity。通常上限 8 MiB，候选请求 1,100,000 字节，重置偏好请求 2,048 字节。
- 修改请求的 `Origin` 若存在须与访问地址同源，`Sec-Fetch-Site: cross-site` 被拒绝；Host 限制为本机地址或局域网入口允许的本机内网 IP。未开放通用跨域调用。
- API 响应使用 `Cache-Control: no-store`。这不表示图片偏好评分每次重新计算，评分另有持久缓存。
- 时间通常为 ISO 8601 UTC 字符串；观看位置 `viewed_at` 是毫秒整数。安全整数上限为 `9007199254740991`。
- `{id}` 代表对应资源 ID。列表中的 ID 应作为不透明标识使用，调用方不依赖其生成规则。

### 错误

业务错误通常返回 `{"error":"说明"}`；候选接口的校验错误另有 `"kind":"validation"`。HTTP 层拒绝可能返回纯文本，调用方应先检查状态码与 Content-Type。

| 状态 | 含义 |
| --- | --- |
| 400 | 参数、JSON 或生图后端校验错误 |
| 403 | Host 或跨站修改限制 |
| 404 | 路由或资源不存在 |
| 409 | 修订号、重复请求内容或名称冲突 |
| 410 | 资源已清理且不再可访问 |
| 413 / 415 | 请求过大 / 缺少正确的 JSON Content-Type |
| 502 | 获取图片时上游后端失败 |

部分接口通过 `200` 返回业务不可用状态，例如连接检查 `ok:false`、漫游 `paused:true`、评分 `status:"unavailable"`，不能仅靠 HTTP 状态判断业务成功。

## 初始化与实时事件

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/bootstrap` | 无 | 初始化数据，字段见下文 |
| GET | `/api/events` | SSE 长连接 | `event: change`，data 为 `{revision,topic}` |

Bootstrap 包括：`name,module,version,database_path,data_directory,backend_types,backends,jobs,artifacts,roam_view,roam_settings,artifact_revision,counts,artifact_page,recommendation,capabilities`。后端配置隐藏 API Key；`jobs` 为最近 100 条，`artifacts` 为保存观看位置附近的漫游窗口。通用、历史设置另行读取各自接口。

`recommendation` 包括 `available,model_version,feature_version,policy_version,error`。`capabilities` 包括 `generation,feedback,preference_learning,cooccurrence_prompts,prompt_sequences,events,roam_prefetch`。

SSE 首条主题为 `ready`，之后可能为 `jobs,feedback,artifacts,backends,workflows,candidate,settings,roam_settings,general_settings,recommendation`；约 20 秒无变化发送注释心跳。它是刷新通知，客户端收到后重读有关资源。`revision` 为进程内递增值，重启归零；没有历史事件重放，慢客户端可能只收到最近通知。

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

通用设置支持部分更新，未传字段保留。历史清理作用于未喜欢图片，包括未评价和不喜欢；喜欢图片保留。`cleanup` 为清理统计，详情见[数据目录](data-layout.md)。

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
| `prefetch_count` | 整数 0–20；0 关闭自动预取 | 0 |
| `max_history_images` | 整数 0–100000；0 关闭数量清理 | 0 |
| `backend_id` / `preset_id` | 字符串；空串自动选择 | 空串 |
| `playback_interval_seconds` | 整数 1–600 | 5 |
| `liked_tags_only` | 布尔值；喜欢范围 / 全部范围 | `false` |
| `prompt_mode` | `random` 漂流 / `along` 顺流 / `stay` 停泊 | `random` |
| `candidate_count` | 整数 1–20 | 4 |
| `recommendation_strength` | `standard / strong` | `standard` |
| `strong_candidate_multiplier` | 整数 1–5 | 2 |
| `pinned_positive` | 非空完整词项的字符串数组 | `[]` |
| `preset_base_positive` | 只读，当前预设的固定正向词 | `[]` |

响应还包含 `artifact_revision,paused,preference_learning`，暂停时可附 `error`。`epoch` 为内部状态，不作为 HTTP 字段提交。

PUT 可单独更新以下任意一项或组合：`playback_interval_seconds,liked_tags_only,prompt_mode,candidate_count,recommendation_strength,strong_candidate_multiplier,pinned_positive`。更新预取数量、历史数量、后端或预设时须携带 `prefetch_count`，其他未传项保留。

切换范围、方式、后端、预设或锚点会保留当前图并使后续旧预取失效；执行中的旧结果完成后隐藏。只改播放间隔、候选数量、推荐力度保留已有预取。预设固定词优先，与之重复的锚点会被移除；停泊时不能修改锚点。数量清理仅统计当前图之前的漫游图片，超限未喜欢图清理，喜欢图仅从漫游隐藏。

### 观看位置与预取

`artifact_id` 可为 null；非空时必须是可见漫游图片。`viewed_at` 为非负安全整数，仅严格较新的时间戳更新。原图已隐藏或清理时 GET 可解析到邻近图。

Ensure 响应包括 `enabled,prefetch_count,target,waiting_for_liked_tags,preference_learning,ready,pending,roam_pending,paused`，按实际情况附 `job,error,recommendation_error,backend_id,preset_id`。`ready` 为锚点之后可看图片数，`pending` 为全应用未完成任务数，`roam_pending` 为未失效的漫游未完成任务数。

一次调用最多创建一个漫游任务，不等待图片生成完成；`demand:true` 在关闭预取时仍可主动请求下一张。喜欢范围空池时返回 `waiting_for_liked_tags:true`，不回退全词库。自动播放计时在浏览器中处理，Ensure 不启动定时投喂循环。详情见[漫游预取](issues/roam-pipeline.md)和[漫游方式](issues/roam-modes.md)。

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

## 生成任务

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/jobs` | 无 | `{jobs:[Job]}`，最近 100 条 |
| GET | `/api/jobs?page=1` | `page` 正整数 | `{jobs,page,page_size,total,total_pages}` |
| POST | `/api/jobs` | 生成请求，见下表 | `202`，`{job,jobs,next_seed,candidate_result,next_candidate}` |
| POST | `/api/jobs/cancel-pending` | `{}` | `{cancelled_count}` |
| POST | `/api/jobs/{id}/cancel` | `{}` | `{job}` |

分页固定每页 15 条，超出末页返回末页。

| 生成字段 | 类型及说明 |
| --- | --- |
| `backend_id` | 必填，已保存后端 ID |
| `request_id` | 必填，8–100 字符；重试沿用同一值，不同生成操作使用新值 |
| `positive` | 手动生成时必填非空字符串，最多 20000 字符 |
| `negative` | 字符串，默认空，最多 20000 字符 |
| `seed` | 整数 -1 或 0–9007199254740991；默认 -1 随机图像种子 |
| `count` | 每次数量，整数 1–10，默认 1 |
| `repetitions` | 生成次数，整数 1–10，默认 1 |
| `candidate` | 可选，候选生成参数，见候选章节；提供时每次重新抽取 |

一次请求创建 `count × repetitions` 个任务；工作流自身的 batch_size 可能使每个任务输出多张图。确定种子按任务递增，`next_seed` 为下次值；随机种子保持 -1。`candidate_result` 是最后一轮候选结果，`next_candidate` 为后续种子及帧序号；无候选参数时为 null。

相同 `request_id` 复用已创建结果，内容不一致会冲突。`202` 表示任务已入库，不代表生成完成；通过列表及 SSE 获取进度。批量取消仅影响生成页尚未执行的任务，保留漫游预取。单个取消通过任务服务处理，不保证能中断已开始的 GPU 计算。

### Job

主要字段：`id,request_id,backend_id,revision_id,status,positive,negative,seed,backend_prompt_id,error,created_at,updated_at`。列表还提供 `source`（`roam / generate`）、`backend_name,seed_applied`。不返回含密钥的配置快照。

状态为 `queued / submitting / running / completed / failed / unknown / cancelled`。`unknown` 表示提交或执行结果无法确认，不应据此直接重新提交同一生图操作。

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

分数持久缓存到图片信息；普通读取只补缺失缓存，不因每次学习而重算历史图片。主动 refresh 重算所选范围，更新 `refreshed_at`；普通读取不更新该时间。重置偏好会清除评分缓存。推荐暂不可用时仍可能展示已有缓存；刷新失败保留旧缓存，检查 `scoring_available,error`。详情见[评分缓存](issues/image-score-cache.md)。

## 用户偏好

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/recommendation/preferences` | `page` 默认 1；`all` 为 0 或 1，默认 0 | 偏好报告 |
| POST | `/api/recommendation/preferences/reset` | `{request_id,expected_reset_revision}` | `{request_id,reset_revision,reset_at}` |

报告字段：`available,error,feature_version,state_revision,reset_revision,reset_at,evidence_count,term_count,page,page_size,total_pages,terms`。每项 term 为 `{text,channel,weight,evidence_count}`；方向为 `positive / negative`，权重表示模型参数，不是概率。

默认每页 15 条；`all=1` 返回全部已学习词项，供前端导出 JSON，沿用同一接口。查看和导出不触发学习，不包含完整学习矩阵，无法用于恢复训练状态。只接受 page、all 查询参数。

重置 `request_id` 为 1–128 位字母、数字、下划线或横线，`expected_reset_revision` 使用最新报告值。重复请求可安全重试，修订冲突返回 409。重置清除学习状态及评分缓存，保留图片和评价，不把重置前的反馈自动重放为新学习。详见[用户偏好](issues/recommendation-preferences.md)和[导出](issues/preference-export.md)。

## 候选词库、预设与预览

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/candidate/tags` | `query`，`page=1`，`page_size=15`（1–200） | `{tags:[{id,name,post_count}],total,page,page_size}` |
| GET | `/api/candidate/dataset` | 无 | 数据状态、来源、修订、图片总数和 `tag_count` |
| GET | `/api/candidate/presets` | 无 | `{presets:[{id,name}]}` |
| GET | `/api/candidate/presets/{id}` | 无 | `{id,name,document}` |
| POST | `/api/candidate/presets` | `{name,document,id?}` | 保存后的 `{id,name,document}` |
| DELETE | `/api/candidate/presets/{id}` | `{}` | `{deleted:布尔值,id}` |
| POST | `/api/candidate/generate` | 候选生成参数 | 完整组合及报告 |
| POST | `/api/candidate/relations` | `{anchor,terms:[完整词项]}` | `{anchor:{text,known},relations:[{text,known,pmi,count}]}` |

词库只读，无添加、编辑、删除词库词项的 HTTP 接口。原名保留下划线，例如 black_hair；搜索支持空格等价匹配，按词频降序、同频名称排序。候选最终输出使用逗号分隔、空格连接词。

预设 POST 省略 id 创建，提供已有 id 更新。预设是可编辑的固定词和共现参数，不修改只读词库。

### 预设 document

| 字段 | 范围 | 默认 |
| --- | --- | --- |
| `base_positive` / `base_negative` | 完整词项字符串数组，允许自定义文本 | `[]` |
| `min_tags` | 整数 1–1000 | 5 |
| `max_tags` | 整数 min_tags–1000 | 20 |
| `pmi_threshold` | 有限数值 | 0 |
| `min_cooccurrence` | 正整数，最大安全整数 | 10 |
| `change_budget` | 整数 0–2000 | 2 |
| `blocked_keywords` | 关键词字符串数组 | `[]` |

固定正向词数不得超过 max_tags。新增正向词必须与已有词库正向词满足 PMI 和最低共现次数；自定义固定词无统计，不参与相关性门槛，负向词不参与正向扩展。关键词只过滤新抽取词，大小写不敏感，空格与下划线等价。

### 候选生成参数

| 字段 | 范围及默认 |
| --- | --- |
| `preset_id` | 必填，非空预设 ID |
| `mode` | `random_each_run / fixed_seed / sequence`，默认 random_each_run |
| `seed` | 整数 0–9007199254740991，默认 0，提示词种子 |
| `sequence_step` | 整数 0–1000，默认 0，仅 sequence 使用 |
| `max_steps` | 整数 1–1000000，省略时 100；所有模式的扩展搜索上限 |
| `seed_control` / `step_control` | `fixed / increment / decrement / randomize`，默认 fixed |
| `document` | 可选预设草稿，覆盖已保存预设内容 |

生成后控制用于任务多轮生成时推进下一轮参数；单次预览返回当前结果，不自动推进。random_each_run 每次生成新的提示词种子；图像种子在任务请求中单独设置。

响应包括 `positive,negative,seed,selected_tags,candidate_id,source_id,preset_id,mode,report`。selected_tags 每项含 `id,text,categories,channel,source_id`。`report` 为 `{stop_reason,tag_count,unrecognized_fixed}`；sequence 另有 `{seed,step,change_budget,changes}`。

目标长度在上下限内均匀抽取，共现不足或搜索上限到达时返回当前组合，不因未达到目标长度报错。stop_reason 可能为 `target_length,search_limit,no_eligible_tags,budget_zero`。数据未 ready 或参数无效仍返回错误。

Relations 仅查询当前词项关系，不创建生成任务；已知词对缺记录表示共现不足 10、未保留统计，pmi/count 为 null；自定义词 known=false，无统计。不能将 null 当作零共现或 PMI=0。统计口径见[PMI 数据设计](issues/candidate-pmi.md)。

## 调用示例

以下示例请求读取词库及预览提示词，不提交图片生成任务：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/tags?query=black_hair&page=1&page_size=15'

$preview = '{"preset_id":"default","mode":"fixed_seed","seed":42}'
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/generate' -Method Post `
  -ContentType 'application/json' -Body $preview
```

浏览器建立事件连接：

```javascript
const events = new EventSource('/api/events');
events.addEventListener('change', (event) => {
  const { topic, revision } = JSON.parse(event.data);
  // 根据 topic 重读相关资源；revision 用于识别本次通知。
});
```

## 实现与维护入口

- [HTTP 路由、请求解析及状态码](../backend/host.py)
- [应用编排与 HTTP 返回对象](../backend/application.py)
- [候选参数与结果](../backend/candidate/service.py)、[种子和序列参数](../backend/candidate/rounds.py)
- [推荐模块内部契约](../backend/contracts/recommendation.py)
- [任务存储与分页模型](../backend/store/sqlite.py)

本文是 HTTP 参考，不将模块内部的评分、学习等 Python 方法作为额外公开 HTTP 接口；当前没有 OpenAPI / Swagger 页面。新增、删除或调整路由时同步维护对应章节和导航。
