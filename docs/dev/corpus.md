# Corpus Processing

[简体中文](corpus.zh-CN.md)

[Developer documentation](README.md) · [Source and dependencies](../../corpus/README.md) · [Runtime storage](reference/storage.md#candidate-data)

Produce a ready-to-use Pictide statistical library from raw Parquet metadata with one importer command. Parameters control excluded tags, minimum tag frequency, and minimum pair frequency, so the same source can produce libraries of different sizes.

## Files and preparation

| Location | Purpose |
| --- | --- |
| `corpus/download.py` | Optional metadata downloader with a pinned revision and SHA-256 verification |
| `corpus/importer.py` | Deduplication, tag counts, pair counts, PMI, and finished SQLite export |
| `corpus/portable.py`, `corpus/resources.json` | Portable resource preparation and pinned source/model file checksums |
| `scripts/prepare_vocabulary.py`, `corpus/prebuilt.json` | Export a release vocabulary and lock its downloadable files |
| `corpus/profiles/compact.json` | Default portable-build profile; also usable for manual processing |
| `corpus/requirements.txt` | Offline dependencies: PyArrow, SciPy, and NumPy |
| `dev/datasets/danbooru-2026/` | Long-lived raw files and download manifest; manual processing examples also write outputs here |
| `dev/cache/portable/` | Portable-build intermediate state, completed libraries, and reports |
| `dev/models/minilm/<model-revision>/` | Long-lived pinned recommendation model and tokenizer files |
| `dev/runtime/importer/` | Local offline processing environment |
| `data/libraries/` | Read-only libraries selected by the application |

Run commands from the project root using the Python interpreter of the offline processing environment. Prepare that environment using the instructions for [Windows (Chinese)](setup/windows.md#从源码准备), [Linux (Chinese)](setup/linux.md#从源码准备), or [macOS (Chinese)](setup/macos.md#从源码准备), then install dependencies:

```shell
python -m pip install -r corpus/requirements.txt
```

The importer processes existing local files. Downloading and environment installation are separate steps. Preserve raw data and write each finished library to a new path under `dev/datasets/`; use the application to [upload or select the result](../guides/prompts.md#add-and-switch-libraries).

## Portable build resources

Local `scripts/build_portable.py` builds can prepare the compact library from raw data, or consume an exported library with `--prebuilt-library DIR`. Both use a separate builder environment and stay independent of the development application's `data/`. See the native build instructions for [Windows (Chinese)](setup/windows.md#构建便携包), [Linux (Chinese)](setup/linux.md#构建便携包), or [macOS (Chinese)](setup/macos.md#构建便携包).

Raw shards and `download.sqlite3` remain in `dev/datasets/danbooru-2026/`. Missing shards are downloaded at the pinned source revision; statistics and completed libraries go to `dev/cache/portable/`, while pinned MiniLM files remain in `dev/models/minilm/<model-revision>/`. Clearing the build cache preserves raw data and model files for local recomputation. Valid library and model files allow a build without network requests. Change `--dataset-dir`, `--cache-dir`, `--models-dir` (default: `dev/models/`), or `--profile` to use other locations or processing settings. The [build cache record (Chinese)](issues/portable-build-cache.md) defines fingerprints and file verification. Manual processing below remains available for other library specifications.

### Prebuilt vocabulary

Prepare one vocabulary locally and reuse it across native GitHub Actions builds. In the offline processing environment, with `corpus/requirements.txt` installed, run:

```shell
python scripts/prepare_vocabulary.py
```

The command downloads missing pinned raw shards, processes them or reuses a verified library cache, then exports `vocabulary.sqlite3` and `report.json`. The default export directory is `dev/cache/portable/exports/<fingerprint>/`. It also updates the tracked `corpus/prebuilt.json` resource lock with `release_tag`, `fingerprint`, and each exported file's `path`, `bytes`, and `sha256`. Use `--dataset-dir`, `--cache-dir`, `--profile`, or `--output-dir` to change the corresponding locations or processing profile.

The report records the source revision and checksums, normalized processing parameters, importer code hash, and producer NumPy/SciPy/PyArrow versions. Consumers verify that the source, profile, and importer match the checkout, and check file integrity and the ready SQLite database. Producer dependency versions remain provenance; the consumer need not install the processing dependencies or reproduce their versions.

Upload both files using the `gh release create` command printed by the preparation script. The resource tag is `corpus-<fingerprint>`; it is a prerelease excluded from the latest application release and does not match the application's `v*` workflow trigger. Authenticate GitHub CLI before uploading. Keep published resource assets unchanged; a changed vocabulary gets a new resource release. Commit and push the resulting resource lock after the upload succeeds.

GitHub Actions downloads the exact locked files and passes their directory through `--prebuilt-library`. A missing, outdated, or damaged resource stops the build; CI never falls back to processing the raw dataset. MiniLM is still downloaded separately at its pinned revision. Release builders install `backend/requirements-release.txt`; PyArrow and SciPy are needed only on machines preparing raw vocabulary data. For tag/version requirements and release commands, see [GitHub Actions releases (Chinese)](development.md#github-actions-发版).

## One-command processing

With raw files already available, this command runs both statistical passes and exports the standard runtime library:

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/candidate.sqlite3 --revision REVISION
```

Replace `REVISION` with the source revision recorded during download. Defaults are 100 posts per ordinary tag and 10 co-occurrences per pair.

The compact profile retains ordinary tags occurring in at least 100 posts, excludes the `questionable` and `explicit` rating labels, and retains pairs occurring in at least 1,000 posts:

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact.sqlite3 --revision REVISION --exclude-tags questionable explicit --min-tag-occurrences 100 --min-cooccurrences 1000 --report dev/datasets/danbooru-2026/compact-report.json
```

Load these settings from the compact profile:

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact-profile.sqlite3 --revision REVISION --config corpus/profiles/compact.json
```

### Processing parameters

| Argument | Default | Meaning |
| --- | --- | --- |
| `raw` | Required | Directory searched recursively for `*.parquet`, processed in sorted path order |
| `database` | Required | New finished SQLite path; an existing file is rejected |
| `--revision` | Required | Pinned source revision recorded in the result and state |
| `--source` | `Shio-Koube/Danbooru-2026-parquet-metadata` | Source identifier |
| `--exclude-tags TAG [TAG ...]` | Empty | Exact original tag names to remove; repeat the option for more names |
| `--min-tag-occurrences` | `100` | Minimum unique-post count for an ordinary tag |
| `--min-cooccurrences` | `10` | Minimum globally accumulated pair count in the finished library |
| `--config` | None | JSON object with any of `exclude_tags`, `min_tag_occurrences`, and `min_cooccurrences` |
| `--state` | `<database-stem>-state.sqlite3` beside the output | Intermediate statistics and resumable progress |
| `--block-size` | `256` | Tag columns per pair-computation block; positive integer |
| `--batch-size` | `16384` | Parquet rows read per batch; positive integer |
| `--report` | None | New JSON report path, separate from inputs, state, and runtime library |

Both frequency thresholds accept integers from `1` through `9007199254740991` (2^53−1). A JSON configuration has this form:

```json
{
  "exclude_tags": ["questionable", "explicit"],
  "min_tag_occurrences": 100,
  "min_cooccurrences": 1000
}
```

Explicit CLI options override corresponding configuration values. Repeated `--exclude-tags` options combine CLI names; that list replaces the configuration's `exclude_tags`. Names match exactly, including underscores. Exclusions apply to ordinary tags and rating labels. The frequency threshold applies only to ordinary tags: every observed rating is retained unless explicitly excluded. Excluding a rating removes its label and relationships, while posts with that rating still contribute to the statistics. Existing libraries and portable packages need to be rebuilt to use a changed profile.

For example, `--config corpus/profiles/compact.json --min-cooccurrences 2000` keeps the profile's tag selection while exporting pairs with at least 2,000 co-occurrences. Larger thresholds usually reduce size and connectivity; generation quality needs separate evaluation.

## Raw input structure

Each Parquet file must provide these columns; other columns are ignored:

| Column | Value | Interpretation |
| --- | --- | --- |
| `id` | `int64`, non-null post ID | Deduplication identity across all files and row groups |
| `tag_string_general` | `string`, whitespace-separated original names, or null | Ordinary tags; null is an empty set |
| `rating` | `string`: `g`, `s`, `q`, or `e` | Maps to `general`, `sensitive`, `questionable`, or `explicit` |

For example, `{"id": 123, "tag_string_general": "blue_hair outdoors blue_hair", "rating": "g"}` contributes once each to `blue_hair`, `outdoors`, and `general`. Artist, character, copyright, and meta tag columns are not read. Unknown or missing ratings fail processing for a unique post.

Files are sorted by path, then read in row-group and row order. The first record for each `id` wins, including when duplicates disagree. All unique posts remain in the population: excluding a tag, removing a rare tag, or leaving a post with no retained tags does not remove that post or change population size `N`.

### Optional download

The downloader fetches metadata, pins a revision, and verifies each file's byte size and SHA-256:

```shell
python -m corpus.download dev/datasets/danbooru-2026
```

The revision is printed at download start. To fetch the same revision later, add `--revision REVISION`. Raw shards remain below `raw/`, preserving source subdirectories. Partial downloads use `.part` files and support continuation.

`download.sqlite3` stores one manifest table:

| Table | Fields | Meaning |
| --- | --- | --- |
| `files` | `name` primary key, `revision`, `size`, `sha256`, `completed` | Source-relative path, pinned revision, expected bytes and digest; `completed=1` after verification |

## Statistics and output structure

Processing has two passes: count tags across unique posts, then count pairs among retained tags. A tag contributes at most once per post. Pair thresholds apply after counts from all row groups have accumulated.

For distinct retained tags `a` and `b`:

```text
PMI(a, b) = log2(pair_count(a, b) × N / (post_count(a) × post_count(b)))
```

`N` is the total unique source posts. Raising the pair threshold only drops relationships: retained tags, their frequencies, and surviving PMI values keep the same meaning. A missing relationship means its statistic was not retained; its exact count is unknown to the application.

The finished database contains three application tables, plus SQLite-generated index statistics:

| Table | Field | Meaning |
| --- | --- | --- |
| `tags` | `id` | Integer primary key, assigned from original names in sorted order |
| | `name` | Unique original tag name, including underscores |
| | `post_count` | Unique posts containing this tag |
| `correlations` | `tag_a`, `tag_b` | Composite primary key referencing `tags.id`; each unordered pair stored once with `tag_a < tag_b` |
| | `pmi` | Base-2 PMI |
| | `count` | Unique posts containing both tags |
| `dataset` | `id` | Single row, always `1` |
| | `source`, `revision` | Source identifier and pinned revision |
| | `post_count` | Population size `N` |
| | `status` | `ready` after successful export |
| | `min_cooccurrence` | Export pair-count floor; the application uses it as its minimum selectable floor |

Personal presets and library selection stay in the application's separate personal database. Raw records, temporary counts, and progress stay outside the finished library.

The CLI prints a JSON summary after progress messages. With `--report`, it also writes that summary to a new file: `source`, `revision`, `post_count`, `status`, `min_cooccurrence`, `tag_count`, `pair_count`, `min_tag_occurrences`, `exclude_tags`, `database`, `bytes`, `state`, `inputs`, and `elapsed_seconds`. Keep reports beside libraries when comparing profiles; an existing report file is rejected.

### Intermediate state and reuse

The separate state database contains:

| Table | Fields | Meaning |
| --- | --- | --- |
| `source` | `source`, `revision` | Dataset identity |
| `inputs` | `path` primary key, `bytes` | Absolute input paths and file sizes checked on reuse |
| `processing` | `id`, `min_tag_occurrences`, `excluded_tags` | Singleton configuration affecting retained tags and IDs; exclusions stored as JSON |
| `posts` | `id` primary key | Unique posts committed in the frequency pass |
| `frequencies` | `name` primary key, `count` | Per-tag unique-post counts |
| `groups` | `path`, `group_no`, `phase` composite primary key; `next_block`, `complete` | Row-group progress; phase `1` counts tags, phase `2` counts pairs |
| `pair_posts` | `id` primary key | Unique posts committed in completed pair row groups |
| `pair_counts` | `tag_a`, `tag_b` composite primary key; `count` | All observed retained-tag pair counts before the export floor |

Resume an interrupted statistical pass with the same state path, raw files, source, revision, minimum tag frequency, and exclusion set. These determine the meaning of stored tag IDs. Input reuse checks paths and byte sizes; retain verified raw files unchanged. Older states without recorded processing parameters are rejected: use a new state path.

The pair-export threshold, block size, and batch size may change with compatible state. A completed state can export another pair threshold without recomputing pair counts:

```shell
python -m corpus.importer dev/datasets/danbooru-2026/raw dev/datasets/danbooru-2026/compact-pair2000.sqlite3 --revision REVISION --config corpus/profiles/compact.json --min-cooccurrences 2000 --state dev/datasets/danbooru-2026/compact-state.sqlite3
```

This reuses state from the explicit `compact.sqlite3` example above. Changing tag frequency or exclusions requires new state. Every export requires a new output file. The importer leaves the running application's library in place; upload or select the completed library through the application.

## Verification and historical records

Importer smoke tests use temporary Parquet and SQLite files for deduplication, ratings, thresholds, PMI, configuration, and resumption:

```shell
python -m unittest discover -s tests/corpus -p test_importer.py -v
```

See [candidate smoke tests (Chinese)](../../tests/candidate/README.md) for application-side checks.

| Record | Scope |
| --- | --- |
| [PMI processing (Chinese)](issues/candidate-pmi.md) | Original frequency, rating, PMI, and pair-floor decisions |
| [Reduced library (Chinese)](issues/candidate-pair1000.md) | Historical 1,000-pair floor, sizes, and generation verification |
| [Library floor (Chinese)](issues/library-cooccurrence-floor.md) | Application behavior based on the selected library's floor |

Historical one-off pruning scripts and reports remain under `dev/verification/candidate-pair1000-20261019/`. Their paths and structures describe that run; use the importer above for current repeatable processing.
