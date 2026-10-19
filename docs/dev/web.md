# Pictide Web

[简体中文](web.zh-CN.md)

Pictide's only browser entry point; npm package `pictide-web`. See the [User Guides](../README.md#使用指南) for product operations and the [API Index](api.md) for interfaces.

## Code Entry Points

Code paths in this section are relative to `web/` at the project root.

- `index.html` → `src/main.tsx`: the only React root. It mounts all workspaces, then initializes each business controller once.
- `src/feed.tsx`: application shell, sidebar, Roam, Generate, and categorized Settings pages.
- `src/editor.tsx`: React-managed workspaces for read-only libraries, generation presets, and previews; no separate page entry point.
- `src/controllers/`: browser state, events, and API calls. The backend Candidate module handles preset validation, co-occurrence expansion, and continuous generation within a budget.
- `src/components/ui/`, `src/styles/theme.css`: shared shadcn/ui components and design tokens. See [Design Guidelines](design-system.md).

The React shell and existing DOM controllers manage presentation and drafts. Controllers initialize only once per page lifecycle. The shared control layer integrates official shadcn/Radix components through portals, maintaining a single React root. Hidden form-state interfaces bridge legacy controllers and must not appear as visible native controls. New features reuse this layer without creating separate page entry points or a React root per control.

## Pages and State

Internal routes are `#feed`, `#generate`, `#liked`, `#prompts`, and `#settings/general|roam|backend|history`. Task records live in Settings' History section, with no separate Tasks section.

The React page shell and controllers jointly maintain drafts. Image windows distinguish Generate and Roam by source; Liked spans sources. The backend saves the viewing position. The UI does not access files, SQLite, or Python modules directly; business algorithms run in the backend.

`components/generated-results.tsx` and `generated-viewer.tsx` manage the Generate/Liked grids and full-size viewer. The roam controller manages the current image, prefetch, and autoplay; `components/page-controls.tsx` manages ordinary pagination. The [Image API](reference/api/images.md) defines source, count, and feedback semantics.

The entire application shares one `/api/events` EventSource. Existing polling fallback remains on disconnection; switching sections does not create a second connection. Candidate uses `/api/candidate/tags|presets|dataset|generate|relations`; see the [Candidate API](reference/api/candidate.md) for methods and fields.

## Build

Run `pnpm install --frozen-lockfile`, `pnpm run typecheck`, and `pnpm run build` in `web/`. The [Development Workflow](development.md) defines initial setup, validation, and release order. Do not clear dist directly in a directory currently serving pages.

Builds use dependencies under the project root's `dev/runtime/frontend/` and caches under `dev/cache/`. `web/node_modules` points to the actual dependencies, and `web/dist` contains distribution assets. Node.js is used only for builds; the Python host serves `/static/ui/` at runtime.

## Further Reading

- [Shared Components, Theme, and Page Guidelines](design-system.md)
- [Module Boundaries](architecture.md)
- [Image Operations and Keyboard Shortcuts](../guides/roam.md#浏览与自动播放)
- [Third-Party Component Notices](../../web/src/THIRD_PARTY_NOTICES.md)
