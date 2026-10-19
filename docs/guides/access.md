# LAN Access and Home Screen App

[简体中文](access.zh-CN.md)

[Documentation](../README.md) · Complete [local setup](getting-started.md) first

## LAN access

Follow the LAN startup and firewall instructions for the host operating system:

- [Windows](setup/windows.md#局域网访问)
- [Linux](setup/linux.md#局域网访问)
- [macOS](setup/macos.md#局域网访问)

Use `http://127.0.0.1:8189` on the host computer. Other devices use its LAN IP address, such as `http://192.168.50.50:8189`; use the new address if the IP changes. Normal startup allows local access only.

All devices must be on a trusted LAN that permits communication between them. You do not need to expose the ComfyUI port. If you use a different port, update the firewall rule accordingly; do not configure router port forwarding.

LAN startup listens on all IPv4 interfaces, but HTTP only accepts the loopback address or the host's private IP address on which the request actually arrived. Same-origin checks for modifications remain enabled. LAN devices share images, settings, tasks, and preferences without account isolation, and can generate, rate, and delete images. Grant access only to trusted devices.

Phones use bottom navigation, and enlarged images support horizontal swipes. In standalone app mode, swiping up on a roaming image raises its rating by one level; swiping down lowers it by one level. In a regular browser, vertical swipes retain page scrolling. Immersive mode provides a touch-accessible exit button. A regular iPhone browser uses page scrolling and remembers the position in each section; address-bar collapse still depends on content height and browser handling of user gestures. Home Screen standalone mode hides the top brand bar while retaining section titles and system safe areas, with a fixed shell and separate layouts for images and the bottom action bar. Over plain HTTP, copying attempts a browser-compatible fallback; when native fullscreen is unavailable, an in-page immersive layout is used.

## iPhone Home Screen app

Open the computer's LAN address in Safari → Share → Add to Home Screen → Add. If the system shows “Open as Web App,” leave it enabled. Launch Pictide from its Home Screen icon to use a standalone window without the Safari address bar, reusing the existing bottom navigation and safe-area layout. If you installed an older shortcut, remove it and add it again to update the installation-time icon and window mode.

Current support includes Home Screen launch, an app icon, a standalone window, and theme colors; there is no Service Worker or offline cache. Pictide must be running on the computer, and the phone must be able to reach its LAN address. If the computer's IP changes, add the app again using the new address. An Apple developer account is not required. Modern iOS can open websites directly as Home Screen web apps; see [Apple's instructions](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios) and [WebKit's Home Screen app notes](https://webkit.org/blog/17333/webkit-features-in-safari-26-0/#every-site-can-be-a-web-app-on-ios-and-ipados) for installation and behavior details.
