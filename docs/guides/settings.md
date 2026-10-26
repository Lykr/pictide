# Settings and Cleanup

[简体中文](../zh-CN/guides/settings.md)

[Documentation](../README.md)

Use Settings to adjust the interface, check generation tasks, and manage the space your images use.

## General settings

Let the interface language and theme follow your system, or choose your own. You can also turn off image transitions and check the path to your data directory here. Changes save automatically.

Choose **Start tour** in the Getting started row to revisit connecting a service and roaming.

Choose **Check for updates** to look for a new stable release. Checks, downloads, and installation happen only when you request them; Pictide never updates automatically. Compatible portable releases offer **Download update**, then **Install and restart**. Save your edits and finish generation tasks first. Images, preferences, models, and your selected data folder are kept.

If direct installation is unavailable, open the release notes and update manually. Source deployments always update manually. The command-line equivalents are described in the [Windows](setup/windows.md#updates), [macOS](setup/macos.md#updates), and [Linux](setup/linux.md#updates) guides.

See [Roam](roam.md) to adjust exploration, or [Getting started](getting-started.md) to connect an image service.

Under **LLM API**, manage named text-service connections using API keys or ChatGPT sign-in. Under **Image API**, choose Danbooru or natural language; natural-language connections select one of your saved LLM APIs. See [setup](getting-started.md#natural-language-prompts).

## Start and stop local ComfyUI

In General settings, enable **Start and stop with Pictide**, select a saved local ComfyUI image API, then choose **Detect installation** or enter its installation folder. Review the detected Python and options under **Advanced startup settings**, then choose **Save startup settings**. Changes apply the next time Pictide starts.

If ComfyUI is already running, Pictide reuses it. Otherwise it starts the configured environment and waits for readiness. Exiting Pictide stops only the process it started; closing the browser leaves Pictide and its service running. Startup failures remain visible in settings with a log location, so you can correct the configuration.

Configure this on the computer running Pictide using its localhost address. Remote image services keep their existing lifecycle. Pictide-installed Windows environments keep their automatic startup unless you disable this setting.

## Task records

Open History to check generation progress, inspect failures, or cancel tasks you no longer need. Generate also lets you cancel all its tasks that have not started; tasks already running in the image service continue.

## Historical image cleanup

**History → Image cleanup** sets how long to keep unliked images. The default is **1 day (24 hours)**; set it to `0` to turn off expiration cleanup. Liked images are excluded from automatic cleanup.

Expired images are cleaned up as you use the app. Their local image files and prompts are permanently deleted. Removing a like makes the image eligible again, using its original generation time, so it may be cleaned up soon afterward.

To keep your complete data collection, make a [backup](backup.md#backup-and-recovery) first.
