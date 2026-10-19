# macOS Installation and Startup

[简体中文](macos.zh-CN.md)

[Installation and backend setup](../getting-started.md) · [Documentation](../../README.md)

Read [Before you start](../getting-started.md#before-you-start) first. Run the commands below in a terminal at the project root.

## Portable edition

Extract the release package for your operating system and CPU architecture, then double-click `start.command`. Once ready, it opens the system's default browser automatically. Close the launcher window or press Ctrl+C to stop. Personal data is stored in the package's data directory and reused on the next startup.

Native build and startup paths are provided; native execution still needs verification on this operating system. On first use, connect ComfyUI, OpenAI Images, or Gemini in [Backend settings](../getting-started.md). Supported startup parameters are `--port`, `--data-dir`, `--lan`, and `--no-browser`. Desktop environments can open a browser automatically; on a server, use the address shown in the terminal.

## Run from source

In a directory with the frontend already built, double-click `start.command`. Open http://127.0.0.1:8189 and press Ctrl+C or close the launcher window to stop the application. Next, [connect a generation backend](../getting-started.md).

If the archive lost executable permissions, first run:

```bash
chmod +x start.sh start.command
```

The launcher looks for `python3`, creates `data/runtime/venv`, and installs backend dependencies. Install a suitable Python first if none is available. To specify Python:

```bash
PICTIDE_PYTHON=/path/to/python3 ./start.command
```

## Prepare from source

See [macOS development and builds (Chinese)](../../dev/setup/macos.md#从源码准备).

## Port and data directory

```bash
./start.command --port 8191 --data-dir "$HOME/PictideData"
```

Use a separate port and data directory for development verification: `./start.command --port 8191 --data-dir ./dev/verification/example/data`. Run `./start.command --help` to view parameters. See [data location](../backup.md#data-location) for directory selection rules.

## LAN access

```bash
./start.command --lan
```

Access the application using the host's LAN IP. If the system firewall asks whether Python may accept incoming connections, allow it for your trusted LAN use. The script does not modify the firewall. See [LAN access and Home Screen app](../access.md) for phone access and data sharing.

## Build a portable package

See [macOS development and builds (Chinese)](../../dev/setup/macos.md#构建便携包).
