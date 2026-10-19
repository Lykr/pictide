# General and History Settings

[简体中文](settings.zh-CN.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#通用约定)

## General and history settings

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/settings/general` | None | `{theme,language,image_transitions}` |
| PUT | `/api/settings/general` | At least one general setting | Complete saved general settings |
| GET | `/api/settings/history` | None | `{unliked_retention_days,cleanup,artifact_revision}` |
| PUT | `/api/settings/history` | `{unliked_retention_days}` | Same as GET; also triggers a lazy cleanup check |

| Field | Type and range | Default |
| --- | --- | --- |
| `theme` | `system / light / dark` | `system` |
| `language` | `system / zh-CN / en` | `system` |
| `image_transitions` | Boolean | `true` |
| `unliked_retention_days` | Integer 0–3650; 0 disables time-based cleanup | 1 |

General settings support partial updates, preserving omitted fields. History cleanup applies to unliked images, including unrated and disliked images; liked images are preserved. `cleanup` contains cleanup statistics; see [Data layout](../../data-layout.md).
