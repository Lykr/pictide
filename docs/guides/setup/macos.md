# macOS Installation and Startup

[简体中文](macos.zh-CN.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

Extract the portable package matching your Mac's chip and double-click `start.command`. On first launch, wait for the [recommendation dependency download](../getting-started.md#recommendation-dependency-preparation); the browser opens when ready. Next, [connect an image service](../getting-started.md) and start roaming.

Keep the launcher terminal open and press Ctrl+C to stop. Personal data stays in the package's `data/` directory for your next session.

On first launch, macOS may ask you to allow both `start.command` and the internal `Pictide` executable. The portable edition is not Developer ID-signed or notarized yet. If you trust your download from this repository, follow Apple's [Open Anyway instructions](https://support.apple.com/en-us/102445) for each blocked entry.

## LAN access

Open a terminal in the portable package directory and run:

```bash
./start.command --lan
```

Connect your phone to the same LAN and open the computer's LAN address, such as `http://192.168.50.50:8189`. If the firewall asks to allow incoming connections, allow them for your trusted LAN use. See [LAN access and Home Screen app](../access.md) to install it on your phone.

## Port and data directory

To use another port or data location:

```bash
./start.command --port 8191 --data-dir "$HOME/PictideData"
```

## Prepare from source

Follow [macOS source preparation (Chinese)](../../dev/setup/macos.md#从源码准备) to install prerequisites and build the frontend, then double-click `start.command` in the project directory. LAN, port, and data directory options are the same as above.

Source startup requires Python 3.10+. If the source launch scripts lack executable permissions, run `chmod +x start.sh start.command` in the project directory. See the [development guide (Chinese)](../../dev/setup/macos.md#构建便携包) to build a release package.
