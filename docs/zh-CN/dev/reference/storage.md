# SQLite 存储参考

[English](../../../dev/reference/storage.md)

[数据目录与职责](../data-layout.md) · [调用和数据流](../architecture/flows.md)

业务主库保存应用状态，个人预设库保存预设与词库选择，libraries 中的词库文件保存离线统计。这里记录当前归属和关联，不作为旧版本升级操作手册。

## 主库归属

| 表或表组 | 职责 |
| --- | --- |
| `backends` / `backend_revisions` | 当前配置入口与不可变历史快照 |
| `jobs` / `generation_batches` | 独立任务、批次幂等和执行上下文 |
| `artifacts` / `feedback` | 图片来源、隐藏/清理状态及 -1/1 反馈；撤回移除当前评价 |
| `pending_image_deletions` | 本地图片和 JSON 的持久回收队列 |
| `roam_*` | 观看位置、预取归属、设置、锚点与暂停状态 |
| `general_settings` | 主题、语言和切图动效 |
| `recommendation_*` | 模型向量、偏好参数、反馈证据与重置记录 |
| `artifact_preference_scores` / `recommendation_score_range` | 图片原始评分缓存、手动刷新时间与历史评分范围 |

## 漫游与历史快照

SQLite 在初始化时以 `CREATE TABLE IF NOT EXISTS` 增加漫游表，保留现有任务和图片：

| 表 | 数据 |
| --- | --- |
| `roam_jobs` | `job_id` 为主键并引用 `jobs`，另存 `epoch`、`candidate` JSON、`created_at`。候选 JSON 含 `candidate_id`、`preset_id`、`policy`、正负文本、`features` 和 `terms`；标签含来源、ID、当时文本/类目/方向及 `content_revision`。 |
| `roam_settings` | 预取数量、历史上限、后端/预设、方式、喜欢范围与 epoch。 |
| `roam_playback_settings` / `roam_candidate_settings` | 自动播放间隔与候选组合数量。 |
| `roam_recommendation_settings` / `roam_anchor_settings` | 推荐力度/强力倍数及 pinned_positive/preset_base_positive。 |
| `roam_runs` | `epoch` 为主键，`error` 为该版本暂停原因；存在记录即为暂停。 |
| `roam_view` | 单个本地用户的观看位置；`actor_id` 固定为 `local` 并为主键，`artifact_id` 可为空并引用 `artifacts`，`viewed_at` 是非负安全整数毫秒时间戳。仅严格较新的保存覆盖原值，防止请求乱序倒退。 |

任务与候选快照在同一数据库事务中保存；图片通过原有任务/产物关系关联，不扩展图片旁 JSON 内容。改变需要失效预取的设置或完整保存恢复暂停后使用新 epoch，旧任务和暂停记录保留，旧版本失败不会暂停新设置。

这些快照用于追溯实际生成时使用的标签文本、类目和身份，更新词库不改写历史快照。手动输入的提示词没有标签来源，不能以模糊匹配补造关联；是否可学习取决于快照完整性和推荐可用状态。备份时同时保留 SQLite 与 漫游设置。

