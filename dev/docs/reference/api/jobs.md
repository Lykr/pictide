# 生成任务

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
