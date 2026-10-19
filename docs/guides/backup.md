# Data Backup and Recovery

[简体中文](backup.zh-CN.md)

[User documentation](../README.md). This page explains where personal data is stored and how to back it up and restore it.

## Data location

View the current data directory under Settings → General. The portable edition defaults to `data/` inside the release directory; the source edition defaults to `data/` in the project. Moving the entire portable directory keeps your personal data together with the application.

To choose another data directory, follow the instructions for [Windows](setup/windows.md#端口与数据目录), [Linux](setup/linux.md#端口与数据目录), or [macOS](setup/macos.md#端口与数据目录).

## Backup and recovery

1. Close Pictide and wait for it to exit.
2. Copy the entire data directory to a backup location named with the date. For the portable edition, you can instead back up the entire release directory to preserve both the application and your personal data.
3. Before restoring, close Pictide, save another copy of the current data directory, then replace the corresponding directory with the backup.
4. Start Pictide and check images, likes, and backend settings.

A full directory backup preserves images, tasks, ratings, preferences, prompt presets, backend settings, workflows, tag libraries, and recommendation models. Backups contain backend API keys; store them securely.

When moving to another operating system, use its portable package or prepare a source environment for that system, then restore your personal data: `db/`, `images/`, `workflows/`, `history-cleanup.json`, plus `libraries/` and `models/`. Restore images, tasks, and ratings from the same backup.

## Restore an individual workflow

Versions saved before a workflow was updated or deleted are in `workflows/.backups/` under the data directory. Copy the required version back to the corresponding workflow file, then select it again and save under Settings → Backends.

## Further reading

- [Add and switch tag libraries](prompts.md#添加与切换词库)
- [Historical image cleanup](settings.md#历史图片清理)
- [Developers: full directory layout and responsibilities](../dev/data-layout.md)
