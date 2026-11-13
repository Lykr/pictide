# User Data

[简体中文](../../../zh-CN/dev/reference/api/user-data.md)

[API index](../../api.md) · [Common conventions and errors](../../api.md#general-conventions)

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/api/user-data/export` | None | Portable ZIP attachment |
| POST | `/api/user-data/import` | ZIP bytes with `Content-Type: application/zip` | Import summary |

Both operations require a loopback peer and a localhost `Host`. They are unavailable through the LAN listener because the application has no account authentication.

## Export format

The ZIP contains:

```text
manifest.json
data.json
images/<artifact-id>.<extension>
prompts/<artifact-id>.json
state/precision.bin
state/reward.bin
```

The manifest records the format and Pictide versions, recommendation feature and policy versions, item counts, and SHA-256 metadata for every other entry. `data.json` contains currently liked original-image metadata, exact prompt text and snapshots, current feedback, the latest recommendation event needed for each artifact, current evidence, the reset boundary, and score range. Large posterior precision and reward matrices are stored as binary `state/` entries instead of inflating JSON. Historical journal entries that are not referenced by current evidence are omitted.

API keys, ChatGPT tokens, non-liked image files, presets, canvas pools, general and roam settings, caches, models, statistical libraries, and runtime files are not exported. The archive is a portable liked collection and learned-preference transfer, not a replacement for a complete data-directory backup.

The server builds the archive under `tmp/` and removes it after the response completes or the transfer is interrupted. Export is unavailable when a liked image file is missing or its stored content type is unsupported.

## Import

Import is limited to one compressed archive no larger than 4 GiB and 8 GiB expanded. The server validates paths, entry counts, JSON documents, image metadata, recommendation evidence, policy matrices, and every checksum before copying files or changing the database.

The recommendation policy version must match the running application. If the recommendation feature/model version differs, Pictide imports the model-independent event snapshots, discards the incompatible posterior matrix and derived evidence, and rebuilds learning with the current local model. The response reports `preferences_migrated` when rebuilding completes immediately or `preference_rebuild_pending` when it must resume in the background. Invalid, malformed, truncated, oversized, or policy-incompatible archives return `400` without changing liked images, feedback, preferences, or database records.

Before an import, Pictide creates a consistent SQLite backup under `backups/before-user-data-import-<timestamp>/pictide.sqlite3`. The import then:

- Adds liked images that do not already exist.
- Leaves an existing artifact with the same ID unchanged and counts it as skipped.
- Replaces current local feedback-learning events, evidence, posterior state, reset boundary, score range, and image score cache with the archive state.
- Preserves existing image APIs, workflows, prompts presets, canvas pools, general settings, roam settings, and non-imported images.
- Restores original bytes and prompt JSON for each newly imported liked image.

Active generation tasks or another settings write in progress block import with `409`. Newly copied image files are removed if the database transaction fails. The response contains:

```json
{
  "liked_imported": 12,
  "liked_skipped": 1,
  "preference_evidence": 43,
  "backup": "backups/before-user-data-import-.../pictide.sqlite3",
  "artifact_revision": 27
}
```

After a successful import the Host publishes the existing jobs, artifacts, feedback, and recommendation change events. The Settings UI reloads the page so all views use the imported state.
