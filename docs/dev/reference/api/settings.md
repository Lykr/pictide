# General and History Settings

[简体中文](../../../zh-CN/dev/reference/api/settings.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## General and history settings

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/settings/general` | None | `{theme,language,image_transitions}` |
| PUT | `/api/settings/general` | At least one general setting | Complete saved general settings |
| GET | `/api/settings/history` | None | `{unliked_retention_days,cleanup,artifact_revision}` |
| PUT | `/api/settings/history` | `{unliked_retention_days}` | Same as GET; also triggers a lazy cleanup check |
| POST | `/api/settings/cache/clear` | `{}` | `{deleted_image_scores}` |

| Field | Type and range | Default |
| --- | --- | --- |
| `theme` | `system / light / dark` | `system` |
| `language` | `system / zh-CN / en` | `system` |
| `image_transitions` | Boolean | `true` |
| `unliked_retention_days` | Integer 0–3650; 0 disables time-based cleanup | 1 |

General settings support partial updates, preserving omitted fields. History cleanup applies to unliked images, including unrated and disliked images; liked images are preserved. `cleanup` contains cleanup statistics; see [Data layout](../../data-layout.md).

## Manual cache cleanup

`POST /api/settings/cache/clear` accepts an empty object and returns the number of score-cache rows removed. It only removes `artifact_preference_scores` belonging to images with `deleted_at` set. Hidden but retained images keep their scores. Repeating the request is safe and returns zero when nothing remains; extra parameters are rejected.

Images, tasks, feedback, learning evidence, model parameters, and semantic vectors are preserved. This operation does not compact SQLite or promise a reduction in file size. Score writes check that the image is still undeleted within their write transaction, so late scoring results cannot recreate cleared entries.
