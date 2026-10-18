# PMI 候选数据与生成调整（已确认，保留共现次数）

## 架构

沿用 Host → Application → Candidate；推荐和任务接口不变。离线 importer 读取本地原始 Parquet，生成独立 SQLite 成品，再经备份/验证替换应用候选数据库。在线不运行导入。

统计阶段读取 tag_string_general 与图片 rating，按 post ID 全局去重、同一图片同一标签计一次。g/s/q/e 分别转换为 general/sensitive/questionable/explicit 并加入标签集合；普通标签保留 post_count >=100 的词，出现的评级强制保留。先完成全部图片的共现累计，再仅将 count >=10 的关系写入成品；不能逐批裁掉不足 10 次的局部计数。总样本 N 是全部去重图片数。未知或空评级报错，不静默丢弃图片。

## 数据流与存储

原始 Parquet → 离线去重/词频 → 普通标签频次至少 100 + 评级标签 → 全局两两计数 ≥10 → PMI → 应用成品 SQLite。

PMI(a,b) = log2(count(a,b) * N / (count(a) * count(b)))。

- tags(id INTEGER PRIMARY KEY, name TEXT UNIQUE, post_count INTEGER)：仅原始名称及图片频次，取消 text 和 category。
- correlations(tag_a INTEGER, tag_b INTEGER, pmi REAL, count INTEGER, PRIMARY KEY(tag_a,tag_b)) WITHOUT ROWID：tag_a < tag_b，一对只保存一次；保留正、零、负 PMI。共现不足 10 次的关系不建行。缺失行仅说明 count <10，不能推断零共现或具体 PMI，生成时排除；预览返回 PMI/count 均为 null。
- 成品库保留 PMI 和共现次数，不保留导入图片 ID、进度表或类别冲突表；这些属于 data 下独立的离线处理 SQLite。成品库继续保存必要数据来源、N、生成预设，业务主库的任务/图片/偏好保持原样。

## 接口与生成行为

- 词库 list_tags(query,page,page_size=15) 去掉 category；HTTP GET /api/candidate/tags 保留，响应标签仅 id/name/post_count，移除 categories/text/category。前端删除类别筛选和重复显示名称，直接展示原名。
- 固定词仍可自由输入，匹配时将空格形式转为原始下划线形式；最终生图提示词沿用空格连接词、逗号分隔标签，转换只在内存中进行，不存显示名称。
- 预设将 threshold 改为 pmi_threshold（默认 0，允许负数，不限定为 0–1）。保留 min_cooccurrence（新预设默认 10），用于排除高 PMI 但证据不足的偶然关系；数据层硬下限是 10，旧预设低于 10 的值仍保存但无法恢复已裁剪关系。
- storage.expansion_candidates(existing,pmi_threshold,min_cooccurrence) 要求新标签与每个已有可统计标签的 PMI 均达标且共现次数满足 min_cooccurrence；在达标候选中按 2 ** mean(PMI) 加权随机抽取，使负 PMI 也有有效正权重。无可统计锚点时仍按标签频次抽取起点。
- 查询优化仅在存储内部实现：先读取频次最少的已有标签的合格邻居，再用现有正反向索引分批检查剩余交集中的候选 ID，避免为后续标签读取整份邻居列表。保留标签遍历、PMI 求和及结果 ID 排序，不改变权重或随机种子结果；不新增索引、跨请求缓存或数据库结构。
- CandidateService.generate 的路由、候选完整组合输出和 CandidateProvider 接口不变；推荐输入保留现有标签快照结构，普通词 general、评级词 rating 类别可由候选服务赋值，不需要持久化类别。
- 保留固定正负词、数量上下限、随机/固定种子/连续模式、预算和计数控制。固定自由文本缺少统计时保留但不参与比较。
- 移除停止概率。独立生成先从 `[max(min_tags, 固定正向词数), max_tags]` 等概率抽取目标整数；整个搜索过程不重抽目标；无合格新词或 max_steps 用尽时返回当前有效组合，不重试凑满，也不降低共现门槛，实际数量可以低于 min_tags。连续帧从该区间与 `[上一帧数量 - change_budget, 上一帧数量 + change_budget]` 的交集抽取目标，并将替换计为两次变化；上一帧不足下限且预算无法一次达到下限时，先以预算可达的数量为目标。扩展不足时返回预算内已完成的组合，预算 0 保持上一帧。目标数均匀不等于受共现可行性或连续约束后的成品长度必然均匀。

## 实施与验证

先备份生产数据及预设，在独立数据库重建，不增加旧 schema 兼容层。旧预设阈值不能直接解释为 PMI，原预设保留于备份，新预设使用 PMI 参数。验证 general/100 频次边界、已知 PMI 算例/负值/缺失边、组合门槛、固定种子及连续预算；前端类型检查、构建和少量界面冒烟。报告成品库实际体积，需要重启前告知，不提交 GPU 出图任务。

离线命令保持以下入口，默认中间库为成品文件名加 -state.sqlite3，也可通过 --state 显式指定；成品要求新路径。可复用中间库恢复已完成的阶段和块，不扩展旧成品 schema。

```powershell
python -m pip install -r data_processing/requirements.txt
python -m data_processing.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/candidate.sqlite3 --revision 203df76a018bd5d463c37666c394b88b5acaa202
```

本次重建复用已验证的全量普通标签精确计数，从原始 Parquet 按相同 post ID 去重规则补算评级词频及评级与普通词的共现；校验每个普通词的四评级计数之和等于原词频。输出统一过滤 count >=10 并重算 PMI，原普通标签 ID 保持不变、追加四个评级 ID；新导入器以中性样例验证四评级、去重、100/99 词频与9/10关系边界。新库保留已有预设，切换前从在线库重读预设，避免覆盖处理期间的编辑。统计来源标识升级为 pmi-v2:general+ratings:min100:pair10，历史图片和推荐证据不重写。离线导入使用新的中间 state 文件，避免复用不含评级的旧计数。