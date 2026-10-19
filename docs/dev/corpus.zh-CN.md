# 数据处理

[English](corpus.md)

[开发文档](README.zh-CN.md) · [源码与依赖](../../corpus/README.zh-CN.md) · [运行存储](reference/storage.zh-CN.md#候选数据)

通过一条导入命令，将原始 Parquet 元数据处理为 Pictide 可直接使用的统计词库。通过排除标签、最低标签出现次数和最低标签共现次数，从同一份原始数据生成不同规模的词库。

## 文件与准备

| 位置 | 用途 |
| --- | --- |
| `corpus/download.py` | 可选的元数据下载器，固定版本并校验 SHA-256 |
| `corpus/importer.py` | 去重、词频、共现次数、PMI 与成品 SQLite 导出 |
| `corpus/profiles/compact.json` | 处理配置示例，可按数据集调整 |
| `corpus/requirements.txt` | 离线依赖：PyArrow、SciPy、NumPy |
| `dev/datasets/danbooru-2026/` | 原始文件、下载清单、中间状态、成品词库和报告 |
| `dev/runtime/importer/` | 本机离线处理环境 |
| `data/libraries/` | 应用中选择的只读统计词库 |

以下命令在项目根目录执行，`python` 使用离线处理环境的解释器。按系统准备环境：[Windows](setup/windows.md#从源码准备) · [Linux](setup/linux.md#从源码准备) · [macOS](setup/macos.md#从源码准备)，再安装依赖：

```shell
python -m pip install -r corpus/requirements.txt
```

导入器处理已有的本地文件；下载和安装环境分别执行。保留原始数据，每份成品使用 `dev/datasets/` 下的新路径，通过应用[上传或选择成品](../guides/prompts.zh-CN.md#添加与切换词库)。

## 一键处理

已有原始文件时，以下命令完成两遍统计并导出标准运行词库：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/candidate.sqlite3 --revision REVISION
```

将 `REVISION` 替换为下载时记录的源数据版本。默认保留至少出现在 100 个 post 中的普通标签，以及至少共现 10 次的标签关系。

精简配置保留至少出现 100 次的普通标签，排除 `questionable` 和 `explicit` 评级标签，关系至少共现 1,000 次：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact.sqlite3 --revision REVISION --exclude-tags questionable explicit --min-tag-occurrences 100 --min-cooccurrences 1000 --report dev/datasets/danbooru-2026/compact-report.json
```

也可以从精简配置读取相同设置：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact-profile.sqlite3 --revision REVISION --config corpus/profiles/compact.json
```

### 处理参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `raw` | 必填 | 递归查找 `*.parquet` 的目录，按路径排序处理 |
| `database` | 必填 | 新的成品 SQLite 路径；已有文件会被拒绝 |
| `--revision` | 必填 | 写入成品与状态的固定源数据版本 |
| `--source` | `Shio-Koube/Danbooru-2026-parquet-metadata` | 数据来源标识 |
| `--exclude-tags TAG [TAG ...]` | 空 | 要移除的精确原名；可重复传入该选项以增加名称 |
| `--min-tag-occurrences` | `100` | 普通标签的最低唯一 post 次数 |
| `--min-cooccurrences` | `10` | 成品关系的全局累计共现次数下限 |
| `--config` | 无 | JSON 对象，支持 `exclude_tags`、`min_tag_occurrences` 和 `min_cooccurrences` 中的任意项 |
| `--state` | 成品旁的 `<database-stem>-state.sqlite3` | 中间统计与断点进度 |
| `--block-size` | `256` | 每个共现计算块的标签列数；正整数 |
| `--batch-size` | `16384` | 每批读取的 Parquet 行数；正整数 |
| `--report` | 无 | 新 JSON 报告路径，与输入、状态和运行词库分开 |

两个频次门槛都接受 `1` 至 `9007199254740991`（2^53−1）的整数。JSON 配置格式如下：

```json
{
  "exclude_tags": ["questionable", "explicit"],
  "min_tag_occurrences": 100,
  "min_cooccurrences": 1000
}
```

显式 CLI 参数覆盖配置文件中的对应值。多次 `--exclude-tags` 合并 CLI 提供的名称，并用该列表替换配置中的 `exclude_tags`。名称精确匹配，保留下划线。排除规则同时作用于普通标签与评级标签。词频门槛只作用于普通标签：观察到的评级始终保留，除非显式排除。排除评级只移除对应标签及关系，该评级的 post 仍参与统计。配置调整后，需要重新构建词库和便携包才能应用。

例如，`--config corpus/profiles/compact.json --min-cooccurrences 2000` 沿用配置的标签筛选，只导出共现至少 2,000 次的关系。提高门槛通常减少体积与关系连通性，生成质量需结合实际效果判断。

## 原始输入结构

每个 Parquet 文件需提供以下列，其他列会被忽略：

| 列 | 值 | 含义 |
| --- | --- | --- |
| `id` | `int64`，非空 post ID | 跨文件、跨 row group 去重的身份 |
| `tag_string_general` | `string`，空白分隔的标签原名，或 null | 普通标签；null 视为空集合 |
| `rating` | `string`：`g`、`s`、`q` 或 `e` | 依次映射为 `general`、`sensitive`、`questionable`、`explicit` |

例如，`{"id": 123, "tag_string_general": "blue_hair outdoors blue_hair", "rating": "g"}` 对 `blue_hair`、`outdoors`、`general` 分别计数一次。不读取 artist、character、copyright、meta 标签列。未见过的或缺失的评级会使该唯一 post 的处理失败。

文件按路径排序，再按 row group 和行顺序读取。同一 `id` 保留首次记录，即使后续重复内容不同。全部唯一 post 都计入总体：排除标签、过滤低频词或使某个 post 没有保留标签，均不会删除该 post，也不会改变总体数量 `N`。

### 可选下载

下载器获取元数据，固定版本，并校验每个文件的字节数和 SHA-256：

```shell
python -m corpus.download dev/datasets/danbooru-2026
```

版本号在开始下载时输出。再次获取相同版本可加 `--revision REVISION`。原始分片保存在 `raw/` 下，并保留源目录层级。未完成下载使用 `.part` 文件，可继续下载。

`download.sqlite3` 保存一张清单表：

| 表 | 字段 | 含义 |
| --- | --- | --- |
| `files` | `name` 主键、`revision`、`size`、`sha256`、`completed` | 源相对路径、固定版本、预期字节数与摘要；校验通过后 `completed=1` |

## 统计与成品结构

处理分两遍：先统计去重 post 的标签词频，再统计保留标签的两两共现。每个标签在同一 post 中最多计数一次。关系门槛在全部 row group 的次数累计完成后应用。

对于不同的保留标签 `a`、`b`：

```text
PMI(a, b) = log2(pair_count(a, b) × N / (post_count(a) × post_count(b)))
```

`N` 是源数据去重 post 总数。提高共现门槛只移除关系，标签、词频和保留关系的 PMI 含义保持一致。缺少关系表示该统计未保留，应用不知道其精确次数。

成品数据库包含三张应用表，另有 SQLite 生成的索引统计：

| 表 | 字段 | 含义 |
| --- | --- | --- |
| `tags` | `id` | 整数主键，按原名排序分配 |
| | `name` | 唯一标签原名，保留下划线 |
| | `post_count` | 包含该标签的唯一 post 数量 |
| `correlations` | `tag_a`、`tag_b` | 复合主键，引用 `tags.id`；无序标签对仅存一次，满足 `tag_a < tag_b` |
| | `pmi` | 以 2 为底的 PMI |
| | `count` | 同时包含两个标签的唯一 post 数量 |
| `dataset` | `id` | 唯一一行，固定为 `1` |
| | `source`、`revision` | 来源标识与固定版本 |
| | `post_count` | 总体数量 `N` |
| | `status` | 成功导出后为 `ready` |
| | `min_cooccurrence` | 本次导出的关系次数下限；应用据此设置最低可选门槛 |

个人预设与当前词库选择保存在应用的独立个人数据库。原始记录、中间计数与进度留在成品之外。

CLI 在进度信息后打印 JSON 概览；加上 `--report` 后还会写入新文件，字段为 `source`、`revision`、`post_count`、`status`、`min_cooccurrence`、`tag_count`、`pair_count`、`min_tag_occurrences`、`exclude_tags`、`database`、`bytes`、`state`、`inputs`、`elapsed_seconds`。比较不同规格时可与词库一同保留报告；已有报告文件会被拒绝。

### 中间状态与复用

独立的状态数据库包含：

| 表 | 字段 | 含义 |
| --- | --- | --- |
| `source` | `source`、`revision` | 数据集身份 |
| `inputs` | `path` 主键、`bytes` | 复用时核对的绝对输入路径和字节数 |
| `processing` | `id`、`min_tag_occurrences`、`excluded_tags` | 单行保存影响标签集合与 ID 的配置；排除列表使用 JSON |
| `posts` | `id` 主键 | 词频阶段已提交的唯一 post |
| `frequencies` | `name` 主键、`count` | 每个标签的唯一 post 次数 |
| `groups` | `path`、`group_no`、`phase` 复合主键；`next_block`、`complete` | row group 进度；阶段 `1` 统计词频，阶段 `2` 统计共现 |
| `pair_posts` | `id` 主键 | 已完成共现 row group 中提交的唯一 post |
| `pair_counts` | `tag_a`、`tag_b` 复合主键；`count` | 应用导出门槛之前，保留标签间观察到的全部共现计数 |

统计中断后，用相同状态路径、原始文件、来源、版本、最低词频与排除集合继续处理；这些内容决定中间标签 ID 的含义。输入复用会核对路径和字节数，应保持已校验的原始文件不变。未记录处理参数的旧状态会被拒绝，请使用新的状态路径。

复用兼容状态时，可改变关系导出门槛、块大小和读取批大小。完整状态可直接导出不同共现门槛的成品，无需重新计算共现：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact-pair2000.sqlite3 --revision REVISION --config corpus/profiles/compact.json --min-cooccurrences 2000 --state dev/datasets/danbooru-2026/compact-state.sqlite3
```

此处复用前面显式生成 `compact.sqlite3` 示例的状态。改变词频门槛或排除集合需使用新状态。每次导出都使用新成品文件。导入器保留运行中的应用词库，处理完成后通过应用上传或选择。

## 验证与历史记录

导入冒烟使用临时 Parquet 与 SQLite，覆盖去重、评级、门槛、PMI、配置和恢复：

```shell
python -m unittest discover -s tests/corpus -p test_importer.py -v
```

应用侧验证入口见[候选冒烟](../../tests/candidate/README.md)。

| 记录 | 范围 |
| --- | --- |
| [PMI 处理](issues/candidate-pmi.md) | 最初的词频、评级、PMI 和关系门槛决策 |
| [精简词库](issues/candidate-pair1000.md) | 历史 1,000 次门槛、体积与生图验证 |
| [词库门槛](issues/library-cooccurrence-floor.md) | 应用根据所选词库下限工作的行为 |

历史一次性裁剪脚本和报告保存在 `dev/verification/candidate-pair1000-20261019/`，其中路径和结构对应当时运行。当前可重复处理统一使用上述导入器。
