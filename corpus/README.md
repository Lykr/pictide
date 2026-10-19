# Corpus tools

[简体中文](README.zh-CN.md)

Offline metadata downloads, configurable statistics processing, and dependency manifests live here. From existing raw Parquet, run one command to build a Pictide runtime library:

```shell
python -m corpus.importer RAW NEW.sqlite3 --revision REVISION
```

By default, posts containing `questionable` or `explicit` are excluded before statistics. Whole-post filtering and removal of individual tags are configured separately. See [Corpus processing](../docs/dev/corpus.md) for setup, filtering options, frequency thresholds, JSON profiles, data structures, and resumable processing. The importer preserves raw files and writes a new statistical library for upload or selection in the application.

To export both `filtered` and `all-ratings` from the pinned source with one command, run `python scripts/export_vocabularies.py` from the project root. This prepares or reuses each profile's verified cache and exports separate SQLite files, reports, a manifest, and checksums; it keeps the default portable resource lock unchanged. See [edition exports](../docs/dev/corpus.md#export-both-vocabulary-editions) for publication and [Vocabulary editions](../docs/guides/vocabularies.md) for downloads and selection.
