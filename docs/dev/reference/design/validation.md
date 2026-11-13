# UI development and validation

[简体中文](../../../zh-CN/dev/reference/design/validation.md)

[UI design system](../../design-system.md) · [Development workflow](../../development.md) · [Focused smoke checks](../../testing.md)

1. Before editing a shared interaction, list every consuming surface and intentional variation. For image controls this includes Roam, Generate, Liked, normal/immersive views, and mobile. Reuse `web/src/components/ui/` and the [shared feature layouts](components.md). Change common visuals in their owning stylesheet rather than adding page-specific overrides.
2. Preserve semantic targets, explicit actions, draft state, and save behavior. Keep component sizing, corners, padding, and focus rules in their shared layer.
3. In `web/`, install locked dependencies, run `pnpm run typecheck`, and build. For an active instance, use an isolated output directory and follow the [deployment procedure](../../development.md#integrate-and-deploy).
4. Run the small relevant UI, interface, or browser smoke group, then inspect affected interactions with an isolated instance and tab. Record whether testing used a simulated backend or real generation.
5. Check normal, loading, empty, error, disabled, selected, and unsaved states. Include keyboard focus, long text, narrow screens, dialog scrolling, and translated labels.
6. Preserve the user's drafts and data; close your verification instances and tabs afterward.

## Coverage by surface

For a new or changed surface, record its purpose, primary action, save/effect scope, feedback location, and empty/loading/error behavior in the owning design reference. Check intentional differences across its consumers. An implemented detail or a passing test is evidence to review, not a reason to make an accidental inconsistency the design rule.

| Surface | Design contracts to check | Representative browser evidence |
| --- | --- | --- |
| Roam, Single and Scroll | Current-image identity, motion continuity, waiting, pause/resume, anchor saves | `roam-playback`, `roam-scroll`, `anchor-suggestions`, `canvas-anchors` |
| Generate | Applicable fields, retained drafts, batch submission versus completion, result viewing | `generation-sizes`, `natural-prompts`, `layout` |
| Liked and recovery | Feedback versus selection, thumbnail/full-image roles, export scope, recovery and retained filters | `collection-appearance`, `thumbnails`, `liked-recovery` |
| Prompts | Read-only library versus editable arrangement, search/IME, unsaved work, preview hierarchy | `natural-prompts`, `anchor-suggestions` |
| General settings | Immediate preferences, session-only network effects, next-launch startup drafts, update progress | `first-use`, `local-generation`, `updates` |
| User data | Data location, archive transfer, preference review/reset, owned image cleanup | `user-data` |
| API and canvas configuration | Selection/new drafts, test versus save, credentials, conditional fields, size-row editing | `llm-connections`, `canvas-pools`, `react-forms` |
| History | Task paging, expanded details, current task status and cancellation scope | `smoke` |
| Guidance and shared overlays | Real action progress, dismissal/resume, target access, focus, locale, safe area | `smoke`, `first-use`, `layout`, `request-id` |

These names refer to `web/tests/browser/*.spec.mjs`; commands and further scenarios remain in [focused checks](../../testing.md). Screenshot review and interaction checks serve different purposes. Verify the states involved in the change rather than treating this table as a claim that every state was exercised in one audit.

## Layout regression baseline

`web/tests/browser/layout.spec.mjs` checks the real application at desktop, phone, and wide viewports with light/dark themes and English/Chinese labels. It asserts centered navigation, information-button placement, viewport-bounded panels, equal immersive panel widths and surfaces, focus return, reduced-motion behavior, aligned settings controls, and long-path wrapping. A separate scenario injects nonzero safe-area token values and checks the Generate/Liked frame through portrait/landscape rotation and entering/leaving immersion; desktop mobile emulation alone does not provide iOS device insets. It exercises Roam, Liked, and Generate with simulated generation.

These geometric and computed-style assertions are the portable baseline; they avoid OS-dependent font rasterization snapshots. Each run also attaches screenshots of anchors, information panels, and settings for visual review. Inspect the relevant screenshots after a shared layout change. A passing geometry check alone does not establish visual quality. Existing notification tests separately protect layout, scroll, and drafts during results and errors.

`design-consistency.spec.mjs` also checks narrow-screen Settings deep links, readable generation actions, label-to-control focus and retained drafts, pending connection feedback, stale test results, and configuration-save progress. Collection and Scroll checks compare like-state colors across their consuming surfaces; collection checks also verify that the normal large-view blur toggle matches the collection state and surface.

Run the focused baseline after the isolated build: `pnpm --dir web exec playwright test tests/browser/layout.spec.mjs`. The standard browser group includes it in release checks. Update the assertions only for an intentional design change, and review all consumers before accepting new behavior.

Keep layout ownership in React feature components and their styles. Feature models and actions supply data through explicit subscriptions and callbacks. Do not add property interception, hidden proxy inputs, or DOM observers to synchronize business state. Browser-only adapters may measure or focus elements, manage fullscreen, and position overlays through refs.

The only frontend entry is `web/index.html → web/src/main.tsx`. Prompts is the `#prompts` view in the same application. Navigation retains drafts and each section's position. HTTP serves APIs, events, and built assets.

Preset switching, deletion, and reload protect unsaved edits. Save follows the form's documented contract, including explicit retry on unchanged settings where applicable; field validation and pending-state checks remain in effect. Vocabulary loading is paged. Help explains PMI, minimum cooccurrence, fixed terms in total counts, and additions/removals in change budgets; preview shows actual stop reasons and sequence information.

Use [components](components.md) for controls and notifications and [layout](layout.md) for shell, responsive behavior, image panels, settings, keyboard, and touch acceptance. Keep exact token values and component behavior in source, and maintain each shared rule in its owning reference.

## LAN and Home Screen compatibility

Use `shared/request-id.mjs` for browser-generated request and configuration IDs. LAN HTTP and some Home Screen environments do not expose `crypto.randomUUID`; the helper uses `crypto.getRandomValues` to construct UUID v4 when needed. Keep an uncertain operation's existing ID on retry. The standalone browser smoke removes `randomUUID` and checks API creation, generation/retry, and preference reset; this is capability simulation, not a physical iOS test.
