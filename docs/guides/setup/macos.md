# macOS Installation and Startup

[简体中文](macos.zh-CN.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

These steps describe the new `.app` package built from the current source; it has not yet been released or verified on a Mac desktop. Existing releases keep their original launchers.

Extract the ZIP matching your Mac's chip (Apple Silicon or Intel), drag `Pictide.app` into Applications, and open it. A small preparation window shows the first [recommendation dependency download](../getting-started.md#recommendation-dependency-preparation). Your browser opens when ready. Next, [connect an image service](../getting-started.md) and start roaming.

If preparation fails, choose **Try again** to continue with the files already downloaded. **View logs** provides details when needed.

Closing the browser keeps Pictide running. Use its menu bar icon to reopen Pictide, copy an access address, open your data folder, view logs, or quit. It shows preparation and service status, including unexpected stops. Messages follow the system language: Simplified Chinese or English.

The app is not Developer ID signed or notarized. If macOS blocks the first launch, follow Apple's [Open Anyway instructions](https://support.apple.com/en-us/102445) in System Settings → Privacy & Security after trying to open it. Pictide does not change your security settings.

Personal data is stored in `~/Library/Application Support/Pictide/`. Replacing the app keeps your images and preferences. To move from an older package, quit both versions and follow [Backup and recovery](../backup.md#backup-and-recovery) before copying personal data to the new location; keep the old copy until you have checked it.

## LAN access

Open Terminal and run:

```bash
/Applications/Pictide.app/Contents/MacOS/Pictide --lan
```

Connect your phone to the same LAN and open the LAN address shown in Pictide's menu. See [LAN access and Home Screen app](../access.md).

## Port and data directory

To use another port or data location:

```bash
/Applications/Pictide.app/Contents/MacOS/Pictide --port 8191 --data-dir "$HOME/PictideData"
```

For terminal operation, add `--cli`; press Ctrl+C to stop.

## Prepare from source

Follow [macOS source preparation (Chinese)](../../dev/setup/macos.md#从源码准备) to install prerequisites and build the frontend, then run `./start.command` in the project directory. Source startup keeps its terminal and uses the project's `data/`; use `--lan`, `--port`, or `--data-dir` as needed.

Source startup requires Python 3.10+. If the source launch scripts lack executable permissions, run `chmod +x start.sh start.command` in the project directory. See the [development guide (Chinese)](../../dev/setup/macos.md#构建便携包) to build a release package.
