# <img src="web/public/icons/pictide.svg" alt="" width="36" height="36" /> Pictide

[简体中文](README.zh-CN.md)

**A world of images unfolds as you roam.**

![Pictide roaming demo](docs/assets/roam.gif)

New images are generated along the way, guided by your feedback and anchors.

Pictide is a local generative image exploration app that gradually adapts to your preferences through feedback. No need to write prompts by hand or start with a specific creative goal—begin by browsing images, express what you like, and guide what comes next. Images and preferences are saved on your computer. [About Pictide](docs/guides/about.md).

## User guide

### Quick start

1. Extract the portable package and run its launcher: [Windows](docs/guides/setup/windows.md#portable-edition) · [Linux](docs/guides/setup/linux.md#portable-edition) · [macOS](docs/guides/setup/macos.md#portable-edition). The first launch downloads the recommendation model, then opens your browser when ready.
2. In **Settings → Image API**, connect ComfyUI or enter an OpenAI Images / Gemini API key and model. See [Installation and connections](docs/guides/getting-started.md).
3. Open **Roam** and select **Start roaming**. Browse, express preferences, and use anchors to guide what comes next.

The package includes a default vocabulary and stores personal data in its `data/` directory. For running from source, offline preparation, or another vocabulary, choose a guide in the [user documentation](docs/README.md).

### Feature overview

| Section | Purpose | Guide |
| --- | --- | --- |
| Roam | Discover images you enjoy and guide what comes next | [Roam](docs/guides/roam.md) |
| Generate | Turn a specific idea into images | [Generate](docs/guides/generate.md) |
| Liked | Revisit favorites and find the images you want | [Liked](docs/guides/liked.md) |
| Prompts | Keep a favorite style and adjust image concepts | [Prompts](docs/guides/prompts.md) |
| Settings | Connect a generation service and manage preferences and data | [Settings and cleanup](docs/guides/settings.md) |

### More help

- [LAN access and Home Screen app](docs/guides/access.md): mobile access and PWA support.
- [Backup and recovery](docs/guides/backup.md): data locations, backup, and restoration.
- [User documentation](docs/README.md#user-documentation): find a guide by task.

Pictide is a proof of concept. See the [setup guide](docs/guides/getting-started.md) for current service and platform support.

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
