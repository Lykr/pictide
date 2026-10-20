# Windows Installation and Startup

[简体中文](windows.zh-CN.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

The steps below apply to packages built from the current source. Existing releases keep their original launchers.

Extract the Windows portable package and double-click `Pictide.exe`. On first launch, a short terminal guide lets you connect an existing image API, prepare local ComfyUI, or configure it later. Local preparation shows your detected graphics card and recommends an environment, with other environments available through manual selection. It offers ComfyUI with **Anima Turbo v1.1**, or ComfyUI alone. Before downloading, review the estimated download size, required disk space, location, and model license. Downloads resume after an interruption.

With the recommended model installed, its default workflow is connected automatically. Once the browser opens, choose **Show me around**, then **Start roaming** to generate your first image. Generate is also ready to use. If you chose an existing service, later setup, or ComfyUI alone, follow the [image service connection steps](../getting-started.md) as needed.

Each model lists its hardware requirements before download. Anima Turbo currently requires an **8 GB dedicated VRAM / 16 GB RAM** capacity tier for automatic setup. If requirements are unmet or cannot be detected, the model download is blocked; you can still prepare ComfyUI alone or connect an existing image service.

The temporary window shows download and startup progress, including the first [recommendation dependency download](../getting-started.md#recommendation-dependency-preparation). When ready, it closes and Pictide runs through the system tray. Startup failures remain visible. NVIDIA installation and image generation have been verified; AMD, Intel, and CPU options have not been tested on their corresponding hardware. CPU generation can be slow.

Closing the browser keeps Pictide running. Use its tray menu to reopen Pictide, view logs, or exit. Exiting also stops the ComfyUI process started by Pictide. Startup messages and the tray menu follow your system language, with Simplified Chinese and English supported. Personal data and downloaded local generation resources stay in the package's `data/` directory.

Keep `Pictide.exe` and its `_internal/` folder together. To run in a terminal instead, run `.\Pictide.exe --cli`; press Ctrl+C to stop.

To run the preparation guide again, exit Pictide, open PowerShell in the portable package directory, and run `.\Pictide.exe --setup`. Existing API connections are preserved. Terminal (`--cli`) and no-browser startup skip interactive preparation unless you explicitly pass `--setup`.

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
