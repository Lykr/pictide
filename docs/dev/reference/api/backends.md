# Generation Backends and Workflows

[简体中文](backends.zh-CN.md)

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
| `kind` | Currently supports `comfyui`; the same value is used when omitted |
| `base_url` | HTTP(S) URL of the generation service |
| `api_key` | Optional; omitting it for an existing configuration preserves the key, and an empty string clears it; never returned in plaintext |
| `workflow_mode` | `default / custom`; uses the default text-to-image workflow when no workflow is provided |
| `default_checkpoint` | Model name for default mode; an empty string selects the first available model |
| `workflow` | Custom ComfyUI API node object, rather than the UI's `nodes` array |
| `bindings` | Custom positive and negative text bindings, plus an optional image seed binding |
| `output_nodes` | Array of workflow node IDs from which to collect results |
| `workflow_name` | Used when saving a custom workflow together with the backend |
| `workflow_id` / `workflow_revision` | Submit both when modifying a saved template, preserving its original ID |
| `extra` | Optional adapter extension object |

Example bindings: `{"positive":{"node_id":"2","input":"text"},"negative":{"node_id":"3","input":"text"},"seed":{"node_id":"5","input":"seed"}}`. Custom configuration currently requires positive and negative text bindings, which must not point to the same input; the seed binding may be omitted. Edit node parameters directly in `workflow`.

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
