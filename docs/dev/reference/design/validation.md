# UI development and validation

[简体中文](../../../zh-CN/dev/reference/design/validation.md)

[UI design system](../../design-system.md) · [Development workflow](../../development.md) · [Focused smoke checks](../../testing.md)

1. Reuse `web/src/components/ui/`. Change common behavior in shared components, common visuals in `theme.css`, and page layout in page files. React and dynamic DOM controls share the same recipes.
2. Preserve existing IDs, events, draft state, and save behavior. Keep component sizing, corners, padding, and focus rules in their shared layer.
3. In `web/`, install locked dependencies, run `pnpm run typecheck`, and build. For an active instance, use an isolated output directory and follow the [deployment procedure](../../development.md#integrate-and-deploy).
4. Run the small relevant UI, interface, or browser smoke group, then inspect affected interactions with an isolated instance and tab. Record whether testing used a simulated backend or real generation.
5. Check normal, loading, empty, error, disabled, selected, and unsaved states. Include keyboard focus, long text, narrow screens, dialog scrolling, and translated labels.
6. Preserve the user's drafts and data; close your verification instances and tabs afterward.

The only frontend entry is `web/index.html → web/src/main.tsx`. Prompts is the `#prompts` view in the same application. Navigation retains drafts and each section's position. HTTP serves APIs, events, and built assets.

Preset switching, deletion, and reload protect unsaved edits. Save is enabled only for valid changes. Vocabulary loading is paged. Help explains PMI, minimum cooccurrence, fixed terms in total counts, and additions/removals in change budgets; preview shows actual stop reasons and sequence information.

Use [components](components.md) for controls and notifications and [layout](layout.md) for shell, responsive behavior, image panels, settings, keyboard, and touch acceptance. Keep exact token values and component behavior in source, and maintain each shared rule in its owning reference.
