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

| Field | Type and range | Default |
| --- | --- | --- |
| `theme` | `system / light / dark` | `system` |
| `language` | `system / zh-CN / en` | `system` |
| `image_transitions` | Boolean | `true` |
| `unliked_retention_days` | Integer 0–3650; 0 disables time-based cleanup | 1 |

General settings support partial updates, preserving omitted fields. History cleanup applies to unliked images, including unrated and disliked images; liked images are preserved. `cleanup` contains cleanup statistics; see [Data layout](../../data-layout.md).

## Prompt LLM API

`GET /api/settings/prompting` returns `{base_url,model,revision,has_api_key}`. `PUT` accepts partial `{base_url,model,api_key}` updates and returns the same public shape. The saved configuration must have an HTTP(S) base URL and nonempty model ID; the URL must not contain credentials, query, or fragment. Omitted keys retain their value; an empty `api_key` clears it. Keys are stored locally and never returned in plaintext.

The service is shared by natural-language image configurations and is independent of their image API keys/models. Saving creates a new revision and invalidates outstanding Roam preparation. Conversion appends `/chat/completions` to the base URL and requires JSON-object output. Saving does not contact the provider; an explicit natural-language preview tests conversion and may incur text-service charges.
