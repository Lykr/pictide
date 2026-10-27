# Generation Backends and Workflows

[简体中文](../../../zh-CN/dev/reference/api/backends.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Generation backends

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| PUT | `/api/backends/{id}` | Backend configuration draft | Saved public configuration |
| DELETE | `/api/backends/{id}` | `{}` | `{deleted:true,id}` |
| POST | `/api/backends/{id}/check` | Backend configuration draft | `{ok,message}`; read-only preflight check |
| POST | `/api/backends/{id}/models` | Backend configuration draft | `{models:[name],selected:name or null}` |
| POST | `/api/backends/{id}/template` | Backend configuration draft | Default workflow configuration and available `input_options` |

The backend list is provided by Bootstrap's `backends`; there is no separate GET list route. Path IDs contain 1–80 letters, digits, underscores, or hyphens. Check, model discovery, and template requests do not save configuration.

| Draft field | Description |
| --- | --- |
| `name` | Backend name |
| `kind` | `comfyui / openai / gemini`; omitted means `comfyui` |
| `prompt_type` | `danbooru / natural_language`; omitted means `danbooru`. Natural language uses the separate [prompt service](settings.md#prompt-llm-api). |
| `canvas_pool_id` | Optional saved pixel-size pool ID; an empty string uses the fixed API size. Roam selects sizes from this pool when enabled; Generate can submit an explicit pixel pair for the batch, or omit it to keep fixed settings. |
| `llm_id` | Saved LLM API ID used for natural-language conversion. New natural-language configurations must select an existing connection; legacy configurations without this field use `legacy-prompt-api`. |
| `base_url` | HTTP(S) service root; cloud URLs include the version path, such as `https://api.openai.com/v1` or `https://generativelanguage.googleapis.com/v1beta` |
| `api_key` | Optional; omission preserves a saved key only for the same kind. Switching kinds clears it; an empty string also clears it. Never returned in plaintext. |
| `model` | Required model ID for `openai` and `gemini`; entered manually |
| `size` / `quality` | Optional OpenAI image parameters; empty means service default |
| `aspect_ratio` / `image_size` | Optional Gemini image parameters; empty means service default |
| `workflow_mode` | `default / custom`; uses the default text-to-image workflow when no workflow is provided |
| `default_checkpoint` | Model name for default mode; an empty string selects the first available model |
| `workflow` | Custom ComfyUI API node object, rather than the UI's `nodes` array |
| `bindings` | Custom positive and negative text bindings, plus optional image seed and paired integer width/height bindings |
| `output_nodes` | Array of workflow node IDs from which to collect results |
| `workflow_name` | Used when saving a custom workflow together with the backend |
| `workflow_id` / `workflow_revision` | Submit both when modifying a saved template, preserving its original ID |
| `extra` | Optional adapter extension object |

Example bindings: `{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}}`. Custom configuration currently requires positive and negative text bindings, which must not point to the same input; the seed binding may be omitted. Optional `width` and `height` bindings use the same `{node_id,input}` format, target distinct integer inputs, and must be supplied together. Default workflows bind both automatically. Edit fixed node parameters directly in `workflow`; Roam overrides only explicitly bound size inputs when using a pool.

Workflow fields, checkpoint discovery, and the template route belong to ComfyUI. Cloud `/models` returns the configured model rather than discovering a catalog. Cloud `/check` performs a read-only lookup of the selected model and never submits generation; it does not prove image-output entitlement or validate generation quality.

Public configurations include `capabilities` with `negative_prompt`, `seed`, `dimensions`, `models`, `events`, `cancel`, `recovery`, and `cloud`. OpenAI Images and Gemini do not support a negative prompt channel, explicit image seeds, remote events, cancellation, or recovery in this integration. Danbooru mode rejects nonempty negative prompts, including candidate preset output. Natural-language preparation instead asks the LLM to express avoidance constraints in the positive text and return an empty negative string. Explicit image seeds are rejected. A candidate seed controls local prompt selection only. The UI uses capabilities to show available controls.

OpenAI appends `/images/generations` to its Base URL and Gemini appends `/interactions`. Gemini sends `model`, `input`, `response_format` with image output options, and `store:false`, authenticating with `x-goog-api-key`. These are single-turn text-to-image adapters; `generateContent`, Imagen, image editing, and third-party service presets are outside this release. Successful responses may contain Base64 or image URLs; outputs are saved locally before being exposed as Pictide artifacts. API keys are used by the backend, never by the browser to contact the provider directly.

Cloud submission waits for the completed response. Timeout or interruption without a recorded result leaves the task uncertain, with no automatic resubmission. Local cancellation cannot guarantee remote cancellation or avoid charges. Jobs and artifacts expose `backend_kind` so history can distinguish provider semantics; snapshots retain the model and actual request parameters without claiming an unsupported seed was applied. Cloud integration is verified with protocol mocks; paid provider generation remains unverified.

Public configuration includes `has_api_key` and excludes `api_key`. Default mode resolves installed models before creating the workflow; new jobs save a backend snapshot. Deleting a backend preserves historical jobs and images. Saving the current Roam backend can resume prefetching paused by an earlier error; it does not automatically retry previously failed jobs or resume playback.

## Workflow library

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/workflows` | None | `{workflows:[{id,name,revision}]}` |
| GET | `/api/workflows/{id}` | None | Complete workflow record |
| POST | `/api/workflows` | `{name,workflow,bindings,output_nodes}` | `201`; new record |
| DELETE | `/api/workflows/{id}` | `{revision}` | `{deleted:true,id,detached_backends}` |

A complete record is `{id,name,workflow,bindings,output_nodes,revision}`. A standalone POST only creates a new workflow; duplicate names return 409. To update, rename, and apply an existing workflow, submit `workflow_id,workflow_revision,workflow_name` through `PUT /api/backends/{id}`.

`revision` is the SHA-256 of the workflow file contents. Use the latest value read when deleting or updating; conflicts return 409. Deletion retains a backup and detaches template references from current backends; the actual workflow snapshots in backends and historical jobs are preserved.

## Canvas pools

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/canvas-pools` | None | `[{id,name,sizes,revision}]` |
| PUT | `/api/canvas-pools/{id}` | `{name,sizes:[{width,height}]}` | Complete saved pool list |
| DELETE | `/api/canvas-pools/{id}` | `{}` | Remaining saved pool list |

IDs use the same format as backend IDs. Names contain 1–100 characters after trimming. A pool contains 1–64 unique sizes; each width and height is an integer from 1 to 16384. Pools store exact pixels, with no ratio, pixel-budget, or weighting fields. PUT replaces the whole pool and creates a revision. Deleting a referenced pool returns `400` until the current image APIs unlink it.

`capabilities.dimensions` identifies adapters that accept pixel-size plans: OpenAI Images and ComfyUI workflows with both size bindings. ComfyUI excludes sizes not divisible by 8; save validation requires at least one usable entry for each linked API. OpenAI's service/model may impose additional size restrictions, checked by that service at generation time. Gemini does not support these pixel plans and rejects a nonempty `canvas_pool_id`.

App serializes pool mutations with image-API reference saves and Roam enqueueing. Changing sizes in the active pool invalidates subsequent Roam prefetch when pool mode is enabled; edits to unused pools and name-only changes preserve it. The shared pool list participates in ordinary resource refreshes, including fallback polling and reconnects: coalesced SSE notifications do not have to retain a particular topic. Refreshes retain unsaved drafts and keep the selected editor stable when its revision is unchanged. Existing jobs retain their selected widths and heights independently of later pool changes.
