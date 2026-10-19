# Vocabulary editions

[简体中文](vocabularies.zh-CN.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md)

Pictide provides two processed statistical vocabularies. Portable packages include `filtered`; download `all-ratings` separately to use statistics from every source rating.

## Choose an edition

| Edition | Source posts included | Minimum ordinary-tag frequency | Minimum pair co-occurrences | Portable default |
| --- | --- | --- | --- | --- |
| `filtered` | `general` and `sensitive`; posts containing `questionable` or `explicit` are excluded before statistics | 100 | 1,000 | Yes |
| `all-ratings` | All four ratings: `general`, `sensitive`, `questionable`, and `explicit` | 100 | 1,000 | No |

Both editions retain ordinary tags and observed rating labels for statistics. Neither removes individual tag names. `all-ratings` includes all source ratings; it still applies the frequency thresholds above and contains processed statistics rather than raw image records. Edition names describe source filtering, so they use `filtered` / `all-ratings` rather than SFW / NSFW.

## Download and switch

Download the `.sqlite3` file you want from the [vocabulary resource release](https://github.com/Lykr/pictide/releases/tag/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b):

- [filtered](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-filtered.sqlite3)
- [all-ratings](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-all-ratings.sqlite3)

Open **Prompts → Library → Upload** and select the downloaded file. Uploading selects it automatically. Alternatively, copy it into `libraries/` under your current data directory (default `data/libraries/`), click **Refresh**, and select it from the library dropdown. Both editions can coexist; keep their distinct filenames.

Your personal presets, fixed terms, drafts, existing tasks, and prefetched images remain. New candidates use the selected vocabulary. See [library switching](prompts.md#add-and-switch-libraries) for co-occurrence limits and fixed-term recognition.

Each download has a matching `.report.json`; the resource release also includes `manifest.json` and `SHA256SUMS` for provenance and integrity checks. These metadata files are for inspection and verification; upload the `.sqlite3` file to Pictide. For reproducible exports, see [Corpus Processing](../dev/corpus.md#export-both-vocabulary-editions).
