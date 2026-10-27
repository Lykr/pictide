# 生成任务

[English](../../../../dev/reference/api/jobs.md)

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

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
| `negative` | 字符串，默认空，最多 20000 字符；云端生图通道要求为空，自然语言模式先转换规避概念 |
| `seed` | 整数 -1 或 0–9007199254740991；默认 -1 随机图像种子；云端适配器只接受 -1，不发送图像种子 |
| `width` / `height` | 可选，须成对提供 1–16384 之间的整数像素；整批使用相同尺寸。两项均省略时沿用 API 固定尺寸。需要 `capabilities.dimensions`；ComfyUI 宽高须为 8 的倍数 |
| `count` | 每次数量，整数 1–10，默认 1 |
| `repetitions` | 生成次数，整数 1–10，默认 1 |
| `candidate` | 可选，候选生成参数，见候选章节；提供时每次重新抽取 |
| `preparation_id` | 未传 `candidate` 时，可提供已完成的自然语言预览 ID；标签与配置必须一致 |

一次请求创建 `count × repetitions` 个任务；工作流自身的 batch_size 可能使每个任务输出多张图。确定种子按任务递增，`next_seed` 为下次值；随机种子保持 -1。`candidate_result` 是最后一轮候选结果，`next_candidate` 为后续种子及帧序号；无候选参数时为 null。

相同 `request_id` 复用已创建结果，内容不一致会冲突。`202` 表示任务已入库，不代表生成完成；通过列表及 SSE 获取进度。批量取消仅影响生成页尚未执行的任务，保留漫游预取。单个取消通过任务服务处理，不保证能中断已开始的 GPU 计算。

自然语言后端的输入 `positive`/`negative` 表示原始概念，App 在提交图片任务前完成转换；生图 API 没有负向通道时，将规避要求融入正向文本。所有轮次准备成功后才提交整个批次。响应增加最后一轮的 `rendered`；使用候选时，`candidate_result.rendered` 含相同结果。同轮多张图片共享文本。使用同一请求 ID 明确重试时，继续已有准备或重放已提交批次。图片任务创建前的 LLM 阶段没有专用取消接口，中止 HTTP 请求不保证远端服务停止或免于计费。

### Job

主要字段：`id,request_id,backend_id,revision_id,status,positive,negative,seed,backend_prompt_id,error,created_at,updated_at`。任务还提供可空的 `width,height`，记录漫游选中或生成页指定的请求尺寸；null 沿用固定工作流/API 设置。画幅池修改、重启和提交恢复均不改变它们；这些值不包含工作流之后的放大处理。列表还提供 `source`（`roam / generate`）、`backend_name,backend_kind,seed_applied`。不返回含密钥的配置快照。

`positive`/`negative` 保存实际提交给生图服务的文本。自然语言任务、其产物及图片提示词接口另有 `source_prompts:{positive,negative}`，保存原始概念；旧记录和 Danbooru 记录省略该字段。锚点、标签筛选和历史反馈使用这些来源，不将描述句子解析为标签。

状态为 `queued / submitting / running / completed / failed / unknown / cancelled`。`unknown` 表示提交或执行结果无法确认，不应据此直接重新提交同一生图操作。本次 OpenAI Images 与 Gemini 接入没有远端恢复或取消能力；结果不确定的已发送请求不自动重发，本地取消不能保证服务商停止或免于计费。
