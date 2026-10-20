# LAN Access and Home Screen App

[简体中文](../zh-CN/guides/access.md)

[User documentation](../README.md)

Use the same Pictide library on your phone, tablet, or another computer to keep browsing and roaming.

## LAN access

1. Connect your computer and phone to the same trusted LAN.
2. Enable LAN access on the host computer: [Windows](setup/windows.md#lan-access) · [Linux](setup/linux.md#lan-access) · [macOS](setup/macos.md#lan-access).
3. Open the computer's LAN address on your phone, such as `http://192.168.50.50:8189`.

Keep Pictide running on the computer. If its IP changes, use the new address. You do not need to expose ComfyUI's port.

All devices share images, settings, and preferences, and can generate and delete images. Open access only to a trusted LAN; router port forwarding is unnecessary.

## iPhone Home Screen app

Open the LAN address in Safari, then choose Share → Add to Home Screen → Add. Leave “Open as Web App” enabled if shown. The Home Screen icon opens Pictide in its own window.

The app still needs a connection to the computer running Pictide. If the computer's IP changes, add it again using the new address.

After an interface update, fully close Pictide in the iOS app switcher and reopen it from the Home Screen. Regular updates do not require reinstallation. To update an installation-time icon or window mode, remove the old shortcut and add it again.
