# 独立发行资源与构建缓存

## 概述

便携构建独立准备词库与 MiniLM，有效缓存直接复用，缺失时自动下载并构建，全新检出可完成发行构建。

状态：待用户确认，尚未实现；替代现有打包时读取个人运行数据目录的方式。

## 架构

```mermaid
flowchart TD
    Build[scripts/build_portable.py] --> Prepare[发行资源准备]
    Profile[corpus/profiles/compact.json] --> Prepare
    Lock[固定数据集与模型来源版本] --> Prepare
    Dataset[dev/datasets：长期保留原始数据] --> Prepare
    Prepare --> Cache[dev/cache/portable：构建缓存]
    Prepare --> Download[corpus.download：下载并校验元数据]
    Download --> Dataset
    Prepare --> Import[corpus.importer：统计与导出词库]
    Dataset --> Import
    Cache --> Import
    Import --> Cache
    Prepare --> Model[下载并校验 MiniLM 固定快照]
    Model --> Cache
    Cache --> Seed[干净发行资源与清单]
    Seed --> Package[PyInstaller：releases 下的程序与压缩包]
```

## 职责边界

| 组成 | 接口及职责 |
| --- | --- |
| 便携构建脚本 | 原始数据默认使用已有 `dev/datasets/danbooru-2026/`，构建缓存使用 `dev/cache/portable/`；提供 `--dataset-dir PATH`、`--cache-dir PATH`、`--profile PATH` 与现有 `--output-dir PATH`。移除 `--source-data-dir`，不读取个人词库选择、图片、偏好、密钥或模型目录。前端构建仍沿用现有准备步骤。 |
| 发行资源准备 | 检查成品词库和模型缓存；命中直接导出，缺失或无效时准备对应资源。固定来源、版本与模型文件清单纳入源码。生成随包 `resources/` 和来源、参数及校验清单。 |
| `corpus.download` / `corpus.importer` | 继续负责元数据下载、断点与统计处理；原始分片及下载清单长期保留在 datasets，完整且版本匹配时从本地读取，仅补齐缺失分片。统计中间结果与成品放构建缓存。离线源码及其依赖留在 `corpus/`，首次构建依赖纳入开发构建环境，运行发行包无需安装数据处理依赖。 |
| 模型准备 | 按固定 MiniLM 快照下载现有编码器需要的五个文件；校验文件后缓存。只准备推荐模型，生图模型仍由用户选用的服务提供。 |
| 运行时资源初始化 | 继续使用包内种子，补齐用户所选数据目录中缺失的文件；不在应用启动时下载或统计原始数据。 |

目录布局：

```text
dev/datasets/danbooru-2026/          长期保留，复用当前已有目录
  raw/                              原始 Parquet
  download.sqlite3                  下载清单、版本、校验与断点记录

dev/cache/portable/                 可重建的构建缓存
  libraries/<fingerprint>/
    state.sqlite3                   统计中间结果与进度
    vocabulary.sqlite3              已完成的干净词库
    report.json                     来源、处理参数、数量及校验
  models/minilm/<model-revision>/    五个模型及 tokenizer 文件与校验记录
```

- 词库指纹包含源数据身份及固定版本、规范化后的配置、处理程序版本；配置或算法变化使用新缓存目录。
- 原始数据按清单记录的固定版本复用，保持现有分片路径；不为了接入新构建流程搬迁、复制或重新下载完整数据。版本不匹配时明确报错并允许通过 `--dataset-dir` 指定对应版本，不覆盖已有原始数据。
- 词库参数调整或清理构建缓存后，重新统计直接复用 datasets。完整且版本匹配的本地原始数据可离线重建词库；有效成品与模型缓存齐备时也不请求网络。
- 成品命中要求完成标记、匹配指纹及有效文件校验。未完成输出不作为可发布资源，保留可恢复的下载与统计进度。
- `dev/` 已被 Git 忽略；PyInstaller 的临时构建仍放 `dev/build/`，最终包继续放 `releases/`。原始数据目录和缓存目录可分别指向其他磁盘或 CI 持久目录，清理缓存不清理 datasets。

默认构建命令：

```shell
python scripts/build_portable.py
```

换用已有数据、共享缓存或其他规格：

```shell
python scripts/build_portable.py --dataset-dir DATASET_PATH --cache-dir CACHE_PATH --profile corpus/profiles/compact.json
```

## 调用和数据流

```mermaid
sequenceDiagram
    actor Dev as 开发者
    participant Build as 便携构建
    participant Cache as 发行缓存
    participant Dataset as 长期原始数据
    participant Source as 固定来源
    participant Corpus as 下载与统计处理
    participant Package as 发行包
    Dev->>Build: 执行构建命令
    Build->>Cache: 按固定来源、版本和配置检查资源
    alt 有效成品与模型缓存齐备
        Cache-->>Build: 返回已校验资源
    else 缺少词库成品
        Build->>Corpus: 从 datasets 检查固定版本原始数据
        Corpus->>Dataset: 读取已有清单并校验分片
        opt 缺少原始分片
            Corpus->>Source: 仅下载缺失分片，支持断点继续
            Corpus->>Dataset: 保存原始数据与清单
        end
        Dataset-->>Corpus: 复用匹配版本的原始数据
        Corpus->>Cache: 统计、保存进度并导出完成的词库
    end
    opt 缺少有效模型缓存
        Build->>Source: 下载并校验固定 MiniLM 文件
        Build->>Cache: 保存模型缓存
    end
    Build->>Package: 复制干净词库、模型与清单，完成打包
```

## 重点关注

- 默认精简规格沿用当前 `compact.json`：普通词最低出现 100 次，排除 `questionable` / `explicit` 标签，共现最低 1,000 次；评级对应的原始记录仍参与统计。
- 全新环境缺少原始数据时需要下载并完成统计；清空构建缓存但保留 datasets 时仅需重新统计。输出阶段进度并支持中断后继续。
- 不自动清理其他规格或旧版本缓存；开发者可单独管理 `dev/cache/portable/`，发行数据不与运行中的 `data/` 混用。
- 验证用小型中性数据与模拟下载覆盖首次下载、暖缓存零网络、清理缓存后复用原始数据、配置变化及损坏/中断缓存；保留原有便携初始化冒烟。全量真实数据处理与原生打包分别报告执行结果。
