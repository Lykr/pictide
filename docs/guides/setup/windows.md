# Windows Installation and Startup

[简体中文](windows.zh-CN.md)

[Installation and backend setup](../getting-started.md) · [Documentation](../../README.md)

Read [Before you start](../getting-started.md#before-you-start) first. Run the commands below in PowerShell at the project root.

## Portable edition

Extract the release package for your operating system and CPU architecture, then double-click `start.cmd`. Once ready, it opens the system's default browser automatically. Close the launcher window or press Ctrl+C to stop. Personal data is stored in the package's data directory and reused on the next startup.

An actual Windows portable build has been verified. On first use, connect ComfyUI, OpenAI Images, or Gemini in [Backend settings](../getting-started.md). Supported startup parameters are `--port`, `--data-dir`, `--lan`, and `--no-browser`. Desktop environments can open a browser automatically; on a server, use the address shown in the terminal.

## Run from source

In a directory with the frontend already built, double-click `start.cmd`. Open http://127.0.0.1:8189 and press Ctrl+C or close the launcher window to stop the application. Next, [connect a generation backend](../getting-started.md).

The launcher creates `data/runtime/venv`, installs backend dependencies, and also attempts to find an existing local Codex Python runtime. To specify Python:

```powershell
$env:PICTIDE_PYTHON = 'C:\Path\To\python.exe'
.\start.cmd
```

## Prepare from source

See [Windows development and builds (Chinese)](../../dev/setup/windows.md#从源码准备).

## Port and data directory

```powershell
.\start.cmd -Port 8191 -DataDir 'E:\PictideData'
```

Use a separate port and data directory for development verification: `.\start.cmd -Port 8191 -DataDir .\dev\verification\example\data`. See [data location](../backup.md#data-location) for directory selection rules.

## LAN access

```powershell
.\start.cmd -Lan
```

The launcher window lists the host's LAN addresses. The Windows network must be a trusted Private network. If a firewall rule is needed, run this in an administrator PowerShell:

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

Update the rule if you use another port. See [LAN access and Home Screen app](../access.md) for phone access and data sharing.

## Build a portable package

See [Windows development and builds (Chinese)](../../dev/setup/windows.md#构建便携包).
