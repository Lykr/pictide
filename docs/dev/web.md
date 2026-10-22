# Pictide Web

[简体中文](../zh-CN/dev/web.md)

Pictide's only browser entry point; npm package `pictide-web`. See the [User Guides](../README.md#guides) for product operations and the [API Index](api.md) for interfaces.

## Code Entry Points

Code paths in this section are relative to `web/` at the project root.

- `index.html` → `src/main.tsx`: the only React root. It creates one application session and provides it through `shared/application-context.tsx`. Mounting binds browser listeners and SSE; unmounting releases them.
- `src/feed.tsx`: application shell, navigation, and Roam. `src/features/` contains the controlled Generate, Image API, Roam settings, and History forms.
- `src/editor.tsx`: React-managed workspaces for read-only libraries, generation presets, and previews; no separate page entry point.
- `src/shared/notifications.mjs`, `src/components/notifications.tsx`: the shared floating notification layer for errors and operation results; behavior is defined in the [component guidelines](reference/design/components.md#floating-notifications).
- `src/controllers/`: browser state, events, and API calls. The backend Candidate module handles preset validation, co-occurrence expansion, and continuous generation within a budget.
- `src/controllers/app.js`: composes the page controllers and coordinates navigation, galleries, Roam, and realtime refresh. `backend-settings.js` owns Image API/workflow drafts and save/test actions; `generation-controller.js` owns the Generate form, prompt counters, and uncertain submissions. `components/job-history.tsx` renders task records from the pager state.
- `src/components/ui/`, `src/styles/theme.css`: shared shadcn/ui components and design tokens. See [Design Guidelines](design-system.md).

React owns page markup and controlled inputs. Feature services store ordinary draft data in small observable models (`shared/model.mjs`); `useModel` subscribes with `useSyncExternalStore`. Actions accept values and return results or promises. Use shared shadcn/Radix components directly; do not introduce hidden proxy controls, native property interception, or DOM-based business-state synchronization.

`shared/ui-state.mjs` retains immutable UI facts for the tour and shared views, with explicitly bound application commands for cross-feature actions. `shared/signals.mjs` carries lifecycle invalidations such as theme or library changes. Persistent data belongs in models/facts, not transient events. DOM refs remain appropriate for browser capabilities: focus, measurement, scrolling, fullscreen, image animation, and file selection.

Frontend unit checks live in `web/tests/unit/`; real-page checks and fixtures live in `web/tests/browser/`. Their temporary Python service is `tests/browser_server.py`. See [focused smoke checks](testing.md) for the shared entry points.

## Pages and State

Internal routes are `#feed`, `#generate`, `#liked`, `#prompts`, and `#settings/general|roam|backend|history`. Task records live in Settings' History section, with no separate Tasks section.

Each feature model owns its draft; React views remain mounted across navigation. Server refreshes update service data without replacing unsaved drafts. Image windows distinguish Generate and Roam by source; Liked spans sources. The backend saves the viewing position. The UI does not access files, SQLite, or Python modules directly; business algorithms run in the backend.

`components/generated-results.tsx` and `generated-viewer.tsx` manage the Generate/Liked grids and full-size viewer. The roam controller manages the current image, prefetch, and autoplay; `components/page-controls.tsx` manages ordinary pagination. The [Image API](reference/api/images.md) defines source, count, and feedback semantics.

The entire application shares one `/api/events` EventSource. Existing polling fallback remains on disconnection; switching sections does not create a second connection. Candidate uses `/api/candidate/tags|presets|dataset|generate|relations`; see the [Candidate API](reference/api/candidate.md) for methods and fields.

## Build

Run `pnpm install --frozen-lockfile`, `pnpm run typecheck`, and `pnpm run build` in `web/`. The [Development Workflow](development.md) defines initial setup, validation, and release order. Do not clear dist directly in a directory currently serving pages.

Builds use dependencies under the project root's `dev/runtime/frontend/` and caches under `dev/cache/`. `web/node_modules` points to the actual dependencies, and `web/dist` contains distribution assets. Node.js is used only for builds; the Python host serves `/static/ui/` at runtime.

Compiled JavaScript and CSS filenames include content hashes, and the HTML entry is revalidated with `Cache-Control: no-cache`. Publish new assets before the HTML entry and retain previous assets for pages still using the old build. Already-open pages keep their current code until reloaded; Home Screen apps may need to be fully closed and reopened after deployment.

## Further Reading

- [Shared Components, Theme, and Page Guidelines](design-system.md)
- [Module Boundaries](architecture.md)
- [Image Operations and Keyboard Shortcuts](../guides/roam.md#browsing-and-autoplay)
- [Third-Party Component Notices](../../web/src/THIRD_PARTY_NOTICES.md)
