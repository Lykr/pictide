# Vocabulary editions

[简体中文](../zh-CN/guides/vocabularies.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md)

Vocabularies help Pictide compose prompts. They are downloaded separately from the application. An existing valid vocabulary is reused, including a custom library.

When no valid vocabulary is found, an interactive terminal asks which edition to download. Unattended startup, including desktop workers and background services, defaults to `filtered` without waiting for input. To choose explicitly, add `--vocabulary filtered` or `--vocabulary all-ratings` to your launch command. This option applies only when no valid vocabulary exists.

Downloads are pinned to a published version and verified by size, SHA-256, and SQLite integrity before selection. Interrupted downloads resume after restarting; installed libraries remain in `libraries/` under your data directory.

## Choose an edition

| Edition | Content range |
| --- | --- |
| `filtered` (recommended; unattended default) | Uses sources rated `general` and `sensitive`, excluding `questionable` and `explicit` sources |
| `all-ratings` | Uses all four source ratings, including explicit material. **May generate explicit content.** |

The vocabulary shapes prompt combinations; the model and image service also shape the final image.

## Download and switch

To switch an existing installation or prepare first launch offline, download the vocabulary you want:

- [filtered](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-filtered.sqlite3)
- [all-ratings](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-all-ratings.sqlite3)

Open **Prompts → Library → Upload** and select the downloaded `.sqlite3` file. Uploading selects it automatically. Both editions can coexist; use the library list to switch later.

Switching applies to future prompt generation. Your presets, existing images, and tasks remain.
