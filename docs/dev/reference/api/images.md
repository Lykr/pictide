# Images, Feedback, and Preference Scores

[简体中文](../../../zh-CN/dev/reference/api/images.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Images and feedback

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/artifacts` | Image list query parameters | Image window; see below |
| GET | `/api/artifacts/{id}/image` | None | Image file binary |
| GET | `/api/artifacts/{id}/prompts` | None | JSON download: `{positive,negative}` |
| PUT | `/api/artifacts/{id}/feedback` | `{value:1 or -1 or null}` | `{artifact,artifact_revision}` |
| DELETE | `/api/generated` | `{}` | `{removed,hidden,revision,pending_files}` |
| DELETE | `/api/generated/{id}` | `{}` | Same as above, for one image on the Generate page |

### Image queries

| Parameter | Description |
| --- | --- |
| `liked` | `1` returns liked images only; otherwise includes all feedback states |
| `limit` | 1–200; default 200; the Liked page client uses 100 |
| `before` | `next_cursor` from the previous window, to continue reading older images |
| `source` | `all / roam / generate`; default all |
| `around` | Image ID at the center of the Roam window; only for source=roam; cannot be combined with before or liked=1 |
| `tag` | Repeatable, e.g. `?liked=1&tag=smile&tag=long%20hair`; only for filtering liked images; multiple conditions use AND |

The response is `{artifacts,has_more,has_newer,anchor_id,next_cursor,total,counts,source,revision}`. Images are normally ordered newest first by time and ID. `counts` contains global counts for `artifacts,roam,generate,liked`; `total` is the count for the current filter. `next_cursor` is the last item's ID when older images remain, or null otherwise.

### Artifact

Main fields: `id,job_id,node_id,output_index,created_at,local_path,content_type,deleted_at,generated_hidden_at,roam_hidden_at,positive,negative,seed,feedback,source,backend_kind,seed_applied,image_url`. `image_url` points to the same-origin image endpoint. `seed` is the image seed; `seed_applied` indicates whether it was actually applied by the backend; it is false for OpenAI Images and Gemini. `backend_kind` identifies the generation adapter; an internal stored seed does not imply a deterministic cloud image. Term information reflects the actual text used at generation time.

Feedback values are `1` for like, `-1` for dislike, and `null` to withdraw feedback and return to unrated. The response is returned after feedback is persisted. Preference learning and cleanup triggered by this feedback are handled in the background by the orchestration layer, so scoring may temporarily use the previous preference state. Repeatedly setting the same state does not count again toward learning.

Generated image cleanup clears visibility from unliked image records and reclaims local image files and prompt JSON. Liked images are only hidden from the Generate page and remain on the Liked page. Job history is preserved. This endpoint cannot clean up Roam images.

## Like filters and image preference scores

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/liked/tags` | None | `{tags:[{text,count}],revision}` |
| GET | `/api/liked/ranked` | Repeatable `tag`, as in liked-image filtering | `{artifacts,revision,state_revision,score_min,score_max,scoring_available,error,refreshed_at}` |
| POST | `/api/liked/ranked/refresh` | `{tags:[]}`, or an array of current filter terms | Same as ranked; explicitly recalculates scores for that scope |
| GET | `/api/artifacts/{id}/preference-score` | None | Image preference score; see below |

Tag counts are the number of liked images containing that positive term, counted once per term per image. The list uses lexicographic order by default. Ranked returns all images within the current filter, and the client paginates them at 100 images per page. Images are sorted by descending raw preference score, then descending time and ID for ties; images without scores appear last.

A single-image score returns `{status,score,love_score,score_min,score_max,state_revision,feature_version,reason}`:

- `status`: `scored / missing_snapshot / unavailable`.
- `score`: the deterministic posterior mean score, as a raw value; it is neither the sampled selection score nor a percentage.
- `love_score`: a relative 0–100 value converted using the historical score range: `100 × (score-score_min)/(score_max-score_min)`. It is null when the range is unavailable or its endpoints are equal, and does not represent the probability of a like.
- `state_revision,feature_version`: the learning-state and feature versions of this cached score. When scoring is unavailable, the relevant fields are null and `reason` explains why.

Scores are persistently cached in image metadata. Normal reads only fill missing cache entries; they do not rescore historical images after every learning update. An explicit refresh recalculates scores for the selected scope and updates `refreshed_at`; normal reads do not update that timestamp. Resetting preferences clears the score cache. Existing cached scores may still be shown while recommendations are temporarily unavailable. A failed refresh preserves the old cache; check `scoring_available,error`. See [Score caching (Chinese)](../../../zh-CN/dev/issues/image-score-cache.md).
