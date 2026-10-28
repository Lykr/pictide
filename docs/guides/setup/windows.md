# Windows Installation and Startup

[简体中文](../../zh-CN/guides/setup/windows.md)

[Installation and Image API setup](../getting-started.md) · [User documentation](../../README.md)

## Portable edition

These steps apply to v0.5.0 and later.

1. Extract the package and double-click `Pictide.exe`.
2. On first launch, confirm where to save your data and follow the setup guide. Need an image service? Choose **ComfyUI + Anima Turbo v1.1** to install one.
3. Wait for preparation to finish. Your browser opens automatically; follow the in-app tour to start roaming.

Use ↑/↓ to select, Enter to confirm, and Esc to go back. Directory paths can be typed and edited in the same screen. Downloads and service startup refresh the current screen; detailed logs remain available from the tray menu.

Installing the recommended model also connects the service and its default workflow. To use an existing service, see [image service setup](../getting-started.md).

Pictide keeps running in the system tray after you close the browser. Right-click its tray icon to reopen it, view logs, or exit. Exiting also stops any ComfyUI process started by Pictide.

<details>
<summary>Local installation requirements and data location</summary>

Setup checks your hardware and shows the estimated size and model license before downloading. Automatic Anima Turbo setup requires an **8 GB dedicated VRAM / 16 GB RAM** capacity tier. If requirements are unmet or cannot be detected, you can connect an existing image service. NVIDIA installation and image generation have been verified; AMD, Intel, and CPU options have not been tested on their corresponding hardware.

Images, preferences, and downloaded generation resources stay in the folder selected on first launch, defaulting to `data/` beside the program. Choose a folder outside the program directory to keep your data when deleting the program.

</details>

<details>
<summary>Run setup again or use a terminal</summary>

Keep `Pictide.exe` and `_internal/` together. Open PowerShell in the portable package directory:

- To run setup again, exit Pictide and run `.\Pictide.exe --setup`. If you choose another data folder, existing data stays in the previous location and is not moved automatically.
- To run in a terminal, use `.\Pictide.exe --cli` and press Ctrl+C to stop.

`--cli` and `--no-browser` skip the preparation guide by default; add `--setup` when needed.

</details>

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

Follow [Windows source preparation](../../dev/setup/windows.md#prepare-from-source) to install prerequisites and build the frontend, then run `.\start.cmd` in the project directory.

The source launcher uses `-Lan`, `-Port`, and `-DataDir`, for example `.\start.cmd -Lan -Port 8191 -DataDir 'E:\PictideData'`. Add `-Cli` to keep the terminal open. See the [development guide](../../dev/setup/windows.md#build-a-portable-package) to build a release package.

## Updates

Run these commands in the extracted portable folder. `--check-updates` only checks; `--update` explicitly requests a compatible download, installation, and restart. Nothing updates automatically.

```shell
Pictide.exe --check-updates
Pictide.exe --update
```

Save edits and finish generation tasks first. If direct installation is unavailable, use [GitHub Releases](https://github.com/Lykr/pictide/releases) to update manually. See [Settings](../settings.md#general-settings) for the in-app controls.
