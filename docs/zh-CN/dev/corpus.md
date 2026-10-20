# 数据处理

[English](../../dev/corpus.md)

[开发文档](README.md) · [源码与依赖](../corpus/README.md) · [运行存储](reference/storage.md#候选数据)

通过一条导入命令，将原始 Parquet 元数据处理为 Pictide 可直接使用的统计词库。通过整条图片数据过滤、标签排除、最低标签出现次数和最低标签共现次数，从同一份原始数据生成不同规模与统计总体的词库。

## 文件与准备

| 位置 | 用途 |
| --- | --- |
| `corpus/download.py` | 可选的元数据下载器，固定版本并校验 SHA-256 |
| `corpus/importer.py` | 去重、词频、共现次数、PMI 与成品 SQLite 导出 |
| `corpus/portable.py`、`corpus/resources.json` | 便携词库准备与固定源数据文件校验清单 |
| `scripts/prepare_vocabulary.py`、`corpus/prebuilt.json` | 导出发行词库并锁定可下载的资源文件 |
| `scripts/export_vocabularies.py` | 导出两版独立下载词库，保持便携资源锁不变 |
| `corpus/profiles/compact.json` | `filtered` 版与便携构建默认配置 |
| `corpus/profiles/all-ratings.json` | `all-ratings` 版，纳入全部源评级的图片数据 |
| `corpus/requirements.txt` | 离线依赖：PyArrow、SciPy、NumPy |
| `dev/datasets/danbooru-2026/` | 长期保留的原始文件和下载清单；手动处理示例也在此保存成品 |
| `dev/cache/portable/` | 便携构建统计中间状态、成品词库与报告 |
| `dev/runtime/importer/` | 本机离线处理环境 |
| `data/libraries/` | 应用中选择的只读统计词库 |

以下命令在项目根目录执行，`python` 使用离线处理环境的解释器。按系统准备环境：[Windows](setup/windows.md#从源码准备) · [Linux](setup/linux.md#从源码准备) · [macOS](setup/macos.md#从源码准备)，再安装依赖：

```shell
python -m pip install -r corpus/requirements.txt
```

导入器处理已有的本地文件；下载和安装环境分别执行。保留原始数据，每份成品使用 `dev/datasets/` 下的新路径，通过应用[上传或选择成品](../guides/prompts.md#添加与切换词库)。

## 便携构建资源

本地 `scripts/build_portable.py` 默认使用 `corpus/profiles/compact.json` 对应的 `filtered` 版，可处理原始数据，也可通过 `--prebuilt-library DIR` 复用已导出的词库。两种路径都使用独立构建环境，不读写开发应用的 `data/`。本机步骤见 [Windows](setup/windows.md#构建便携包)、[Linux](setup/linux.md#构建便携包) 或 [macOS](setup/macos.md#构建便携包)。

原始分片与 `download.sqlite3` 长期保存在 `dev/datasets/danbooru-2026/`；仅按固定源版本补齐缺失分片。统计中间结果与成品词库放在 `dev/cache/portable/`。清理构建缓存保留原始数据，可直接本地重新统计；有效词库缓存可离线准备发行词库。通过 `--dataset-dir`、`--cache-dir` 或 `--profile` 调整目录和处理配置。Corpus 只准备词库；MiniLM 改为[应用启动前准备](../guides/getting-started.md#推荐依赖准备)。指纹与文件校验规则见[构建缓存记录](issues/portable-build-cache.md)。下文保留其他词库规格的手动处理入口。

### 预构建词库

在本地准备一份词库，供各平台 GitHub Actions 构建共同使用。离线处理环境安装 `corpus/requirements.txt` 后执行：

```shell
python scripts/prepare_vocabulary.py
```

命令补齐固定版本的缺失原始分片，处理或复用已校验的词库缓存，再导出 `vocabulary.sqlite3` 与 `report.json`。默认导出目录是 `dev/cache/portable/exports/<fingerprint>/`。同时更新 Git 跟踪的 `corpus/prebuilt.json`，记录 `release_tag`、`fingerprint` 和每个导出文件的 `path`、`bytes`、`sha256`。通过 `--dataset-dir`、`--cache-dir`、`--profile` 或 `--output-dir` 可调整相应目录或处理配置。

报告保存源数据版本与校验信息、规范化处理参数、导入器代码摘要及生产时 NumPy/SciPy/PyArrow 版本。消费端核对源数据、配置和导入器是否匹配当前检出，并校验文件完整性及 SQLite 的就绪状态。生产依赖版本保留为来源记录，消费端无需安装或匹配这些处理依赖。

按准备脚本打印的 `gh release create` 命令上传两个文件。资源标签为 `corpus-<fingerprint>`，发布为 prerelease，并排除在最新应用版本之外；它不匹配应用的 `v*` 工作流触发规则。上传前先登录 GitHub CLI。已发布资源保持不变；词库变更使用新的资源 Release。上传成功后，再提交并推送生成的资源锁。

GitHub Actions 下载锁定的文件，将所在目录传给 `--prebuilt-library`。资源缺失、过期或损坏时构建终止，CI 不回退到原始数据统计；构建只携带 MiniLM 固定运行清单，不下载或打包模型文件。发行构建只安装 `backend/requirements-release.txt`，处理原始词库的机器才需要 PyArrow、SciPy 等离线依赖。版本标签要求与发版命令见 [GitHub Actions 发版](development.md#github-actions-发版)。

### 导出两版词库

为用户提供独立下载时，从仓库内的配置一次导出两版：

```shell
python scripts/export_vocabularies.py
```

命令分别为 `compact.json`（`filtered`）和 `all-ratings.json`（`all-ratings`）处理或复用已校验缓存。两版使用相同固定源数据，参数区别见[版本说明](../guides/vocabularies.md#选择版本)。只补齐缺失原始分片，长期保留在 `dev/datasets/danbooru-2026/`；统计与报告仍在 `dev/cache/portable/`。

默认导出目录为 `releases/vocabularies-<contentfingerprint12>/`，包含：

- `pictide-vocabulary-filtered.sqlite3` 与 `pictide-vocabulary-filtered.report.json`；
- `pictide-vocabulary-all-ratings.sqlite3` 与 `pictide-vocabulary-all-ratings.report.json`；
- `manifest.json` 与 `SHA256SUMS`。

通过 `--dataset-dir`、`--cache-dir` 或 `--output-dir` 可调整目录。命令只在本地导出，保持 `corpus/prebuilt.json` 不变，便携构建继续使用锁定的 `filtered` 资源。各版报告记录处理参数和来源，清单记录版本资产及其内容。

检查产物后，执行脚本打印的 `gh release create` 命令，以 `--prerelease --latest=false` 发布固定资源版本；上传前先登录 GitHub CLI。已发布资产保持不变，导出内容变化时使用新的内容指纹标签。本流程与前述默认 CI 资源锁准备分开，应用仍沿用 `v*` 标签发版。向用户提供两个 SQLite 资产的链接与[下载切换指南](../guides/vocabularies.md#下载与切换)。

## 一键处理

已有原始文件时，以下命令完成两遍统计并导出标准运行词库：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/candidate.sqlite3 --revision REVISION
```

将 `REVISION` 替换为下载时记录的源数据版本。默认整条排除包含 `questionable` 或 `explicit` 的图片数据，保留至少出现在 100 个保留 post 中的普通标签，以及至少共现 10 次的标签关系。

精简配置整条排除包含 `questionable` 或 `explicit` 的图片数据，不额外移除保留图片中的标签；普通标签至少出现在 100 个保留 post 中，关系至少共现 1,000 次：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact.sqlite3 --revision REVISION --exclude-posts-with-tags questionable explicit --min-tag-occurrences 100 --min-cooccurrences 1000 --report dev/datasets/danbooru-2026/compact-report.json
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
| `--exclude-posts-with-tags [TAG ...]` | `questionable explicit` | 原始标签集合命中任一指定名称时，整条排除该图片数据；只传选项、不传名称可关闭该过滤 |
| `--exclude-tags TAG [TAG ...]` | 空 | 要移除的精确原名；可重复传入该选项以增加名称 |
| `--min-tag-occurrences` | `100` | 普通标签的最低唯一 post 次数 |
| `--min-cooccurrences` | `10` | 成品关系的全局累计共现次数下限 |
| `--config` | 无 | JSON 对象，支持 `exclude_posts_with_tags`、`exclude_tags`、`min_tag_occurrences` 和 `min_cooccurrences` 中的任意项 |
| `--state` | 成品旁的 `<database-stem>-state.sqlite3` | 中间统计与断点进度 |
| `--block-size` | `256` | 每个共现计算块的标签列数；正整数 |
| `--batch-size` | `16384` | 每批读取的 Parquet 行数；正整数 |
| `--report` | 无 | 新 JSON 报告路径，与输入、状态和运行词库分开 |

两个频次门槛都接受 `1` 至 `9007199254740991`（2^53−1）的整数。JSON 配置格式如下：

```json
{
  "exclude_posts_with_tags": ["questionable", "explicit"],
  "exclude_tags": [],
  "min_tag_occurrences": 100,
  "min_cooccurrences": 1000
}
```

显式 CLI 参数覆盖配置文件中的对应值。两个排除选项均可重复传入，各自合并 CLI 提供的名称，再替换配置中的对应值或默认值。名称精确匹配，保留下划线。整条图片过滤匹配原始 `tag_string`、所有可用 `tag_string_*` 列和映射后的评级，发生在移除标签之前；单个标签排除只作用于参与统计的普通标签和评级。

`exclude_posts_with_tags` 将命中图片整条排除，该 post 不参与词频、共现与 PMI 总体。例如三张图片的标签分别是 `a b c`、`a c d`、`a e f`，传入 `--exclude-posts-with-tags b d` 后只统计第三张。`exclude_tags` 只移除指定标签及关系，图片仍计入总体。词频门槛只作用于普通标签：保留图片中观察到的评级始终保留，除非通过 `exclude_tags` 显式移除。

省略 `exclude_posts_with_tags` 时使用 `["questionable", "explicit"]`；显式空列表可关闭整条图片过滤。JSON 中使用 `"exclude_posts_with_tags": []`，Python 中使用 `exclude_posts_with_tags=[]`，CLI 则只传选项、不传名称。例如下列命令保留全部评级的图片数据，只移除两个评级标签：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/all-posts.sqlite3 --revision REVISION --exclude-posts-with-tags --exclude-tags questionable explicit
```

配置调整后，需要重新构建词库和便携包才能应用。规范化后的整条图片过滤条件与其他处理参数、导入器摘要一起参与便携构建缓存指纹；改变该条件会使用新的缓存目录。

例如，`--config corpus/profiles/compact.json --min-cooccurrences 2000` 沿用配置的标签筛选，只导出共现至少 2,000 次的关系。提高门槛通常减少体积与关系连通性，生成质量需结合实际效果判断。

## 原始输入结构

每个 Parquet 文件需提供以下列：

| 列 | 值 | 含义 |
| --- | --- | --- |
| `id` | `int64`，非空 post ID | 跨文件、跨 row group 去重的身份 |
| `tag_string_general` | `string`，空白分隔的标签原名，或 null | 普通标签；null 视为空集合 |
| `rating` | `string`：`g`、`s`、`q` 或 `e` | 依次映射为 `general`、`sensitive`、`questionable`、`explicit` |

例如，`{"id": 123, "tag_string_general": "blue_hair outdoors blue_hair", "rating": "g"}` 对 `blue_hair`、`outdoors`、`general` 分别计数一次。可选的 `tag_string` 和 `tag_string_*` 列，包括 artist、character、copyright、meta 标签，仅参与整条图片过滤，不增加统计与成品词库的标签类别；缺少这些可选列仍可正常处理。其他列会被忽略。未见过的或缺失的评级会使该唯一 post 的处理失败。

文件按路径排序，再按 row group 和行顺序读取。同一 `id` 保留首次记录，即使后续重复内容不同。整条图片过滤以首次记录为准；被排除的 ID 仍标记为已见，后续重复记录不能重新进入统计。过滤匹配全部可用原始标签列及映射后的评级，统计仍只使用普通标签与评级。移除单个标签、过滤低频词或使某个保留 post 没有保留标签，均不会删除该 post，也不会改变总体数量 `N`。

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

处理分两遍：先统计保留的去重 post 的标签词频，再统计同一批 post 中保留标签的两两共现。每个标签在同一 post 中最多计数一次。关系门槛在全部 row group 的次数累计完成后应用。

对于不同的保留标签 `a`、`b`：

```text
PMI(a, b) = log2(pair_count(a, b) × N / (post_count(a) × post_count(b)))
```

`N` 是整条图片过滤后保留的唯一 post 数。被排除图片对词频和共现均无贡献。提高共现门槛只移除关系，标签、词频和保留关系的 PMI 含义保持一致。缺少关系表示该统计未保留，应用不知道其精确次数。

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

CLI 在进度信息后打印 JSON 概览；加上 `--report` 后还会写入新文件，字段为 `source`、`revision`、`source_post_count`、`excluded_post_count`、`post_count`、`status`、`min_cooccurrence`、`tag_count`、`pair_count`、`min_tag_occurrences`、`exclude_posts_with_tags`、`exclude_tags`、`database`、`bytes`、`state`、`inputs`、`elapsed_seconds`。`source_post_count` 为整条过滤前的唯一源 ID 数，`excluded_post_count` 为排除的唯一 post 数，`post_count` 为保留总体 `N`，满足 `source_post_count = excluded_post_count + post_count`。比较不同规格时可与词库一同保留报告；已有报告文件会被拒绝。

### 中间状态与复用

独立的状态数据库包含：

| 表 | 字段 | 含义 |
| --- | --- | --- |
| `source` | `source`、`revision` | 数据集身份 |
| `inputs` | `path` 主键、`bytes` | 复用时核对的绝对输入路径和字节数 |
| `processing` | `id`、`min_tag_occurrences`、`excluded_tags`、`excluded_post_tags` | 单行保存影响总体、标签集合与 ID 的配置；两类排除列表使用 JSON |
| `posts` | `id` 主键、`included` | 词频阶段已提交的全部首次出现 ID；`included=1` 参与统计，`0` 被排除但仍标记已见 |
| `frequencies` | `name` 主键、`count` | 每个标签的唯一 post 次数 |
| `groups` | `path`、`group_no`、`phase` 复合主键；`next_block`、`complete` | row group 进度；阶段 `1` 统计词频，阶段 `2` 统计共现 |
| `pair_posts` | `id` 主键 | 已完成共现 row group 中扫描的全部首次出现 ID，包含被排除图片；仅保留图片进入共现矩阵 |
| `pair_counts` | `tag_a`、`tag_b` 复合主键；`count` | 应用导出门槛之前，保留标签间观察到的全部共现计数 |

统计中断后，用相同状态路径、原始文件、来源、版本、最低词频与两类排除集合继续处理；这些内容决定统计总体与中间标签 ID 的含义。输入复用会核对路径和字节数，应保持已校验的原始文件不变。缺少整条图片过滤配置或保留标记字段的旧状态会被拒绝，请使用新的状态路径；不迁移旧状态。

复用兼容状态时，可改变关系导出门槛、块大小和读取批大小。完整状态可直接导出不同共现门槛的成品，无需重新计算共现：

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact-pair2000.sqlite3 --revision REVISION --config corpus/profiles/compact.json --min-cooccurrences 2000 --state dev/datasets/danbooru-2026/compact-state.sqlite3
```

此处复用前面显式生成 `compact.sqlite3` 示例的状态。改变词频门槛、标签排除或整条图片排除集合需使用新状态。每次导出都使用新成品文件。导入器保留运行中的应用词库，处理完成后通过应用上传或选择。

## 验证与历史记录

导入冒烟使用临时 Parquet 与 SQLite，覆盖去重、整条图片过滤、评级、门槛、PMI、配置和恢复：

```shell
python -m unittest discover -s tests/corpus -p test_importer.py -v
```

应用侧验证入口见[候选冒烟](../tests/candidate/README.md)。

| 记录 | 范围 |
| --- | --- |
| [PMI 处理](issues/candidate-pmi.md) | 最初的词频、评级、PMI 和关系门槛决策 |
| [精简词库](issues/candidate-pair1000.md) | 历史 1,000 次门槛、体积与生图验证 |
| [词库门槛](issues/library-cooccurrence-floor.md) | 应用根据所选词库下限工作的行为 |

历史一次性裁剪脚本和报告保存在 `dev/verification/candidate-pair1000-20261019/`，其中路径和结构对应当时运行。当前可重复处理统一使用上述导入器。
