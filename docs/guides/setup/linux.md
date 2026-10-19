# Linux Installation and Startup

[简体中文](linux.zh-CN.md)

[Installation and backend setup](../getting-started.md) · [Documentation](../../README.md)

Read [Before you start](../getting-started.md#启动前准备) first. Run the commands below in a terminal at the project root.

## Portable edition

Extract the release package for your operating system and CPU architecture, then run `./start.sh` in the release directory. Once ready, it opens the system's default browser automatically. Close the launcher window or press Ctrl+C to stop. Personal data is stored in the package's data directory and reused on the next startup.

Native build and startup paths are provided; native execution still needs verification on this operating system. On first use, connect ComfyUI in [Backend settings](../getting-started.md#接入-comfyui). Supported startup parameters are `--port`, `--data-dir`, `--lan`, and `--no-browser`. Desktop environments can open a browser automatically; on a server, use the address shown in the terminal.

## Run from source

In a directory with the frontend already built, run:

```bash
bash start.sh
```

Open http://127.0.0.1:8189 and press Ctrl+C to stop the application. Next, [connect ComfyUI](../getting-started.md#接入-comfyui).

By default, the launcher looks for `python3`, creates `data/runtime/venv`, and installs backend dependencies. On Debian / Ubuntu, if venv is missing, install the `python3-venv` package matching the Python version in use. To specify Python:

```bash
PICTIDE_PYTHON=/path/to/python3 bash start.sh
```

## Prepare from source

See [Linux development and builds](../../dev/setup/linux.md#从源码准备).

## Port and data directory

```bash
bash start.sh --port 8191 --data-dir "$HOME/PictideData"
```

Use a separate port and data directory for development verification: `bash start.sh --port 8191 --data-dir ./dev/verification/example/data`. Run `bash start.sh --help` to view parameters. See [data location](../backup.md#数据位置) for directory selection rules.

## LAN access

```bash
bash start.sh --lan
```

Access the application using the host's LAN IP. If a firewall is enabled, use your distribution's firewall tools to allow trusted LAN access to the selected port. The script does not modify the firewall. See [LAN access and Home Screen app](../access.md) for phone access and data sharing.

## Build a portable package

See [Linux development and builds](../../dev/setup/linux.md#构建便携包).
