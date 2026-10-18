# 候选词库与预设

[API 索引](../../api.md) · [通用约定与错误](../../api.md#通用约定)

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

Relations 仅查询当前词项关系，不创建生成任务；已知词对缺记录表示共现不足 10、未保留统计，pmi/count 为 null；自定义词 known=false，无统计。不能将 null 当作零共现或 PMI=0。统计口径见[PMI 数据设计](../../issues/candidate-pmi.md)。
