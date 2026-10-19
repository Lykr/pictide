# Linux Installation and Startup

[简体中文](linux.zh-CN.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

Extract the Linux portable package, open a terminal in that directory, and run:

```bash
./start.sh
```

On first launch, wait for the [recommendation dependency download](../getting-started.md#recommendation-dependency-preparation). The browser opens when ready; you can also visit `http://127.0.0.1:8189`. Next, [connect an image service](../getting-started.md) and start roaming.

Keep the terminal open and press Ctrl+C to stop. Personal data stays in the package's `data/` directory for your next session.

## LAN access

Run from the portable package directory:

```bash
./start.sh --lan
```

Connect your phone to the same LAN and open the computer's LAN address, such as `http://192.168.50.50:8189`. If a firewall is enabled, allow trusted LAN access to the selected port. See [LAN access and Home Screen app](../access.md) to install it on your phone.

## Port and data directory

To use another port or data location:

```bash
./start.sh --port 8191 --data-dir "$HOME/PictideData"
```

## Prepare from source

Follow [Linux source preparation (Chinese)](../../dev/setup/linux.md#从源码准备) to install prerequisites and build the frontend, then run `bash start.sh` in the project directory. LAN, port, and data directory options are the same as above.

The launcher requires Python 3.10+. On Debian / Ubuntu, install the matching `python3-venv` package if venv is missing. See the [development guide (Chinese)](../../dev/setup/linux.md#构建便携包) to build a release package.
