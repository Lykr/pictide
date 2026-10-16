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
- POST /api/candidate/generate：预览完整组合；preset_id/mode/seed/sequence_step/max_steps/document（可选草稿）。
- CandidateProvider.generate(context,{count})：沿用 Sequence[Candidate]，完整正负文本和标签快照；推荐不读取词库或统计数据库。

生成请求沿用 candidate:{preset_id,mode,seed,sequence_step,seed_control,step_control,max_steps?}；每轮刷新组合，同轮共用文本。预设字段及存储接口见 [PMI 设计](candidate-pmi.md#接口与生成行为)。

## 离线导入

完整原始 Parquet 保留在 data/datasets，统计中间状态使用独立离线 SQLite，成品 candidate.sqlite3 不包含去重图片 ID 或导入进度。仅离线工具需要 requirements-import.txt，Web 不依赖 PyArrow/SciPy。CLI 与结果验证见 [PMI 设计](candidate-pmi.md#实施与验证)。

应用候选库更换前备份。状态 ready、导入进程退出且 WAL 已清空后才发布；不复制正在写入的库。旧预设原文件保留于备份，新版本不解释旧的概率阈值。任务、图片、喜欢和推荐证据保留。
