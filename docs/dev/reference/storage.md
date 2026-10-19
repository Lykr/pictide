# SQLite Storage Reference

[简体中文](storage.zh-CN.md)

[Data Layout and Responsibilities](../data-layout.md) · [Calls and Data Flow](../architecture/flows.md)

The main business database stores application state, the personal preset database stores presets and library selection, and library files under libraries store offline statistics. This page records current ownership and associations, rather than serving as an upgrade procedure for old versions.

## Main Database Ownership

| Table or group | Responsibility |
| --- | --- |
| `backends` / `backend_revisions` | Current configuration entries and immutable historical snapshots |
| `jobs` / `generation_batches` | Individual tasks, batch idempotency, and execution context |
| `artifacts` / `feedback` | Image source, hidden/cleaned state, and -1/1 feedback; withdrawal removes the current rating |
| `pending_image_deletions` | Persistent reclamation queue for local images and JSON |
| `roam_*` | Viewing position, prefetch ownership, settings, anchors, and pause state |
| `general_settings` | Theme, language, and image transition effects |
| `recommendation_*` | Model vectors, preference parameters, feedback evidence, and reset records |
| `artifact_preference_scores` / `recommendation_score_range` | Raw image score cache, manual refresh time, and historical score range |

## Roam and Historical Snapshots

SQLite initialization adds roam tables with `CREATE TABLE IF NOT EXISTS`, preserving existing tasks and images:

| Table | Data |
| --- | --- |
| `roam_jobs` | `job_id` is the primary key and references `jobs`; also stores `epoch`, `candidate` JSON, and `created_at`. Candidate JSON contains `candidate_id`, `preset_id`, `policy`, positive/negative text, `features`, and `terms`. Tags include source, ID, text/category/polarity at that time, and `content_revision`. |
| `roam_settings` | Prefetch count, history limit, backend/preset, mode, liked scope, and epoch. |
| `roam_playback_settings` / `roam_candidate_settings` | Autoplay interval and candidate combination count. |
| `roam_recommendation_settings` / `roam_anchor_settings` | Recommendation strength/Strong multiplier and pinned_positive/preset_base_positive. |
| `roam_runs` | `epoch` is the primary key; `error` is this version's pause reason. An existing record means paused. |
| `roam_view` | Viewing position for the single local user. `actor_id` is fixed to `local` and is the primary key; nullable `artifact_id` references `artifacts`; `viewed_at` is a nonnegative safe-integer timestamp in milliseconds. Only strictly newer saves replace the value, preventing out-of-order requests from moving it backward. |

Tasks and candidate snapshots are saved in the same database transaction. Images use the existing task/artifact relationship, without expanding the JSON stored beside each image. Changing settings that invalidate prefetch, or saving complete settings to resume after a pause, uses a new epoch. Old tasks and pause records remain; old-version failures do not pause new settings.

These snapshots trace the tag text, categories, and identities actually used at generation time; updating a library does not rewrite historical snapshots. Manually entered prompts have no tag source, and fuzzy matching must not fabricate associations. Whether learning is possible depends on snapshot completeness and recommendation availability. Backups must retain both SQLite and roam settings.

