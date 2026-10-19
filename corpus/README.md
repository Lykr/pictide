# Corpus tools

[简体中文](README.zh-CN.md)

Offline metadata downloads, configurable statistics processing, and dependency manifests live here. From existing raw Parquet, run one command to build a Pictide runtime library:

```shell
python -m corpus.importer RAW NEW.sqlite3 --revision REVISION
```

See [Corpus processing](../docs/dev/corpus.md) for setup, tag exclusions, frequency thresholds, JSON profiles, data structures, and resumable processing. The importer preserves raw files and writes a new statistical library for upload or selection in the application.
