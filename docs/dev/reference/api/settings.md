# Application and LLM Settings

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

## Local ComfyUI lifecycle

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/settings/local-generation` | None | `{can_configure,config,choices,status,restart_required}` on localhost; `{can_configure:false}` elsewhere |
| PUT | `/api/settings/local-generation` | At least one configuration field | Same as GET after validation and atomic save |
| POST | `/api/settings/local-generation/detect` | `{backend_id,install_dir?}` | `{candidates:[{install_dir,python,entry,cwd,args,source}]}` |

Configuration contains `enabled` (boolean), `backend_id`, `install_dir`, `python`, `entry`, `cwd` (strings), and `args` (an array of separate argument strings). PUT accepts partial updates and rejects unknown fields. Enabled configurations require a saved ComfyUI connection with a direct loopback HTTP URL and valid local Python, `main.py`, and working directory. A recognizable portable or virtual environment can fill omitted launch paths; an omitted installation can be detected when there is exactly one candidate. Disabling remains possible when launch paths or the linked connection have disappeared. Argument lists contain at most 256 strings and 32768 characters in total; paths/arguments reject NUL and line breaks.

`choices` exposes only eligible connection IDs, names and addresses, never API keys. `status` includes `phase` (`disabled`, `starting`, `running`, `external`, `failed`, or `stopped`), `owned`, `url`, `error`, and `log_path`. It describes this Pictide session; `restart_required` compares saved settings with the startup configuration. A save publishes the existing SSE change event with topic `local_generation`, takes effect on the next process startup, and starts neither ComfyUI nor an image job. Discovery is read-only; multiple candidates require user selection. Linked API addresses and ports override conflicting ComfyUI listen/port arguments at launch.

Both a loopback peer and a localhost Host are required to read launch configuration, save it, or discover installations; write/detect requests elsewhere return 403, in addition to existing same-origin protections. LAN callers receive no local paths from GET. Normal startup reuses an already-ready service without ownership; shutdown stops only this session's child process tree. Startup failure does not prevent HTTP/bootstrap from opening so settings can be repaired.

## Prompt LLM API

`GET /api/llm-apis` lists `{id,name,kind,base_url,model,revision,has_api_key,account}` records. `kind` is `openai` (OpenAI-compatible Chat Completions) or `chatgpt` (official plan-backed Responses). `account` contains only email, connection/plan status, and first-use acknowledgement. Credentials are never returned.

`PUT /api/llm-apis/{id}` saves `{name,kind,base_url,model,api_key}` and returns the list. IDs contain 1–80 letters, digits, underscores or hyphens. Names contain 1–100 characters. OpenAI-compatible configurations require an HTTP(S) URL without credentials, query or fragment and a nonempty model ID. Omitted keys retain their value; empty keys clear it. A saved connection's kind is immutable; create a new record to change it. ChatGPT records may initially omit a model to allow sign-in before discovery. Saving does not submit inference.

`DELETE /api/llm-apis/{id}` rejects connections referenced by a natural-language image API; otherwise it removes configuration and disconnects its renewable session. It returns `{connections,revoked}`. An unconfirmed remote revocation is reported, while local tokens are removed.

ChatGPT operations use `POST /api/llm-apis/{id}/{operation}` with an empty JSON object:

| Operation | Result |
| --- | --- |
| `sign-in` | `{authorization_url}`; requires a loopback peer and localhost Host |
| `cancel` | Cancels the pending login and closes its callback listener |
| `models` | `{models:[{value,label}]}` from the account-specific catalog |
| `disconnect` | `{revoked}`; clears local tokens, retaining registration identity |
| `welcome` | Acknowledges the first-use plan message |

`GET /api/llm-apis/{id}/status` returns `idle`, `pending`, `exchanging`, `connected`, `failed`, `cancelled`, or `expired`, with a safe error when applicable. Login expires after ten minutes; callbacks bind PKCE, state, nonce and issued client ID, validate signed identity, and never activate a mismatched returning account.

The legacy `GET/PUT /api/settings/prompting` remains an alias for the migrated `legacy-prompt-api` configuration and retains `{base_url,model,revision,has_api_key}`. Old natural-language image configurations without `llm_id` resolve only this legacy ID. New selections are explicit; no arbitrary first connection or billing fallback is used.

Saving creates a revision and invalidates preparation. Conversion resolves the image API's selected connection; its credentials never enter image jobs. Explicit natural-language previews contact the text service and consume its allowance or API usage.

ChatGPT conversion uses streaming Responses with a strict JSON schema for the `positive` and `negative` strings. Complete text may arrive in output text/item events before the terminal response; Pictide retains those parts but accepts them only after `response.completed` with completed status. Invalid request parameters stop conversion without retrying or signing the user out. Errors retain the HTTP status and bounded error code/parameter; logs also include the provider request ID when available. Provider message/detail bodies are omitted because they may echo prompts or credentials. A generic HTTP 400 points to the model/request format; repeat sign-in only for a confirmed expired or revoked session.
