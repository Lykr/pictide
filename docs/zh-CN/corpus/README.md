# 数据处理工具

[English](../../../corpus/README.md)

离线元数据下载、可配置统计处理和依赖清单集中在本目录。已有原始 Parquet 时，通过一条命令生成 Pictide 运行词库：

```shell
python -m corpus.importer RAW NEW.sqlite3 --revision REVISION
```

默认在统计前整条排除包含 `questionable` 或 `explicit` 的图片数据，整条图片过滤与移除单个标签分别配置。环境准备、过滤参数、频次门槛、JSON 配置、数据结构与断点处理见[数据处理文档](../dev/corpus.md)。导入器保留原始文件，生成新统计词库，供应用上传或选择。

在项目根目录运行 `python scripts/export_vocabularies.py`，可从固定源版本一次导出 `filtered` 和 `all-ratings`。命令分别处理或复用各配置的已校验缓存，导出独立 SQLite、报告、清单和校验文件，保持默认便携资源锁不变。发布步骤见[两版导出](../dev/corpus.md#导出两版词库)，下载与选用见[词库版本](../guides/vocabularies.md)。
