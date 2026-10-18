# 数据目录

应用数据统一存放在一个目录。选择优先级为 `-DataDir` / `--data-dir` 参数、`PICTIDE_DATA_DIR` 环境变量、旧的 `PICTIDE_WEB_DATA_DIR` 环境变量、项目下的 `data/`。参数与环境变量指定整个目录，不单独指定数据库文件；旧变量仅用于保留现有自定义路径，新配置使用 `PICTIDE_DATA_DIR`。

```powershell
& '.\start.ps1' -Port 8189 -DataDir 'E:\PictideData'
```

```text
pictide/
  data/
    pictide.sqlite3        数据库，运行时可能同时存在 WAL / SHM
    history-cleanup.json   保留天数，未创建时默认 1 天（24 小时）
    candidate.sqlite3      原始标签名、词频、PMI/共现次数、生成预设及来源
    datasets/              完整 Parquet 导入素材与下载校验 SQLite
    import/                离线统计中间 SQLite 与待发布成品；在线不读取
    images/               图片与同名正负提示词 JSON
    prompts/              旧版标签库原文件，当前候选不再读取；发布前保留备份
    workflows/            命名的 API 工作流模板 JSON
      .backups/           更新前和删除的工作流，按 ID 与原修订号保存
    backups/              升级迁移备份
    previews/             预览与验证截图
    cache/
      embeddings/         离线 MiniLM 模型缓存
      python/             Python 字节码缓存
      pip/                Python 依赖下载缓存
      pnpm-store/         前端依赖包仓库
      pnpm/               前端下载缓存
      vite/               前端构建缓存
    logs/                 pictide.log，单文件 1 MiB，最多 3 份轮转备份
    tmp/                  本应用进程的临时文件
    runtime/
      venv/               Python 虚拟环境
      frontend/node_modules/ 前端开发依赖实体
  web/
    node_modules          指向上述依赖实体的 Junction
    dist/                 发布的静态资源，不是用户数据
```

启动脚本在导入应用前设置缓存和临时目录，首次启动在所选数据目录的 `runtime/venv` 创建环境并安装依赖，后续复用。迁移旧数据应先停止应用、备份后单独执行；启动脚本不会自动导入其他数据库。项目目录变动时应重建虚拟环境，避免 Windows 环境内的绝对路径失效。

后端通过 `backend.paths.DataPaths` 获取路径，`ensure()` 创建目录，`configure_runtime()` 配置本进程的临时文件、缓存和 `backend` 日志，不修改全局代理或 root logger。ComfyUI 的模型、环境、输入和输出目录仍由 ComfyUI 管理。