观看位置不存入标签库、漫游设置 或浏览器 localStorage；喜欢和生成页的选图不会覆盖它，同一本地实例的浏览器共享这一位置。刷新或重启从数据库恢复；原图清理后，读取时优先返回最近较旧漫游图片，无较旧时返回最近较新图片，没有可用图则为空，保存时间戳保持不变。观看位置 API 与邻近图片窗口契约见 [架构说明](../architecture/flows.md#漫游预取与出图)。

## 生成批次与图片分区

生成批次与独立任务同存于 SQLite，不创建额外批次配置文件。初始化以 `CREATE TABLE IF NOT EXISTS` 增加 `generation_batches` 表：

| 字段 | 数据 |
| --- | --- |
| `request_id` | 文本主键，批次幂等请求 ID。 |
| `payload_hash` | 非空文本，规范化原始生成输入、规则及两种数量的内容校验值。 |
| `count` | 非空整数，本批工作流执行次数。 |
| `job_ids` | 非空文本，按批次顺序保存任务 ID 的 JSON 数组。 |
| `created_at` | 非空文本，批次创建时间。 |
| `context` | 可空文本，新计划的轮次数量、下次计数及最后一轮抽取结果 JSON，重试原样恢复。 |

批次和全部任务在同一事务中写入，网络重试按原请求 ID 找回原批次；每个任务继续引用提交时的后端修订，产物仍通过 `artifacts.job_id` 关联任务。

图片分区复用任务归属：存在 `roam_jobs` 关联的图片属于漫游，其余属于生成区。升级前的手动图片随查询自然归入生成区；不重写、搬移或删除已有图片与提示词 JSON，不改变反馈。喜欢跨来源保留图片，历史清理设置也同时适用于两类图片。

## 配置修订

选中的工作流使用固定 ID，编辑保存替换对应 JSON，并核对客户端读取的 `revision`。更新前和删除时将原始字节备份为 `workflows/.backups/<id>-<revision>.json`；备份不进入工作流选择列表。普通保存或数据库操作失败时恢复本次修改的工作流文件。需要恢复某个版本时，先停止应用，备份当前数据，再将目标备份复制到 `workflows/<id>.json`；使用文件内的 ID 作为文件名。恢复后的后端配置需重新选择并保存模板。

后端配置每次保存都建立不可变的 `backend_revisions` 记录，当前 `backends` 表只保存指向最新修订的入口。任务始终引用提交时的修订。删除后端仅删除这个入口，所有修订（包含 API Key）、任务、图片和评价仍在数据库中。可从 `backend_revisions` 中按原 `backend_id` 找到相应的 `config` 快照，通过后端保存用例恢复该配置；目前没有专用恢复界面。保存整个数据库可保留这些恢复来源，删除配置不等于擦除其中的密钥。

删除工作流会在同一数据库事务中为所有关联的当前后端建立解除引用的新修订，清除 `workflow_id`、`workflow_name` 和 `workflow_revision`，保留实际工作流、绑定、输出及密钥。历史任务引用的修订不修改。工作流更新仅应用于本次保存的后端，其他后端的快照保持原样。


## 推荐缓存与可撤回学习

推荐数据复用 `db/pictide.sqlite3`，不另建数据库：

| 表 | 用途 |
| --- | --- |
| `recommendation_vectors` | 模型/运行/预处理版本与标签文本对应的 float32 语义向量缓存 |
| `recommendation_policy` | 按用户、特征版本保存稳定内容键索引、float64 完整精度矩阵与累计反馈向量、修订及有效证据数 |
| `recommendation_events` | 喜欢/不喜欢/撤回状态变化的单调修订与实际生成组合快照；与反馈同事务写入 |
| `recommendation_resets` | 用户重置修订、时间和反馈事件水位，隔离重置前的学习事件 |
| `recommendation_reset_requests` | 重置请求的幂等结果，重试不会再次清除后来积累的偏好 |
| `recommendation_evidence` | 每用户、特征版本、图片的最新已应用证据，包含撤回状态，防止重复或乱序累计 |

App 的单个后台学习任务处理未应用的反馈记录，启动及后续操作唤醒处理，评分不等待本次学习；运行中编码器不可用时通知保留，图片喜欢正常保存。新特征版本可以重编码同一批历史实际文本与有效反馈；已重置用户仅处理重置水位之后的真实反馈变化，历史喜欢不重新导入；历史类目和标签库 ID 不作为学习身份。缺失或损坏的派生参数可从保留证据重建。模型资源位于 `models/minilm`，与可重新生成的缓存分别存放。源码与便携启动均在 HTTP 服务启动前按固定清单校验并补齐文件，完整有效文件离线复用，详见[模型启动准备](../../guides/getting-started.md#推荐依赖准备)；反馈与快照是恢复学习的依据，备份时应完整保留 SQLite。图片旁 JSON 不增加配置或学习数据。具体接口、特征和学习限制见 [推荐设计](../issues/recommendation-v1.md)。

## 图片评分缓存

图片原始均值分数、特征/策略版本和学习修订保存在 `artifact_preference_scores`；普通读取补缺失缓存，显式刷新重算所选范围。手动刷新时间保存在评分行的 refreshed_at，查询取其最大值；历史评分范围保存在 recommendation_score_range；重置偏好清除相应缓存。HTTP 返回和字段语义见[图片评分接口](api/images.md#喜欢筛选与图片偏好评分)，实现以[主库](../../../../backend/store/sqlite.py)为准。

## 候选数据

词库 dataset.min_cooccurrence 记录加工时的关系次数下限，随导入、上传和发行导出保留；编排与候选生成以它作为最低共现次数下限。基础库为 10，当前精简库为 1000。

`libraries/*.sqlite3` 中 tags 保存 `id,name,post_count`，correlations 保存无序标签对的 `pmi,count`，dataset 保存来源/状态。个人配置独立存放在 `db/candidate.sqlite3`：presets 保存可编辑预设，library_selection 保存当前词库文件名。上传仅导入统计表，个人预设始终沿用本地记录。没有重复保存显示名称或类别列；显示下划线原名，推荐/生图调用时转换为空格文本。

离线处理支持整条图片过滤、标签排除、普通标签词频门槛和关系共现门槛。整条图片过滤决定 PMI 总体，移除单个标签保留该总体。默认值、参数、字段与统计口径统一见[数据处理](../corpus.md#统计与成品结构)。精简配置的关系下限为 1,000，历史处理见[极限裁剪记录](../issues/candidate-pair1000.md)。缺记录表示统计未保留，具体次数未知。PMI 采用以 2 为底的对数。

原始 Parquet 位于项目根目录 `dev/datasets/danbooru-2026/raw/`，下载校验另存 download.sqlite3；导入去重 ID、临时计数和进度只在离线 SQLite 中，成品库不保留。更新统计库不重写主库历史任务或反馈。具体处理见[PMI 设计](../issues/candidate-pmi.md)和[共现候选记录](../issues/cooccurrence-candidates-v1.md)。
