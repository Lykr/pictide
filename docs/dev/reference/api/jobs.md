# Generation Jobs

[简体中文](../../../zh-CN/dev/reference/api/jobs.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Generation jobs

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/jobs` | None | `{jobs:[Job]}`; most recent 100 jobs |
| GET | `/api/jobs?page=1` | `page`, a positive integer | `{jobs,page,page_size,total,total_pages}` |
| POST | `/api/jobs` | Generation request; see table below | `202`; `{job,jobs,next_seed,candidate_result,next_candidate}` |
| POST | `/api/jobs/cancel-pending` | `{}` | `{cancelled_count}` |
| POST | `/api/jobs/{id}/cancel` | `{}` | `{job}` |

Pages have a fixed size of 15 jobs. Requests beyond the last page return the last page.

| Generation field | Type and description |
| --- | --- |
| `backend_id` | Required, saved backend ID |
| `request_id` | Required, 8–100 characters; reuse the same value on retries and use a new value for a different generation operation |
| `positive` | Required nonempty string for manual generation; up to 20000 characters |
| `negative` | String, empty by default; up to 20000 characters; cloud adapters require empty |
| `seed` | Integer -1 or 0–9007199254740991; default -1 for a random image seed; cloud adapters accept only -1 and do not send an image seed |
| `width` / `height` | Optional paired integers, 1–16384 pixels; all jobs in the request share this size. Omit both to retain fixed API settings. Requires `capabilities.dimensions`; ComfyUI sizes must be divisible by 8. |
| `count` | Quantity per round, integer 1–10; default 1 |
| `repetitions` | Number of generation rounds, integer 1–10; default 1 |
| `candidate` | Optional candidate generation parameters; see the candidate section; resampled each round when provided |
| `preparation_id` | Optional completed natural-language preview ID when no `candidate` is supplied; tags and configuration must match |

One request creates `count × repetitions` jobs. The workflow's own batch_size may produce multiple images per job. Fixed seeds increment per job, with `next_seed` giving the next value; random seeds remain -1. `candidate_result` is the candidate result from the final round, and `next_candidate` contains the seed and frame index for subsequent generation; both are null when no candidate parameters are provided.

The same `request_id` reuses the previously created result; different contents cause a conflict. `202` means the job has been persisted, rather than generation having finished; obtain progress through the list and SSE. Batch cancellation affects only jobs on the Generate page that have not started, preserving Roam prefetching. Individual cancellation is handled through the job service and is not guaranteed to interrupt GPU computation that has already started.

For a natural-language backend, input `positive`/`negative` are source concepts. App converts them before submitting jobs, including folding avoidance constraints into positive text for image APIs without a negative channel. All rounds must prepare successfully before the batch is committed. The response adds `rendered` for the final round; `candidate_result.rendered` contains the same value when candidates were used. Repeated images within a round share text. An explicit retry with the same request ID resumes retained preparation or replays the committed batch. No dedicated cancellation endpoint exists for the pre-job LLM stage; stopping an HTTP request does not guarantee that the remote service stops or avoids charges.

### Job

Main fields: `id,request_id,backend_id,revision_id,status,positive,negative,seed,backend_prompt_id,error,created_at,updated_at`. Jobs also provide nullable `width,height`: requested pixels selected by Roam or supplied by Generate; null retains fixed workflow/API settings. They remain unchanged across pool edits, restart, and submission recovery. They describe requested inputs, not any later workflow upscaling. Lists also provide `source` (`roam / generate`) and `backend_name,backend_kind,seed_applied`. Configuration snapshots containing secrets are not returned.

`positive`/`negative` contain actual image-service text. Natural-language jobs, their artifacts, and the image-prompts endpoint also expose `source_prompts:{positive,negative}` with the original concepts; older/Danbooru records omit this field. These sources support tag-based anchors, filtering, and historical feedback without interpreting prose as tags.

Statuses are `queued / submitting / running / completed / failed / unknown / cancelled`. `unknown` means the submission or execution outcome cannot be confirmed; do not directly resubmit the same generation operation on that basis. OpenAI Images and Gemini have no remote recovery or cancellation support here; an uncertain submitted request is not automatically repeated, and local cancellation does not guarantee the provider stopped or avoided charges.
