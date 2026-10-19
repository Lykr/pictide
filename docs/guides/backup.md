# Data Backup and Recovery

[简体中文](backup.zh-CN.md)

[User documentation](../README.md)

Back up your data directory before upgrading or moving computers to keep your images, likes, preferences, and settings.

## Data location

Find the current directory under Settings → General. Windows and Linux packages default to `data/` beside the program; the macOS app uses `~/Library/Application Support/Pictide/`. Source deployments use the project's `data/`.

To store data on another drive, follow the steps for [Windows](setup/windows.md#port-and-data-directory), [Linux](setup/linux.md#port-and-data-directory), or [macOS](setup/macos.md#port-and-data-directory).

## Backup and recovery

1. Close Pictide and wait for it to exit.
2. Copy the entire data directory to your backup location. For Windows and Linux portable editions, you can back up the whole application directory instead. On macOS, back up the separate data directory even when you keep a copy of the app.
3. To restore, close the application, save a separate copy of your current data, and replace the data directory with the backup.
4. Restart and check your images, likes, and Image API settings.

Backups also contain prompt presets, workflows, libraries, recommendation dependencies, and API keys. Store them securely.

When moving between operating systems, prepare the appropriate application first, then copy `db/`, `images/`, `workflows/`, `history-cleanup.json`, `libraries/`, and `models/` from the same backup. Leave the old operating system's runtime behind.

## Restore an individual workflow

Previous versions are saved under `workflows/.backups/` in the data directory before updates or deletions. Copy the required version back to its workflow file, then select it again and save under Settings → Image API.

Before cleaning up images, see [retention rules](settings.md#historical-image-cleanup). Developers can find the full layout in [Data directories](../dev/data-layout.md).
