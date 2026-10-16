# PMI 候选数据与生成调整（已确认，保留共现次数）

## 架构

沿用 Host → Application → Candidate；推荐和任务接口不变。离线 importer 读取本地原始 Parquet，生成独立 SQLite 成品，再经备份/验证替换应用候选数据库。在线不运行导入。

统计阶段仅读取 general 标签，按 post ID 全局去重、同一图片同一标签计一次。先统计总频次，保留 post_count >= 100 的标签，再统计这些标签间的共现；不额外按标签对次数或 PMI 裁剪。总样本 N 是全部去重图片数，包括没有保留标签的图片。

## 数据流与存储

原始 Parquet → 离线去重/词频 → general 且频次至少 100 → 两两计数 → PMI → 应用成品 SQLite。

PMI(a,b) = log2(count(a,b) * N / (count(a) * count(b)))。

- tags(id INTEGER PRIMARY KEY, name TEXT UNIQUE, post_count INTEGER)：仅原始名称及图片频次，取消 text 和 category。
- correlations(tag_a INTEGER, tag_b INTEGER, pmi REAL, count INTEGER, PRIMARY KEY(tag_a,tag_b)) WITHOUT ROWID：tag_a < tag_b，一对只保存一次；保留正、零、负 PMI。零共现不建行，查询语义为负无穷，不视为 0。
- 成品库保留 PMI 和共现次数，不保留导入图片 ID、进度表或类别冲突表；这些属于 data 下独立的离线处理 SQLite。成品库继续保存必要数据来源、N、生成预设，业务主库的任务/图片/偏好保持原样。

## 接口与生成行为

- 词库 list_tags(query,page,page_size=15) 去掉 category；HTTP GET /api/candidate/tags 保留，响应标签仅 id/name/post_count，移除 categories/text/category。前端删除类别筛选和重复显示名称，直接展示原名。
- 固定词仍可自由输入，匹配时将空格形式转为原始下划线形式；最终生图提示词沿用空格连接词、逗号分隔标签，转换只在内存中进行，不存显示名称。
- 预设将 threshold 改为 pmi_threshold（默认 0，允许负数，不限定为 0–1）。保留 min_cooccurrence（默认 5），用于排除高 PMI 但证据不足的偶然关系。
- storage.expansion_candidates(existing,pmi_threshold,min_cooccurrence) 要求新标签与每个已有可统计标签的 PMI 均达标且共现次数满足 min_cooccurrence；在达标候选中按 2 ** mean(PMI) 加权随机抽取，使负 PMI 也有有效正权重。无可统计锚点时仍按标签频次抽取起点。
- CandidateService.generate 的路由、候选完整组合输出和 CandidateProvider 接口不变；推荐输入保留现有标签快照结构，general 类别可由候选服务赋值，不需要持久化类别。
- 保留固定正负词、数量上下限、随机/固定种子/连续模式、预算和计数控制。固定自由文本缺少统计时保留但不参与比较。
- 移除停止概率。独立生成先从 `[max(min_tags, 固定正向词数), max_tags]` 等概率抽取目标整数；整个搜索过程不重抽目标，须精确达到目标，否则报错。连续帧从该区间与 `[上一帧数量 - change_budget, 上一帧数量 + change_budget]` 的交集抽取目标，并将替换计为两次变化；没有合法变化时保留上一帧。目标数均匀不等于受共现可行性或连续约束后的成品长度必然均匀。

## 实施与验证

先备份生产数据及预设，在独立数据库重建，不增加旧 schema 兼容层。旧预设阈值不能直接解释为 PMI，原预设保留于备份，新预设使用 PMI 参数。验证 general/100 频次边界、已知 PMI 算例/负值/缺失边、组合门槛、固定种子及连续预算；前端类型检查、构建和少量界面冒烟。报告成品库实际体积，需要重启前告知，不提交 GPU 出图任务。

离线命令保持以下入口，默认中间库为成品文件名加 -state.sqlite3，也可通过 --state 显式指定；成品要求新路径。可复用中间库恢复已完成的阶段和块，不扩展旧成品 schema。

```powershell
python -m pip install -r requirements-import.txt
python -m backend.candidate.importer data/datasets/danbooru-2026/raw data/import/candidate.sqlite3 --revision 203df76a018bd5d463c37666c394b88b5acaa202
```

本次完整数据复用原始全量精确计数，经相同 general/100 筛选与 PMI 计算重新导出成品；新 Parquet 入口以独立中性样例验证去重、100/99 边界、PMI 和空标签图片的分母。此导出是一次性离线处理，在线没有旧格式兼容逻辑。