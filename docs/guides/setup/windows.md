# Windows Installation and Startup

[简体中文](windows.zh-CN.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

The steps below apply to packages built from the current source. Existing releases keep their original launchers.

Extract the Windows portable package and double-click `Pictide.exe`. A temporary window shows startup progress, including the first [recommendation dependency download](../getting-started.md#recommendation-dependency-preparation). When ready, the startup process exits and Pictide opens your browser, running through the system tray with no service terminal window. Startup failures remain visible. Next, [connect an image service](../getting-started.md) and start roaming.

Closing the browser keeps Pictide running. Use its tray menu to reopen Pictide, view logs, or exit. Startup messages and the tray menu follow your system language, with Simplified Chinese and English supported. Personal data stays in the package's `data/` directory.

Keep `Pictide.exe` and its `_internal/` folder together. To run in a terminal instead, run `.\Pictide.exe --cli`; press Ctrl+C to stop.

## LAN access

Open PowerShell in the portable package directory and run:

```powershell
.\Pictide.exe --lan
```

Connect your phone to the same LAN and open the LAN address recorded in the startup log; choose **View logs** from the tray menu to find it. Set the Windows network to a trusted Private network. If the firewall blocks access, allow it from an administrator PowerShell:

```powershell
New-NetFirewallRule -Name 'Pictide-LAN-8189' -DisplayName 'Pictide LAN (8189)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Profile Private -RemoteAddress LocalSubnet
```

Update the rule if you change the port. See [LAN access and Home Screen app](../access.md) to install it on your phone.

## Port and data directory

To use another port or store data on another drive, run from the portable package directory:

```powershell
.\Pictide.exe --port 8191 --data-dir 'E:\PictideData'
```

## Prepare from source

Follow [Windows source preparation (Chinese)](../../dev/setup/windows.md#从源码准备) to install prerequisites and build the frontend, then run `.\start.cmd` in the project directory.

The source launcher uses `-Lan`, `-Port`, and `-DataDir`, for example `.\start.cmd -Lan -Port 8191 -DataDir 'E:\PictideData'`. Add `-Cli` to keep the terminal open. See the [development guide (Chinese)](../../dev/setup/windows.md#构建便携包) to build a release package.
