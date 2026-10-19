# Vocabulary editions

[简体中文](vocabularies.zh-CN.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md)

Vocabularies help Pictide compose prompts. The portable package includes a default vocabulary so you can start right away. Switch editions when you want a wider range to explore.

## Choose an edition

| Edition | Content range |
| --- | --- |
| `filtered` (default) | Uses sources rated `general` and `sensitive`, excluding `questionable` and `explicit` sources |
| `all-ratings` | Uses all four source ratings |

The vocabulary shapes prompt combinations; the model and image service also shape the final image.

## Download and switch

Download the vocabulary you want:

- [filtered](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-filtered.sqlite3)
- [all-ratings](https://github.com/Lykr/pictide/releases/download/corpus-editions-fa4d623c2a7d32d2569a3e1657e4aa5b1f6937284cc42091d60c1bcc8d899c5b/pictide-vocabulary-all-ratings.sqlite3)

Open **Prompts → Library → Upload** and select the downloaded `.sqlite3` file. Uploading selects it automatically. Both editions can coexist; use the library list to switch later.

Switching applies to future prompt generation. Your presets, existing images, and tasks remain.
