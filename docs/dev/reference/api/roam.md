# Roam

[简体中文](../../../zh-CN/dev/reference/api/roam.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

## Roam

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/settings/roam` | None | Roam configuration and state; see table below |
| PUT | `/api/settings/roam` | Configuration fields; see update rules | Saved configuration and state |
| GET | `/api/roam/view` | None | `{artifact_id,viewed_at}` |
| PUT | `/api/roam/view` | `{artifact_id,viewed_at}` | Actual saved and resolved viewing position |
| POST | `/api/roam/ensure` | `{anchor_id:null or image ID,demand:false}`; both fields may be omitted | Prefetch state; may include a newly created `job` |

### Configuration

| Field | Type and range | Default |
| --- | --- | --- |
| `prefetch_count` | Integer 0–20; 0 disables automatic prefetching | 2 |
| `max_history_images` | Integer 0–100000; 0 disables count-based cleanup | 20 |
| `backend_id` / `preset_id` | String; an empty string selects automatically | Empty string |
| `playback_interval_seconds` | Integer 1–600 | 8 |
| `liked_tags_only` | Boolean; liked scope / full scope | `false` |
| `prompt_mode` | `random` Drift / `along` Flow / `stay` Anchor | `random` |
| `candidate_count` | Integer 1–20 | 10 |
| `recommendation_strength` | `standard / strong` | `standard` |
| `strong_candidate_multiplier` | Integer 1–5 | 2 |
| `pinned_positive` | Array of nonempty complete term strings | `[]` |
| `preset_base_positive` | Read-only; fixed positive terms in the current preset | `[]` |

The response also includes `artifact_revision,paused,preference_learning`, and may include `error` while paused. `epoch` is internal state and is not submitted as an HTTP field.

PUT can update any one or a combination of `playback_interval_seconds,liked_tags_only,prompt_mode,candidate_count,recommendation_strength,strong_candidate_multiplier,pinned_positive` independently. Updates to the prefetch count, history count, backend, or preset must include `prefetch_count`; other omitted fields are preserved. Switching to a different cloud backend forces `prefetch_count` to `0` for that save; a later explicit save on the same backend can enable it. Creating the first cloud backend or converting the active backend to cloud also disables automatic prefetch. Danbooru cloud generation requires a preset with an empty negative prompt.

Changing the scope, mode, backend, preset, or anchors preserves the current image and invalidates subsequent old prefetched results; old results already running are hidden when they finish. Changing only the playback interval, candidate count, or recommendation strength preserves existing prefetched results. Preset fixed terms take priority, and duplicate anchors are removed; anchors cannot be edited in Anchor mode. Count-based cleanup counts only Roam images before the current image. Excess unliked images are cleaned up, while liked images are only hidden from Roam.

### Viewing position and prefetching

`artifact_id` may be null; when non-null, it must identify a visible Roam image. `viewed_at` is a nonnegative safe integer, and only a strictly newer timestamp causes an update. If the original image has been hidden or cleaned up, GET may resolve the position to a neighboring image.

The Ensure response includes `enabled,prefetch_count,target,waiting_for_liked_tags,preference_learning,ready,pending,roam_pending,paused`, with `job,error,recommendation_error,backend_id,preset_id` included as applicable. `ready` is the number of viewable images after the anchor, `pending` is the number of unfinished jobs across the application, and `roam_pending` is the number of unfinished Roam jobs that have not been invalidated.

One call creates at most one Roam job and does not wait for image generation to finish. `demand:true` can explicitly request the next image even when prefetching is disabled. If the liked-scope pool is empty, the response returns `waiting_for_liked_tags:true` without falling back to the full library. Autoplay timing is handled in the browser; Ensure does not start a timed feeding loop.

For a natural-language backend, `preparing_prompt:true` reports the asynchronous text-conversion stage before an image job exists. Repeated calls share that preparation; completion publishes a jobs event. Failure pauses the epoch without submitting an image or silently retrying. Saving the full Roam settings explicitly starts a fresh epoch when paused, even when every value is unchanged. This leaves image API configuration and existing image tasks unchanged; reads and option-only updates do not authorize a retry. Drift requests fresh wording, Flow supplies the previous tags/text, and Anchor reuses compatible text. Natural-language cloud configurations can keep negative concepts, which the LLM expresses in the positive description.