图片提示词 JSON 只保存实际提交的 `positive` 和 `negative`，不附带规则配置或 TXT。24 小时懒清理只处理本应用过期且未喜欢的图片及同名 JSON；数据库内的任务、反馈及幂等记录保留。具体触发、保护和重试行为见 [README](../README.md#历史图片清理)。

完整备份应先停止应用，再备份整个数据目录。数据库包含后端密钥，按含密钥文件保管。迁往其他目录或机器后，Python 虚拟环境可删除后由启动脚本重建；标签库、图片、数据库、工作流、清理与漫游设置保留。

## 生成结果清理

生成结果清理状态保存在 SQLite：`artifacts.generated_hidden_at` 标记移出生成页的喜欢图片，`deleted_at` 标记已清除的未喜欢图片；升级自动添加前者，不修改已有图像或反馈。全局产物修订同时包含删除与隐藏变化，刷新和重启不会重新显示已移出的结果。喜欢图片在 `source=generate` 列表中隐藏，原图、JSON 及喜欢列表仍可访问；未喜欢图片的文件通过原有安全待删除队列回收，保持路径与共享文件保护。任务、配置修订及幂等历史保留。用户操作语义见 [生成与图片来源](../README.md#生成与图片来源)。

## 喜欢状态升级

图片只有喜欢或未评价两种状态：`feedback` 表仅保存 `value=1` 的记录，撤回喜欢删除对应记录。升级首次启动时，在 SQLite 事务中重建旧反馈表，保留所有用户的喜欢记录及其时间；旧 `-1` 标记移除并按未评价处理，不删除对应图片、提示词、任务或候选快照。再次启动不会重复迁移。正负提示词属于生图文本，与此变更无关。

部署升级前先停止应用并备份 SQLite，保留可恢复的原反馈数据；日常完整备份仍按上述数据目录备份方式执行。未标记喜欢的图片继续遵循既有历史清理期限。

## 漫游设置与历史快照

主 SQLite 的 `roam_settings` 表保存 `prefetch_count`、`max_history_images`、`backend_id`、`preset_id` 和设置版本 `epoch`。未保存时默认关闭预取，保存生成新 epoch。表本身不启动后台投喂；旧 roam.json 保留在原始备份，新版本不读取或自动迁移。

数量清理只选择 `roam_jobs` 关联且严格早于已保存观看锚点、未删除且未隐藏的图片，喜欢与未喜欢都计入总量。当前和较新图片不计，无已保存锚点时不执行。在 SQLite 写事务中按 UTC 入库时间、ID 从早到晚处理超限部分：未喜欢的写入 `artifacts.deleted_at` 并通过安全队列回收本地图片及 JSON；任意用户喜欢的只写入 `artifacts.roam_hidden_at`，原文件、提示词与喜欢记录保留。隐藏状态在升级时增列，加入产物修订，漫游列表、分页、游标恢复、缓冲与计数均过滤隐藏图片，喜欢页仍可读取；不会将隐藏漫游图归入生成页。保留任务、候选快照、幂等记录及观看游标。具体使用和分批触发见 [README](../README.md#漫游缓冲)。

SQLite 在初始化时以 `CREATE TABLE IF NOT EXISTS` 增加漫游表，保留现有任务和图片：

| 表 | 数据 |
| --- | --- |
| `roam_jobs` | `job_id` 为主键并引用 `jobs`，另存 `epoch`、`candidate` JSON、`created_at`。候选 JSON 含 `candidate_id`、`preset_id`、`policy`、正负文本、`features` 和 `terms`；标签含来源、ID、当时文本/类目/方向及 `content_revision`。 |
| `roam_runs` | `epoch` 为主键，`error` 为该版本暂停原因；存在记录即为暂停。 |
| `roam_view` | 单个本地用户的观看位置；`actor_id` 固定为 `local` 并为主键，`artifact_id` 可为空并引用 `artifacts`，`viewed_at` 是非负安全整数毫秒时间戳。仅严格较新的保存覆盖原值，防止请求乱序倒退。 |

任务与候选快照在同一数据库事务中保存；图片通过原有任务/产物关系关联，不扩展图片旁 JSON 内容。显式保存设置后使用新 epoch，旧任务和暂停记录保留，旧版本失败不会暂停新设置。

这些快照用于追溯实际生成时使用的标签文本、类目和身份，修改、删除或禁用标签不改写历史快照。手动输入的提示词没有标签来源，不能以模糊匹配补造关联；快照入库也不代表已启用偏好训练。备份时同时保留 SQLite 与 漫游设置。

观看位置不存入标签库、漫游设置 或浏览器 localStorage；喜欢和生成页的选图不会覆盖它，同一本地实例的浏览器共享这一位置。刷新或重启从数据库恢复；原图清理后，读取时优先返回最近较旧漫游图片，无较旧时返回最近较新图片，没有可用图则为空，保存时间戳保持不变。观看位置 API 与邻近图片窗口契约见 [架构说明](architecture.md#漫游预取调用链)。

## 生成批次与图片分区

生成批次与独立任务同存于 SQLite，不创建额外批次配置文件。初始化以 `CREATE TABLE IF NOT EXISTS` 增加 `generation_batches` 表：

| 字段 | 数据 |
| --- | --- |
| `request_id` | 文本主键，批次幂等请求 ID。 |
| `payload_hash` | 非空文本，规范化原始生成输入、规则及两种数量的内容校验值。 |
| `count` | 非空整数，本批工作流执行次数。 |
| `job_ids` | 非空文本，按批次顺序保存任务 ID 的 JSON 数组。 |
| `created_at` | 非空文本，批次创建时间。 |
| `context` | 可空文本，新计划的轮次数量、下次计数及最后一轮抽取结果 JSON，重试原样恢复；升级只增列。 |

批次和全部任务在同一事务中写入，网络重试按原请求 ID 找回原批次；每个任务继续引用提交时的后端修订，产物仍通过 `artifacts.job_id` 关联任务。升级前单任务没有批次记录，数量为 `1` 的原请求仍可幂等找回。

图片分区复用任务归属：存在 `roam_jobs` 关联的图片属于漫游，其余属于生成区。升级前的手动图片随查询自然归入生成区；不重写、搬移或删除已有图片与提示词 JSON，不改变反馈。喜欢跨来源保留图片，历史清理设置也同时适用于两类图片。

## 配置编辑、删除与恢复

选中的工作流使用固定 ID，编辑保存替换对应 JSON，并核对客户端读取的 `revision`。更新前和删除时将原始字节备份为 `workflows/.backups/<id>-<revision>.json`；备份不进入工作流选择列表。普通保存或数据库操作失败时恢复本次修改的工作流文件。需要恢复某个版本时，先停止应用，备份当前数据，再将目标备份复制到 `workflows/<id>.json`；使用文件内的 ID 作为文件名。恢复后的后端配置需重新选择并保存模板。

后端配置每次保存都建立不可变的 `backend_revisions` 记录，当前 `backends` 表只保存指向最新修订的入口。任务始终引用提交时的修订。删除后端仅删除这个入口，所有修订（包含 API Key）、任务、图片和评价仍在数据库中。可从 `backend_revisions` 中按原 `backend_id` 找到最近的 `preset_id`，通过后端保存用例恢复该配置；目前没有专用恢复界面。保存整个数据库可保留这些恢复来源，删除配置不等于擦除其中的密钥。

删除工作流会在同一数据库事务中为所有关联的当前后端建立解除引用的新修订，清除 `workflow_id`、`workflow_name` 和 `workflow_revision`，保留实际工作流、绑定、输出及密钥。历史任务引用的修订不修改。工作流更新仅应用于本次保存的后端，其他后端的快照保持原样。

配置 API 通过应用编排调用存储，删除请求同样要求同源和 JSON：

| 请求 | 内容与结果 |
| --- | --- |
| `PUT /api/backends/{id}` | 选择已有模板时提交 `workflow_id`、`workflow_revision`、`workflow_name` 与图/绑定/输出；原 ID 更新。未带 ID 则新建或复用同名同内容模板。 |
| `DELETE /api/workflows/{id}` | JSON `{ "revision": "读取时的修订号" }`；修订冲突返回 409，不存在返回 404。成功返回 `deleted`、`id`、`detached_backends` 数量。 |
| `DELETE /api/backends/{id}` | JSON `{}`；仅移除配置入口。成功返回 `deleted`、`id`，不存在返回 404；不返回包含密钥的配置。 |

前端源码构建使用项目根目录的 `data/` 存放依赖及缓存，`web/node_modules` 为 Junction；`web/dist/` 是由 Vite 生成的可发布资源。正常启动不加载 Node.js。指定其他运行数据目录不会自动迁移源码构建环境。

## 推荐缓存与可撤回学习

推荐数据复用 `pictide.sqlite3`，不另建数据库：

| 表 | 用途 |
| --- | --- |
| `recommendation_vectors` | 模型/运行/预处理版本与标签文本对应的 float32 语义向量缓存 |
| `recommendation_policy` | 按用户、特征版本保存稳定内容键索引、float64 完整精度矩阵与累计反馈向量、修订及有效证据数 |
| `recommendation_events` | 喜欢/撤回状态变化的单调修订与实际生成组合快照；与反馈同事务写入 |
| `recommendation_resets` | 用户重置修订、时间和反馈事件水位，隔离重置前的学习事件 |
| `recommendation_reset_requests` | 重置请求的幂等结果，重试不会再次清除后来积累的偏好 |
| `recommendation_evidence` | 每用户、特征版本、图片的最新已应用证据，包含撤回状态，防止重复或乱序累计 |

启动和评分前由 App 重放未应用的最新通知；模型不可用时通知保留，图片喜欢正常保存。新特征版本可以重编码同一批历史实际文本与有效反馈；已重置用户仅处理重置水位之后的真实反馈变化，历史喜欢不重新导入；历史类目和标签库 ID 不作为学习身份。缺失或损坏的派生参数可从保留证据重建。模型缓存位于 `cache/embeddings`，可以重新准备；反馈与快照是恢复学习的依据，备份时应完整保留 SQLite。图片旁 JSON 不增加配置或学习数据。具体接口、特征和正向学习限制见 [推荐设计](issues/recommendation-v1.md)。

## 共现候选数据

`candidate.sqlite3` 保存原始下划线标签名、展示文本、Danbooru 类别、次数，无序标签对共现次数、数据集来源与处理状态以及可编辑命名预设。共现概率由计数计算，不重复保存。只读词库由离线导入工具生成；下载 Parquet 保留在 `datasets/danbooru-2026/raw/`，下载校验记录存于同目录上级的 download.sqlite3。运行时无需网络或 Parquet。

漫游缓冲、历史上限、后端与 preset_id 保存在主数据库 `roam_settings` 表中；新实现不读取旧 roam.json 或旧候选 JSON。发布前备份数据库、原词库和旧设置文件；不清空任务、图片、喜欢及推荐记录。新候选数据结构与接口见 [共现候选说明](issues/cooccurrence-candidates-v1.md)。

## PMI 候选库

候选成品只保留 general 且频次至少 100 的标签；tags 保存 id/name/post_count，correlations 保存无序标签对的 pmi/count，另有数据来源和预设。原名是词库显示内容，空格形式仅在推荐和生图调用时转换。导入去重 ID、进度和临时计数只在独立离线 SQLite 中，成品不保留。重建先备份旧 candidate.sqlite3，不做旧概率预设兼容；历史任务快照和推荐反馈仍在主库，保持原文本。完整规则见 [PMI 设计](issues/candidate-pmi.md)。

## 正负反馈表更新

不喜欢反馈发布前先停止应用并备份 `pictide.sqlite3`，再执行 `python -m backend.store.feedback_upgrade <数据库绝对路径>`。这是针对当前安装的一次性离线转换，将推荐事件与证据的 `liked` 转为 `value`（喜欢 1、撤回 null），并允许图片反馈 -1；保留已有点赞、策略参数、向量缓存、修订与重置分界。不在应用启动时执行。转换后使用对应新版代码启动；需要回退时恢复完整数据库备份与旧代码。见 [不喜欢反馈](issues/dislike-feedback.md)。

## 喜欢图片标签范围

`roam_settings.liked_tags_only` 为 0/1，默认 0；播放间隔与该开关复用同一设置行。当前安装发布前停止应用、备份主数据库，再离线执行 `ALTER TABLE roam_settings ADD COLUMN liked_tags_only INTEGER NOT NULL DEFAULT 0 CHECK(liked_tags_only IN (0,1))`。新建数据库直接包含该字段，不在启动时迁移；回退需恢复备份数据库与对应旧代码。喜欢图片的标签池按实际正向文本即时解析，不另存派生词库。接口与空池行为见 [喜欢图片标签漫游](issues/roam-liked-tags.md)。

## 漫游方式与预取失效

发布前停止应用并备份主库，离线增加 `roam_settings.prompt_mode TEXT NOT NULL DEFAULT 'random' CHECK(prompt_mode IN ('random','along','stay'))` 和 `roam_jobs.discarded_at TEXT`；新库直接包含，不在启动时迁移。前者保存漫游方式，后者保存未完成旧任务的失效时间。切换设置事务复用 `roam_hidden_at` 隐藏当前图之后的旧缓存，喜欢和图片文件保留；迟到产物入库时直接隐藏。顺流与停泊参考来自既有任务快照和观看位置，不新增状态表。完整接口见 [漫游方式](issues/roam-modes.md)。
