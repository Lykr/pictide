# 数据处理工具

[English](README.md)

离线元数据下载、可配置统计处理和依赖清单集中在本目录。已有原始 Parquet 时，通过一条命令生成 Pictide 运行词库：

```shell
python -m corpus.importer RAW NEW.sqlite3 --revision REVISION
```

默认在统计前整条排除包含 `questionable` 或 `explicit` 的图片数据，整条图片过滤与移除单个标签分别配置。环境准备、过滤参数、频次门槛、JSON 配置、数据结构与断点处理见[数据处理文档](../docs/dev/corpus.zh-CN.md)。导入器保留原始文件，生成新统计词库，供应用上传或选择。
