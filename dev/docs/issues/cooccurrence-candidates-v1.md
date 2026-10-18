# 共现提示词候选

当前候选使用普通 general 标签与四个图片评级标签、全量图片频次及保留关系的两两 PMI（基础导入至少 10 次，当前试用裁剪为至少 1,000 次），保留固定正负词、随机/固定种子/连续生成和变化预算。旧槽位、JSON 词库与条件概率阈值已退役。

## 1. 架构与边界

候选只提供完整提示词组合；Application 获取组合、调用推荐评分、选定组合后交给任务。候选、推荐、任务不直接交互。在线候选存储由 Host 注入；离线统计工具独立运行，不进入请求或启动链路。

## 2. 调用与数据流

完整原始 Parquet → 离线普通标签及评级词频、关系筛选 → 标签对计数与 PMI → 精简候选 SQLite。在线浏览器 → Host → Application → Candidate；推荐和生图都收到与最终输出一致的空格形式标签文本。

筛选、PMI 分母、成品结构、抽样和预算行为统一维护在 [PMI 候选设计](candidate-pmi.md)。

## 3. 接口

- GET /api/candidate/tags：只读原名词库，query/page/page_size，默认每页 15 条。
- GET /api/candidate/dataset：已导入数据状态及来源。
- GET /api/candidate/presets、GET /api/candidate/presets/{id}、POST /api/candidate/presets、DELETE /api/candidate/presets/{id}：命名预设。
- POST /api/candidate/relations：只读查询当前组合词项的两两相关性，详见下文预览悬停相关性。
- POST /api/candidate/generate：预览完整组合；preset_id/mode/seed/sequence_step/max_steps/document（可选草稿）。
- CandidateProvider.generate(context,{count})：沿用 Sequence[Candidate]，完整正负文本和标签快照；推荐不读取词库或统计数据库。

生成请求沿用 candidate:{preset_id,mode,seed,sequence_step,seed_control,step_control,max_steps?}；每轮刷新组合，同轮共用文本。预设字段及存储接口见 [PMI 设计](candidate-pmi.md#接口与生成行为)。

## 离线导入

完整原始 Parquet 保留在 data/datasets，统计中间状态使用独立离线 SQLite，成品 candidate.sqlite3 不包含去重图片 ID 或导入进度。仅离线工具需要 data_processing/requirements.txt，Web 不依赖 PyArrow/SciPy。CLI 与结果验证见 [PMI 设计](candidate-pmi.md#实施与验证)。

应用候选库更换前备份。状态 ready、导入进程退出且 WAL 已清空后才发布；不复制正在写入的库。旧预设原文件保留于备份，新版本不解释旧的概率阈值。任务、图片、喜欢和推荐证据保留。


## 预览悬停相关性（已确认并实现）

### 架构

沿用 Browser → Host → Application → CandidateService → SQLiteCandidateStore；不新增模块，不调用推荐或任务，不改生成和评分接口。新增候选模块的只读相关性查询用例。

### 调用与数据流

预览按 `selected_tags` 中的完整词项及正负向展示可悬停文本，保留顺序、逗号分隔和完整复制；不按字符串中的逗号拆分自由词项。

首次悬停或键盘聚焦一个词时，浏览器把该词及当前组合的其他词交给相关性查询。候选服务将空格形式匹配到原始下划线标签，用现有索引查询标签对；返回的 PMI 和共现次数由浏览器展示。仅查询当前组合，不检索全库相似词。每个预览结果在浏览器内按悬停词缓存，切换组合清空；不增加持久化缓存或写入数据库。

正负向都可查看数据集中的关联，正负方向不改变 PMI 数值；固定负向词仍不参与正向生成筛选。当前无匹配的自由文本保留展示，明确标记“无统计”。

### 接口

`POST /api/candidate/relations`，只读，不创建任务或保存配置。

请求：

```json
{
  "anchor": "black hair",
  "terms": ["blue eyes", "custom style", "forest"]
}
```

响应结构：

```json
{
  "anchor": {"text": "black hair", "known": true},
  "relations": [
    {"text": "blue eyes", "known": true, "pmi": 1.25, "count": 500},
    {"text": "custom style", "known": false, "pmi": null, "count": null},
    {"text": "forest", "known": true, "pmi": null, "count": null}
  ]
}
```

数值仅为结构示例。两词都已知但没有关系行时表示该关系的统计未保留，PMI/count 都返回 null，显示“未保留统计 / —”；不能显示零共现或 PMI 0。任一词未知时 PMI/count 均为 null；同一个标签不与自身比较，重复其他词按规范化标签去重。

Host 分派 `relations`；`Application.candidate(...)` 只做转发；`CandidateService.relations(anchor, terms)` 负责匹配及返回语义；`SQLiteCandidateStore` 内新增按锚点/其他标签 ID 查询关系的方法，沿用已有正反向索引。生成结果响应不新增字段。

### 界面

悬停词强调显示，其他词按正关联、负关联和无统计显示轻量颜色提示；浮层列出当前词与其他词的 PMI、共现次数，PMI 数值保留适量小数，仅展示时四舍五入。正/负 PMI 不等于协调/冲突结论。复用现有 shadcn 浮层与主题，支持键盘聚焦及触屏点按；加载、无统计、未保留关系、读取失败各自明确显示。

### 验证

少量中性样例验证双向查询、未保留关系与未知词的区别、自由词项完整性及悬停高亮；前端类型检查和构建，真实页面悬停/焦点检查。不提交生图任务。新增后端用例发布前需核对任务状态并告知重启。


## 候选池并行生成

完整组合之间独立计算，候选 provider 每批最多使用 4 个工作线程，仍按原种子 / 帧顺序返回组合；线程随批次结束释放。单组内部逐词检查 PMI，保持原抽取语义。单组合与直接 sequence 帧池保留串行，顺流的各候选都从同一个实际参考组合独立推进。候选、编排、推荐、任务的接口与调用关系不变，不新增配置项或后台服务。

以下为增量优化前的历史测量。真实只读词库对相同种子的 40 组候选交错测量两轮：串行平均 24.0 秒，2 线程 18.6 秒，4 线程 16.6 秒，4 线程约减少 31% 耗时。不同执行方式的完整输出指纹一致。3 项冒烟覆盖并发实际发生、固定种子顺序、连续帧回放、顺流预算及异常传播。仅测候选生成，不含推荐和生图；运行负载、缓存及具体组合会影响耗时。

改造后的真实 provider 另测：10 组 4.4 秒，40 组 17.5 秒；输出指纹与上述串行对照一致。实测记录保存在 data/verification/candidate-parallel-20261017/report.json。


### 批次准备与增量求交

同批共享预设、固定词和只读标签元数据，固定锚点的公共候选基集只计算一次；每组复制独立交集，加入新词时仅查询新词与剩余候选的合格关系。顺流删词时从基集和保留词重建，使原先受被删词限制的候选恢复。保持原锚点排序、浮点累加顺序、过滤与抽样顺序，完整固定种子快照不变。批次结束释放准备数据，不增加长期缓存、数据库结构或模块调用关系。

当前实现的对照结果与存储读接口见 [候选生成增量优化](candidate-generation-optimization.md#6-实施结果2026-10-17)。本次真实词库 10／40 组平均约 0.60／1.92 秒，相同条件下旧实现约 4.01／11.97 秒；不含推荐与生图。
