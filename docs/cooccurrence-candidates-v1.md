# 共现提示词候选

当前候选使用 general 标签、全量图片频次及两两 PMI，保留固定正负词、随机/固定种子/连续生成和变化预算。旧槽位、JSON 词库与条件概率阈值已退役。

## 1. 架构与边界

候选只提供完整提示词组合；Application 获取组合、调用推荐评分、选定组合后交给任务。候选、推荐、任务不直接交互。在线候选存储由 Host 注入；离线统计工具独立运行，不进入请求或启动链路。

## 2. 调用与数据流

完整原始 Parquet → 离线 general 词频及筛选 → 标签对计数与 PMI → 精简候选 SQLite。在线浏览器 → Host → Application → Candidate；推荐和生图都收到与最终输出一致的空格形式标签文本。

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

完整原始 Parquet 保留在 data/datasets，统计中间状态使用独立离线 SQLite，成品 candidate.sqlite3 不包含去重图片 ID 或导入进度。仅离线工具需要 requirements-import.txt，Web 不依赖 PyArrow/SciPy。CLI 与结果验证见 [PMI 设计](candidate-pmi.md#实施与验证)。

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
  "terms": ["gray eyes", "custom style", "forest"]
}
```

响应结构：

```json
{
  "anchor": {"text": "black hair", "known": true},
  "relations": [
    {"text": "gray eyes", "known": true, "pmi": 1.25, "count": 500},
    {"text": "custom style", "known": false, "pmi": null, "count": null},
    {"text": "forest", "known": true, "pmi": null, "count": 0}
  ]
}
```

数值仅为结构示例。两词都已知但没有关系行时表示零共现，PMI 数学上为负无穷，JSON 返回 null 并显示“无共同记录（0 次）”，不能显示 PMI 0。任一词未知时 PMI/count 均为 null；同一个标签不与自身比较，重复其他词按规范化标签去重。

Host 分派 `relations`；`Application.candidate(...)` 只做转发；`CandidateService.relations(anchor, terms)` 负责匹配及返回语义；`SQLiteCandidateStore` 内新增按锚点/其他标签 ID 查询关系的方法，沿用已有正反向索引。生成结果响应不新增字段。

### 界面

悬停词强调显示，其他词按正关联、负关联和无统计显示轻量颜色提示；浮层列出当前词与其他词的 PMI、共现次数，PMI 数值保留适量小数，仅展示时四舍五入。正/负 PMI 不等于协调/冲突结论。复用现有 shadcn 浮层与主题，支持键盘聚焦及触屏点按；加载、无统计、零共现、读取失败各自明确显示。

### 验证

少量中性样例验证双向查询、零共现与未知词的区别、自由词项完整性及悬停高亮；前端类型检查和构建，真实页面悬停/焦点检查。不提交生图任务。新增后端用例发布前需核对任务状态并告知重启。