Viewing position is stored outside the tag library, roam settings, and browser localStorage. Image selection in Liked and Generate does not overwrite it; browsers using the same local instance share the position. Refresh and restart restore it from the database. If the original image has been cleaned up, reads first return the nearest older roam image, otherwise the nearest newer image, or null when no image is available; the saved timestamp remains unchanged. See the [Architecture Description](../architecture/flows.md#roam-prefetch-and-image-generation) for viewing-position and neighboring-image-window API contracts.

## Generation Batches and Image Sections

Generation batches and individual tasks share SQLite; there is no separate batch configuration file. Initialization adds `generation_batches` with `CREATE TABLE IF NOT EXISTS`:

| Field | Data |
| --- | --- |
| `request_id` | Text primary key; idempotent batch request ID. |
| `payload_hash` | Non-null text; content checksum of normalized original generation input, rules, and both counts. |
| `count` | Non-null integer; number of workflow executions in this batch. |
| `job_ids` | Non-null text; JSON array of task IDs in batch order. |
| `created_at` | Non-null text; batch creation time. |
| `context` | Nullable text; JSON containing the new plan's round count, next count, and last round's sampling result, restored unchanged on retry. |

The batch and all tasks are written in one transaction. Network retries retrieve the original batch by request ID. Each task still references its submission-time backend revision; artifacts remain linked through `artifacts.job_id`.

Image sections reuse task ownership: images linked through `roam_jobs` belong to Roam; all others belong to Generate. Queries naturally place manual images created before the upgrade in Generate, without rewriting, moving, or deleting existing images or prompt JSON, or changing feedback. Liked retains images across sources, and history cleanup settings apply to both image types.

## Configuration Revisions

The selected workflow uses a fixed ID. Saving edits replaces its JSON and checks the client-read `revision`. Before updates and on deletion, original bytes are backed up to `workflows/.backups/<id>-<revision>.json`; backups do not appear in workflow selection. If an ordinary save or database operation fails, the workflow file changed by that operation is restored. To restore a version, stop the application, back up current data, and copy the target backup to `workflows/<id>.json`, naming it with the ID inside the file. The backend configuration must select and save the template again after restoration.

Every backend save creates an immutable `backend_revisions` record; the current `backends` table contains only an entry pointing to the latest revision. Tasks always reference their submission-time revision. Deleting a backend removes only this entry. All revisions, including API keys, tasks, images, and ratings remain in the database. Find the corresponding `config` snapshot in `backend_revisions` by the original `backend_id`, then restore it through the backend-save use case; there is currently no dedicated recovery UI. Saving the entire database retains these recovery sources; deleting a configuration does not erase its stored keys.

Deleting a workflow creates a new revision that unlinks it for every associated current backend, all in one database transaction. It clears `workflow_id`, `workflow_name`, and `workflow_revision`, retaining the actual workflow, bindings, outputs, and keys. Revisions referenced by historical tasks remain unchanged. Workflow updates apply only to the backend being saved; other backend snapshots remain as they were.

## Recommendation Cache and Retractable Learning

Recommendation reuses `db/pictide.sqlite3` without creating another database:

| Table | Purpose |
| --- | --- |
| `recommendation_vectors` | float32 semantic vector cache keyed by model/runtime/preprocessing version and tag text |
| `recommendation_policy` | Stable content-key index, float64 full precision matrix, accumulated feedback vector, revision, and valid evidence count, per user and feature version |
| `recommendation_events` | Monotonic revisions of like/dislike/withdrawal state changes and actual generated combination snapshots; written in the same transaction as feedback |
| `recommendation_resets` | User reset revision, time, and feedback-event watermark, isolating learning events from before the reset |
| `recommendation_reset_requests` | Idempotent reset request results, so retries do not clear preferences accumulated later |
| `recommendation_evidence` | Latest applied evidence per user, feature version, and image, including withdrawal state, preventing duplicate or out-of-order accumulation |

App's single background learning worker processes unapplied feedback records, woken at startup and by later operations. Scoring does not wait for the current learning update. If the encoder becomes unavailable during runtime, notifications remain while image likes save normally. New feature versions can re-encode the same historical actual text and valid feedback. After a user's reset, only actual feedback changes beyond the reset watermark are processed; historical likes are not imported again. Historical categories and library tag IDs do not define learning identity. Missing or corrupt derived parameters can be rebuilt from retained evidence. Model resources live in `models/minilm`, separate from regenerable caches. Source and portable startup both verify the fixed catalog and prepare missing files before HTTP starts; complete valid files are reused offline. See [model startup preparation](../../guides/getting-started.md#recommendation-model-startup). Feedback and snapshots are the basis for recovering learning, so back up the complete SQLite database. JSON beside images gains no configuration or learning data. See [Recommendation Design (Chinese)](../issues/recommendation-v1.md) for interfaces, features, and learning limitations.

## Image Score Cache

`artifact_preference_scores` stores raw image mean scores, feature/policy versions, and learning revisions. Ordinary reads fill missing cache entries; explicit refresh recomputes the selected scope. Manual refresh time is stored in the score row's refreshed_at, and queries return its maximum. Historical score ranges live in recommendation_score_range; resetting preferences clears the corresponding cache. See the [Image Scoring API](api/images.md#like-filters-and-image-preference-scores) for HTTP responses and field semantics, and the [Main Database Implementation](../../../backend/store/sqlite.py) as the implementation authority.

## Candidate Data

The library's dataset.min_cooccurrence records the minimum relation count used during processing and is retained through import, upload, and release export. Orchestration and candidate generation use it as the lower bound for minimum co-occurrence count. The base library uses 10; the current reduced library uses 1000.

In `libraries/*.sqlite3`, tags stores `id,name,post_count`; correlations stores `pmi,count` for unordered tag pairs; dataset stores source/status. Personal configuration lives separately in `db/candidate.sqlite3`: presets stores editable presets, and library_selection stores the current library filename. Uploads import statistical tables only, preserving local personal presets. Display names and category columns are not duplicated. The UI displays original names with underscores, converted to space-separated text for recommendation/generation calls.

Offline processing supports tag exclusions, ordinary-tag frequency thresholds, and pair-count thresholds. Defaults are 100 posts per ordinary tag and 10 co-occurrences per pair; observed rating labels—general / sensitive / questionable / explicit—are retained unless explicitly excluded. Tag filtering keeps all unique source posts in the PMI population. See [Corpus Processing](../corpus.md#statistics-and-output-structure) for parameters, field definitions, and statistics. The current trial library uses a pair floor of 1,000; see the historical [Extreme Reduction Record (Chinese)](../issues/candidate-pair1000.md). A missing record means the statistic was not retained and its exact count is unknown. PMI uses base-2 logarithms.

Raw Parquet lives under `dev/datasets/danbooru-2026/raw/` at the project root; download verification is stored separately in download.sqlite3. Import deduplication IDs, temporary counts, and progress exist only in offline SQLite, not in the finished library. Updating statistical libraries does not rewrite historical tasks or feedback in the main database. See [PMI Design (Chinese)](../issues/candidate-pmi.md) and [Co-occurrence Candidate Records (Chinese)](../issues/cooccurrence-candidates-v1.md) for processing details.
