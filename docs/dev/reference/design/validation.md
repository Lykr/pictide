# UI development and validation

[简体中文](../../../zh-CN/dev/reference/design/validation.md)

[UI design system](../../design-system.md) · [Development workflow](../../development.md) · [Focused smoke checks](../../testing.md)

1. Before editing a shared interaction, list every consuming surface and intentional variation. For image controls this includes Roam, Generate, Liked, normal/immersive views, and mobile. Reuse `web/src/components/ui/` and the [shared feature layouts](components.md). Change common visuals in their owning stylesheet rather than adding page-specific overrides.
2. Preserve existing IDs, events, draft state, and save behavior. Keep component sizing, corners, padding, and focus rules in their shared layer.
3. In `web/`, install locked dependencies, run `pnpm run typecheck`, and build. For an active instance, use an isolated output directory and follow the [deployment procedure](../../development.md#integrate-and-deploy).
4. Run the small relevant UI, interface, or browser smoke group, then inspect affected interactions with an isolated instance and tab. Record whether testing used a simulated backend or real generation.
5. Check normal, loading, empty, error, disabled, selected, and unsaved states. Include keyboard focus, long text, narrow screens, dialog scrolling, and translated labels.
6. Preserve the user's drafts and data; close your verification instances and tabs afterward.

## Layout regression baseline

`web/tests/browser/layout.spec.mjs` checks the real application at desktop, phone, and wide viewports with light/dark themes and English/Chinese labels. It asserts centered navigation, information-button placement, viewport-bounded panels, equal immersive panel widths and surfaces, focus return, reduced-motion behavior, aligned settings controls, and long-path wrapping. It exercises Roam, Liked, and Generate with simulated generation.

These geometric and computed-style assertions are the portable baseline; they avoid OS-dependent font rasterization snapshots. Each run also attaches screenshots of anchors, information panels, and settings for visual review. Inspect the relevant screenshots after a shared layout change. A passing geometry check alone does not establish visual quality. Existing notification tests separately protect layout, scroll, and drafts during results and errors.

Run the focused baseline after the isolated build: `pnpm --dir web exec playwright test tests/browser/layout.spec.mjs`. The standard browser group includes it in release checks. Update the assertions only for an intentional design change, and review all consumers before accepting new behavior.

Keep layout ownership in React feature components and their styles. Existing DOM controllers may still supply business state and actions; new layout components should not add property interception or another DOM observer. Remove obsolete DOM writes when their presentation is retired, and migrate remaining bridges incrementally when touching the owning feature.

The only frontend entry is `web/index.html → web/src/main.tsx`. Prompts is the `#prompts` view in the same application. Navigation retains drafts and each section's position. HTTP serves APIs, events, and built assets.

Preset switching, deletion, and reload protect unsaved edits. Save is enabled only for valid changes. Vocabulary loading is paged. Help explains PMI, minimum cooccurrence, fixed terms in total counts, and additions/removals in change budgets; preview shows actual stop reasons and sequence information.

Use [components](components.md) for controls and notifications and [layout](layout.md) for shell, responsive behavior, image panels, settings, keyboard, and touch acceptance. Keep exact token values and component behavior in source, and maintain each shared rule in its owning reference.
