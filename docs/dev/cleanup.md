# Project Cleanup

[简体中文](../zh-CN/dev/cleanup.md)

[Data layout](data-layout.md) · [Development workflow](development.md)

Use `scripts/clean_project.py` to review disposable development files and remove the entries you approve. It requires Python 3.10+ and Git, with no extra packages. Run it from the project root using your Python interpreter.

## Preview and review

```shell
python scripts/clean_project.py
```

This writes a new JSON plan in `dev/maintenance/` and prints candidate paths, sizes and modification times. The default keeps anything modified in the last seven days. To include recent files in the preview:

```shell
python scripts/clean_project.py --older-than-days 0
```

| Group | Cleanup scope |
| --- | --- |
| `caches` | Children of `dev/cache/`, `dev/build/` and `dev/tmp/`, including rebuildable vocabulary statistics and exports |
| `backups` | Standalone frontend backups under `data/backups/`: an entry containing only `dist/` with `index.html` |
| `verification` | Disposable entries under `dev/verification/`, such as reports, screenshots and isolated test data |

All three groups are previewed by default. Use `--groups caches verification` to select groups, or `--plan dev/maintenance/my-cleanup.json` to name a new plan file. Existing plan files are preserved.

Review `entries` in the plan and remove any entries you want to keep. `skipped` explains preserved files and directories. Models, raw dataset files, environments, repositories, Git-tracked files, symlinks and Windows junctions cause their containing candidate to be preserved. Personal database/image/workflow backups are kept. `data/` is otherwise outside cleanup scope, as are `dev/datasets/`, `dev/models/`, `dev/runtime/`, `dev/maintenance/` and `releases/`.

## Apply the reviewed list

Finish builds and stop any validation instances using the selected directories. Then pass the exact reviewed plan path:

```shell
python scripts/clean_project.py --apply dev/maintenance/my-cleanup.json
```

This permanently deletes only the listed entries. The script checks the project root, allowed paths, Git tracking, links, file sizes and modification times again before deleting. If an entry changed after preview, generate and review a new plan. File content is not hashed; the recorded fingerprint covers directory and file metadata. If cleanup stops partway because a file changes or is locked, the console lists completed deletions; create a new plan for the remainder.

Model-bearing verification directories and personal backups require separate review if you intend to remove them. Rebuilding a deleted portable vocabulary cache reuses the retained raw dataset, or uses the published prebuilt vocabulary when explicitly supplied. Application history and image cleanup remain in [Settings](../guides/settings.md#historical-image-cleanup).
