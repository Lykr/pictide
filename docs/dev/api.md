# HTTP API Reference

[简体中文](../zh-CN/dev/api.md)

The entry point for Pictide's currently implemented HTTP API. Read the general conventions, then follow the topic for your operation. Fields and return values are maintained only on their topic pages.

## Find by Operation

| Operation | API details |
| --- | --- |
| Initialize pages and subscribe to state changes | [Initialization and Live Events](reference/api/events.md) |
| Change language, theme, and retention period | [General and History Settings](reference/api/settings.md) |
| Configure roam, save viewing position, and replenish prefetch | [Roam](reference/api/roam.md) |
| Connect generation backends, check connections, and manage workflows | [Generation Backends and Workflows](reference/api/backends.md) |
| Create, paginate, and cancel tasks | [Generation Tasks](reference/api/jobs.md) |
| Query images, submit feedback, clean up, score preferences, and sort | [Images, Feedback, and Scoring](reference/api/images.md) |
| Inspect, export, and reset preferences | [User Preferences](reference/api/preferences.md) |
| Search libraries, save presets, generate, and preview relations | [Candidate Libraries and Presets](reference/api/candidate.md) |

## General Conventions

- Default address: `http://127.0.0.1:8189`; paths below are relative to this address. See the [Project README](../guides/access.md#lan-access) for LAN startup. There is currently no account authentication; data and preferences share the local user `local`.
- Responses are JSON except images, downloads, and SSE. Success usually returns `200`; task submission returns `202`, and creating a workflow separately returns `201`.
- Library upload `POST /api/candidate/library` uses multipart/form-data. All other non-GET/HEAD `/api/` requests, including DELETE, must carry `Content-Type: application/json`; send `{}` when there are no parameters. Request bodies must be JSON objects, without duplicate fields or NaN/Infinity. The usual limit is 8 MiB, with 1,100,000 bytes for candidate requests and 2,048 bytes for preference reset requests.
- For mutation requests, `Origin`, when present, must match the accessed origin; `Sec-Fetch-Site: cross-site` is rejected. Host is restricted to local addresses or the machine's LAN IP allowed by the LAN entry point. General cross-origin calls are not enabled.
- API responses use `Cache-Control: no-store`. This does not mean image preference scores are recomputed every time; scoring has a separate persistent cache.
- Times are usually ISO 8601 UTC strings; viewing position `viewed_at` is an integer in milliseconds. The maximum safe integer is `9007199254740991`.
- `{id}` denotes the corresponding resource ID. IDs in lists are opaque identifiers; callers must not depend on how they are generated.

### Errors

Business errors usually return `{"error":"description"}`. Validation errors in the Candidate API additionally include `"kind":"validation"`. HTTP-layer rejections may return plain text; callers should first check the status code and Content-Type.

| Status | Meaning |
| --- | --- |
| 400 | Parameter, JSON, or generation backend validation error |
| 403 | Host or cross-site mutation restriction |
| 404 | Route or resource does not exist |
| 409 | Revision, duplicate request content, or name conflict |
| 410 | Resource has been cleaned up and is no longer accessible |
| 413 / 415 | Request too large / Content-Type does not meet API requirements |
| 502 | Upstream backend failed while retrieving an image |

Some APIs return business unavailability with `200`, such as connection checks with `ok:false`, roam with `paused:true`, and scoring with `status:"unavailable"`. HTTP status alone does not determine business success.

## Examples

These requests read the tag library and preview prompts without submitting image generation tasks:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/tags?query=black_hair&page=1&page_size=15'

$preview = '{"preset_id":"default","mode":"fixed_seed","seed":42}'
Invoke-RestMethod 'http://127.0.0.1:8189/api/candidate/generate' -Method Post `
  -ContentType 'application/json' -Body $preview
```

Create an event connection in the browser:

```javascript
const events = new EventSource('/api/events');
events.addEventListener('change', (event) => {
  const { topic, revision } = JSON.parse(event.data);
  // Read related resources again based on topic; revision identifies this notification.
});
```

## Implementation and Maintenance Entry Points

- [HTTP routes, request parsing, and status codes](../../backend/host.py)
- [Application orchestration and HTTP response objects](../../backend/application.py)
- [Candidate parameters and results](../../backend/candidate/service.py), [Seed and sequence parameters](../../backend/candidate/rounds.py)
- [Recommendation internal contracts](../../backend/recommendation/contracts.py)
- [Task storage and pagination model](../../backend/store/sqlite.py)

This is an HTTP reference. Internal Python methods for scoring, learning, and similar operations are not additional public HTTP interfaces. There is currently no OpenAPI / Swagger page. When adding, removing, or changing routes, update the corresponding topic and navigation.
