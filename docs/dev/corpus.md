# 数据处理

集中维护 Pictide 统计词库的离线下载、预处理和导入工具。处理流程为：下载 Parquet → 去重与词频统计 → 两两共现与 PMI → 成品 SQLite → 在应用中选择词库。

## 工具与数据位置

| 位置 | 用途 |
| --- | --- |
| `download.py` | 下载指定版本的完整 Parquet，保存 SQLite 清单并校验 SHA-256 |
| `importer.py` | 按图片 ID 去重，统计词频、评级、共现次数和 PMI，输出成品库 |
| `requirements.txt` | 离线处理依赖：PyArrow、SciPy、NumPy |
| `dev/datasets/danbooru-2026/` | 原始数据、下载清单、中间状态与待导入成品 |
| `dev/runtime/importer/` | 本机离线处理环境 |
| `data/libraries/` | 应用可选择的只读统计词库 |

工具从项目根目录以 Python 模块运行，独立于应用启动流程。源码安装步骤按系统阅读：[Windows](setup/windows.md#从源码准备) · [Linux](setup/linux.md#从源码准备) · [macOS](setup/macos.md#从源码准备)。下列命令中的 python 使用离线处理环境的解释器。

## 下载与导入

安装离线依赖：

```shell
python -m pip install -r corpus/requirements.txt
```

下载元数据，下载完成后输出固定的数据版本号；将该值填入导入命令的 REVISION：

```shell
python -m corpus.download dev/datasets/danbooru-2026
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/candidate.sqlite3 --revision REVISION
```

重新获取同一版本时，下载命令可加 `--revision REVISION`。导入成品使用新文件名；中间状态默认保存为成品文件名加 `-state.sqlite3`，也可用 `--state` 指定。中断后复用相同中间状态继续导入；各参数见两个模块的 `--help`。

## 统计口径

- 来源：Shio-Koube/Danbooru-2026-parquet-metadata，仅读取图片元数据。
- 普通标签取 tag_string_general，总出现次数至少 100；图片评级映射为 general / sensitive / questionable / explicit，并保留观察到的评级标签。
- 同一图片的同一标签计一次；所有图片累计后，基础成品保留共现至少 10 次的关系。
- PMI(a,b) = log2(共现次数 × 去重图片总数 / (a 的出现次数 × b 的出现次数))。
- 成品保存原始名称、词频、两两 PMI/次数和数据来源，dataset.min_cooccurrence 记录关系保留下限。

成品表结构见[存储参考](reference/storage.md#候选数据)。处理完成后，可通过[词库页面上传或选择](../guides/prompts.md#添加与切换词库)使用成品。

## 裁剪与历史处理记录

| 工作 | 说明与结果 |
| --- | --- |
| 词频筛选、评级、PMI 和关系门槛 | [PMI 处理记录](issues/candidate-pmi.md) |
| 共现至少 1,000 次的精简词库 | [裁剪口径、体积和生成验证](issues/candidate-pair1000.md) |
| 词库门槛随所选文件变化 | [词库最低共现次数](issues/library-cooccurrence-floor.md) |

裁剪从完整统计库的备份生成新文件，保留标签词频与原始 PMI，仅过滤关系并重建索引，更新 dataset.min_cooccurrence。历史一次性脚本和报告保存在 `dev/verification/candidate-pair1000-20261019/`；脚本中的路径与表结构反映当时环境。完整原始数据与中间统计保存在 `dev/datasets/`，供重新处理使用。

## 验证

导入冒烟使用临时 Parquet 与 SQLite，覆盖去重、评级、词频与关系门槛、PMI 和中断恢复：

```shell
python -m unittest discover -s tests/corpus -p test_importer.py -v
```

应用候选生成的验证入口见[候选冒烟](../../tests/candidate/README.md)。
