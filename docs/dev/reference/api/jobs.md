# Generation Jobs

[简体中文](jobs.zh-CN.md)

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
| `negative` | String, empty by default; up to 20000 characters |
| `seed` | Integer -1 or 0–9007199254740991; default -1 for a random image seed |
| `count` | Quantity per round, integer 1–10; default 1 |
| `repetitions` | Number of generation rounds, integer 1–10; default 1 |
| `candidate` | Optional candidate generation parameters; see the candidate section; resampled each round when provided |

One request creates `count × repetitions` jobs. The workflow's own batch_size may produce multiple images per job. Fixed seeds increment per job, with `next_seed` giving the next value; random seeds remain -1. `candidate_result` is the candidate result from the final round, and `next_candidate` contains the seed and frame index for subsequent generation; both are null when no candidate parameters are provided.

The same `request_id` reuses the previously created result; different contents cause a conflict. `202` means the job has been persisted, rather than generation having finished; obtain progress through the list and SSE. Batch cancellation affects only jobs on the Generate page that have not started, preserving Roam prefetching. Individual cancellation is handled through the job service and is not guaranteed to interrupt GPU computation that has already started.

### Job

Main fields: `id,request_id,backend_id,revision_id,status,positive,negative,seed,backend_prompt_id,error,created_at,updated_at`. Lists also provide `source` (`roam / generate`) and `backend_name,seed_applied`. Configuration snapshots containing secrets are not returned.

Statuses are `queued / submitting / running / completed / failed / unknown / cancelled`. `unknown` means the submission or execution outcome cannot be confirmed; do not directly resubmit the same generation operation on that basis.
