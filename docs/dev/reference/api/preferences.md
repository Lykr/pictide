# User Preferences

[简体中文](preferences.zh-CN.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#通用约定)

## User preferences

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/recommendation/preferences` | `page`, default 1; `all`, 0 or 1, default 0 | Preference report |
| POST | `/api/recommendation/preferences/reset` | `{request_id,expected_reset_revision}` | `{request_id,reset_revision,reset_at}` |

Report fields: `available,error,feature_version,state_revision,reset_revision,reset_at,evidence_count,term_count,page,page_size,total_pages,terms`. Each term is `{text,channel,weight,evidence_count}`. Channels are `positive / negative`; weights are model parameters, rather than probabilities.

The default page size is 15. `all=1` returns all learned terms for frontend JSON export through the same endpoint. Viewing and exporting do not trigger learning, do not include the complete learning matrix, and cannot restore training state. Only the page and all query parameters are accepted.

For reset, `request_id` contains 1–128 letters, digits, underscores, or hyphens; use the latest report value for `expected_reset_revision`. Duplicate requests can be retried safely, and revision conflicts return 409. Reset clears the learning state and score cache, preserves images and feedback, and does not automatically replay pre-reset feedback as new learning. See [User preferences](../../issues/recommendation-preferences.md) and [Export](../../issues/preference-export.md).
