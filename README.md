# <img src="web/public/icons/pictide.svg" alt="" width="36" height="36" /> Pictide

[简体中文](README.zh-CN.md)

**A world of images unfolds as you roam.**

![Pictide roaming demo](docs/assets/roam.gif)

New images are generated along the way, guided by your feedback and anchors.

Pictide is a local generative image exploration app that gradually adapts to your preferences through feedback. Browse, express what you like, and guide the next image without needing a specific creative goal. Images and preferences are saved on your computer. Cloud backends receive your generation prompts. [About Pictide](docs/guides/about.md).

## User guide

### Quick start (portable edition)

1. Prepare a ComfyUI instance with a text-to-image model, or an OpenAI Images / Gemini API key and image-capable model.
2. Extract the portable package for your system and run its launcher: [Windows](docs/guides/setup/windows.md#portable-edition) · [Linux](docs/guides/setup/linux.md#portable-edition) · [macOS](docs/guides/setup/macos.md#portable-edition). Your browser opens automatically when the application is ready.
3. Connect your generation service in **Settings → Image API** using the [backend setup guide](docs/guides/getting-started.md), then open **Roam** to start browsing. Cloud Roam starts with automatic prefetch disabled; use a preset with an empty negative prompt.

The package includes the runtime, frontend, and compact statistical library. On first startup, it downloads and verifies MiniLM before opening the application; follow the progress in the launcher window. Later startups reuse the local model. See [model startup preparation](docs/guides/getting-started.md#recommendation-model-startup) for offline setup and download retries. Personal data stays in the package's `data/` directory. The Windows package has been validated; see the platform guides for the status of native Linux and macOS builds and verification.

### Run from source

1. Prepare a ComfyUI instance with a text-to-image model, or an OpenAI Images / Gemini API key and image-capable model.
2. Follow the installation and startup guide for [Windows](docs/guides/setup/windows.md), [Linux](docs/guides/setup/linux.md), or [macOS](docs/guides/setup/macos.md). Open http://127.0.0.1:8189.
3. Configure your generation service in **Settings → Image API**, test the connection, and save. Once the library and recommendation model are ready, open **Roam**, select **Start roaming**, and browse, rate, and advance through images.

Co-occurrence generation requires a statistical library; preference learning requires a local MiniLM model. See [setup and connections](docs/guides/getting-started.md) for preparation. Close the launcher window or press Ctrl+C to stop the application.

### Workspace

| Section | Purpose | Guide |
| --- | --- | --- |
| Roam | Browse recommended images, give feedback, and anchor visual elements | [Roam](docs/guides/roam.md) |
| Generate | Generate images manually or in batches from presets | [Generate and Liked](docs/guides/images.md) |
| Liked | Browse the image grid, filter by tags, and sort by preference score | [Generate and Liked](docs/guides/images.md#tag-filters-in-liked) |
| Prompts | Browse the read-only library, edit presets, and preview co-occurrence expansion | [Prompts](docs/guides/prompts.md) |
| Settings | Manage general settings, roaming, backends, and task history | [Settings and cleanup](docs/guides/settings.md) |

### More help

- [LAN access and Home Screen app](docs/guides/access.md): mobile access and PWA support.
- [Backup and recovery](docs/guides/backup.md): data locations, backup, and restoration.
- [User documentation](docs/README.md#user-documentation): find a guide by task.

Pictide connects to ComfyUI, OpenAI Images, and Gemini native image generation as a standalone application. Cloud integration has been validated with protocol mocks; paid provider generation remains unverified. This support is available in the current source; existing portable builds need an update. This proof of concept currently has no separate user accounts, image-feature learning, or offline web caching.

## Developer documentation

- [Portable builds and validation (Chinese)](docs/dev/issues/automatic-startup.md): directory-based packaging, resource initialization, and platform validation.
- [Development workflow (Chinese)](docs/dev/development.md): source setup, builds, verification, and deployment. Start with [preparing a checkout (Chinese)](docs/dev/development.md#首次准备检出目录).
- [Architecture and module boundaries](docs/dev/architecture.md): responsibilities, dependencies, and call flows.
- [Corpus tools](docs/dev/corpus.md): library downloads, offline statistics, and processing records.
- [HTTP API reference](docs/dev/api.md): endpoints, request parameters, and responses.
- [UI design system (Chinese)](docs/dev/design-system.md): components, visuals, and interactions.
- [Developer documentation index](docs/dev/README.md): code entry points, storage reference, issue records, and design template.

## License

Pictide's original source code and documentation are licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for project attribution. Third-party components, fonts, model weights, datasets, and generated images retain their applicable licenses and rights; the project license does not grant additional rights to those materials.
