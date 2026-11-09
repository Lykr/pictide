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
| POST | `/api/roam/start` | `{artifact_id}`; an existing liked image ID | New viewing position `{artifact_id,viewed_at}` |
| POST | `/api/roam/ensure` | `{anchor_id:null or image ID,demand:false}`; both fields may be omitted | Prefetch state; may include a newly created `job` |

### Configuration

| Field | Type and range | Default |
| --- | --- | --- |
| `prefetch_count` | Integer 0–20; 0 disables automatic prefetching | 2 |
| `max_history_images` | Integer 0–100000; 0 disables count-based cleanup | 20 |
| `backend_id` / `preset_id` | String; an empty string selects automatically | Empty string |
| `playback_interval_seconds` | Integer 1–600 | 8 |
| `playback_style` | `single / scroll` | `single` |
| `scroll_speed` | `slow / normal / fast`; 24 / 48 / 80 CSS pixels per second | `normal` |
| `liked_tags_only` | Boolean; liked scope / full scope | `false` |
| `use_canvas_pool` | Boolean; randomly select a usable size from the active image API’s pool; false uses fixed API settings | `true` |
| `prompt_mode` | `random` Drift / `along` Flow / `stay` Anchor | `random` |
| `candidate_count` | Integer 1–20 | 10 |
| `recommendation_strength` | `standard / strong` | `standard` |
| `strong_candidate_multiplier` | Integer 1–5 | 2 |
| `pinned_canvas` | `{width,height}` integer pixels 1–16384, or null to follow Roam; must be supported by the selected API | `null` |
| `pinned_positive` | Array of nonempty complete term strings | `[]` |
| `excluded_positive` | Array of nonempty complete term strings, matched without case and with equivalent spaces and underscores | `[]` |
| `preset_base_positive` | Read-only; fixed positive terms in the current preset | `[]` |

The response also includes `artifact_revision,paused,preference_learning`, and may include `error` while paused. `epoch` is internal state and is not submitted as an HTTP field.

PUT can update any one or a combination of `playback_interval_seconds,playback_style,scroll_speed,liked_tags_only,prompt_mode,candidate_count,recommendation_strength,strong_candidate_multiplier,pinned_positive,excluded_positive,use_canvas_pool,pinned_canvas` independently. Updates to the prefetch count, history count, backend, or preset must include `prefetch_count`; other omitted fields are preserved. Switching to a different cloud backend forces `prefetch_count` to `0` for that save; a later explicit save on the same backend can enable it. Creating the first cloud backend or converting the active backend to cloud also disables automatic prefetch. Danbooru cloud generation requires a preset with an empty negative prompt.

Changing the scope, mode, backend, preset, anchors, or canvas-pool mode preserves the current image and invalidates subsequent old prefetched results. Old results already running are hidden when they finish. Changing only the playback interval, candidate count, or recommendation strength preserves existing prefetched results. Positive pins that duplicate preset fixed terms are removed. Switch out of Anchor mode to edit prompt anchors. Canvas pins are editable in every mode. Count-based cleanup counts only Roam images before the current image. Excess unliked images are cleaned up, while liked images are only hidden from Roam.

Exclusions take priority over fixed and sampled positive terms in Roam and remove matching positive pins on save. Flow regenerates a combination if its previous variable tags include an excluded term. Anchor mode reuses the complete saved reference when available. The exclusion list is applied as a candidate constraint scoped to Roam.

A non-null `pinned_canvas` takes priority over both canvas-pool mode and the API default. Saving or clearing it preserves the current image and discards old future results; repeated saves of the same pin preserve the epoch. The browser defers replacement prefetch until the next navigation, as for prompt anchors. Pool edits do not invalidate prefetched images while a canvas pin is active. A pin keeps its exact pixels even if the pool changes; if a later API configuration cannot apply them, clear the pin or choose a supported size.

Canvas-pool mode samples uniformly from the current API's usable sizes. An unlinked API keeps its fixed size. App selects width and height after any natural-language preparation and before persisting the job; Task reuses those stored pixels for submission and recovery. The candidate, recommendation, and LLM inputs are unchanged. See [canvas pool configuration](backends.md#canvas-pools).

### Viewing position and prefetching

POST `/api/roam/start` starts Roam from any liked original, including Generate images and hidden Roam images. Store atomically references the artifact, restores its Roam visibility, advances the saved viewing position and list revision, and invalidates old future prefetch. Queued old work is cancelled; already accepted old work remains hidden when it finishes. Original files, source, likes, and preference evidence are unchanged. Generate origins remain Generate results unless previously hidden there. Starting from a like clears manual positive pins, exclusions and the pinned canvas in the same transaction. Preset fixed terms and other Roam settings remain in force; this call creates no image job. The browser opens the selected image paused, replacing its old window and scroll position; ordinary Ensure requests resume prefetch. Flow resolves a manual origin's source tags against the current vocabulary and preset; if no compatible combination exists, it uses the existing fresh-candidate fallback. Anchor reuses the saved source prompts. Unavailable or no-longer-liked images return 404; malformed bodies return 400.

`artifact_id` may be null; when non-null, it must identify a visible Roam image. `viewed_at` is a nonnegative safe integer, and only a strictly newer timestamp causes an update. If the original image has been hidden or cleaned up, GET may resolve the position to a neighboring image.

Scroll playback operates on the image covering the viewport center (nearest image edge if the center is in a gap). It persists that centered image through the same viewing-position API, so anchor changes retain the image being viewed. Reload restores that image; older images follow the configured history limit. Presentation-only options preserve generation settings, prefetched images, and paused errors. Single-image display time remains saved while Scroll uses its separate speed.

The Ensure response includes `enabled,prefetch_count,target,waiting_for_liked_tags,preference_learning,ready,pending,roam_pending,paused`, with `job,error,recommendation_error,backend_id,preset_id` included as applicable. `ready` is the number of viewable images after the anchor, `pending` is the number of unfinished jobs across the application, and `roam_pending` is the number of unfinished Roam jobs that have not been invalidated.

One call creates at most one Roam job and does not wait for image generation to finish. `demand:true` can explicitly request the next image even when prefetching is disabled. If the liked-scope pool is empty, the response returns `waiting_for_liked_tags:true` without falling back to the full library. Autoplay timing is handled in the browser; Ensure does not start a timed feeding loop.

For a natural-language backend, `preparing_prompt:true` reports the asynchronous text-conversion stage before an image job exists. Repeated calls share that preparation; completion publishes a jobs event. Failure pauses the epoch without submitting an image or silently retrying. Saving the full Roam settings explicitly starts a fresh epoch when paused, even when every value is unchanged. This leaves image API configuration and existing image tasks unchanged; reads and option-only updates do not authorize a retry. Drift requests fresh wording, Flow supplies the previous tags/text, and Anchor reuses compatible text. Natural-language cloud configurations can keep negative concepts, which the LLM expresses in the positive description.
