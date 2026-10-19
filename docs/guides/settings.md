# Settings and Cleanup

[简体中文](settings.zh-CN.md)

[Documentation](../README.md) · [Settings API](../dev/reference/api/settings.md)

Settings has General, Roam, Backend, and History sections. General shows the data location; History contains task records and image cleanup.

## General settings

Settings → General offers System / 简体中文 / English for the interface language. The default follows the browser's preferred language, falling back to English for unsupported languages. Changes apply immediately, are saved in SQLite, and synchronize live to other pages of the same application. Interface language does not change prompts, original tag names, or user-defined names. See [internationalization](../dev/issues/i18n.md) for the maintenance entry point for new languages.

Settings → General offers System / Dark / Light themes. Changes apply immediately, are saved in `data/db/pictide.sqlite3`, and persist across refreshes and restarts. Other open pages of the same application synchronize through live events. The default follows the system; existing explicit choices are retained. Changes in system appearance apply live, and all sections and overlays share the theme. See [general settings](../dev/issues/general-settings.md) for API details.

Settings → General includes an Image transition animation switch, enabled by default, controlling fade-ins in Roam and the enlarged Generate / Liked views. The choice survives refreshes; animations do not play when the system requests reduced motion. See [general settings](../dev/issues/general-settings.md).

## Task records

Task history is stored in SQLite, with 15 entries per page by default. You can page through results, enter a page number, expand details, or cancel individual tasks. Live updates preserve the current page. “Cancel pending tasks” on Generate only cancels its tasks that have not started; roaming prefetch and tasks already executing on the backend are retained.

## Historical image cleanup

Settings → History → Image cleanup sets the retention period for images that are not liked. The default is **1 day (24 hours)**; `0` disables new expiration cleanup. The period starts when an image completes and enters Feed. An image liked by any user is protected; other expired images are cleaned up on demand. After unliking, age is still measured from the original insertion time, so an already-expired image may be removed at the next trigger.

Checks run on demand at application startup, when reading image lists or images, submitting generation, or rating images. Saving settings runs an immediate check. There is no scheduled task, cleanup polling, or separate background service. Time-based expiration checks are at least 60 seconds apart. An enabled roaming history count limit continues to be checked during these operations so that new images do not keep exceeding it between expiration checks. Together, both cleanup methods mark at most 100 images and reclaim at most 100 sets of pending files per trigger to avoid blocking operations on large collections. Cleanup does not run while the application is closed or without a triggering operation.

Cleanup removes images and their same-named prompt JSON from Pictide's `data/images`, and hides them from Feed. Generation records, rating history, and duplicate-submission protection records are retained. Remote ComfyUI files, configuration, tag libraries, and backup directories are unaffected. Cleaned-up images cannot be recovered through old links or task retries.

When files are in use or temporarily cannot be deleted, pending deletions persist in the database and are retried at the next trigger. Files already marked for deletion are still retried even after new expiration cleanup is disabled. Deletion is refused for paths outside the allowed directory, symbolic links, and Windows Junctions. Files and JSON shared by active images are also protected. Settings are stored in `data/history-cleanup.json`; if the settings file is corrupted, new expiration cleanup pauses and can be repaired by saving again in the settings dialog.

## Continue reading

- [Roaming scope, modes, and prefetch](roam.md)
- [Editing backends and workflows](getting-started.md#接入-comfyui)
- [Data backup and recovery](backup.md#备份与恢复)
