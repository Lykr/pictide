# Visual foundation

[简体中文](../../../zh-CN/dev/reference/design/visual.md)

[UI design system](../../design-system.md) · [Development workflow](../../development.md)

Use the shared Neutral theme, Luma pill buttons, and softly filled inputs. Light and dark modes share semantic tokens. Settings → General offers System, Dark, and Light through a shared single-selection ToggleGroup. Read the saved selection before mounting; System follows `prefers-color-scheme`. Persist the selection in application SQLite, with no second browser-storage copy. Pages and overlays inherit the root theme.

| Element | Convention |
| --- | --- |
| Body text | 14px, approximately 1.5 line height; supporting text 12px |
| Headings | Page 20px, section 16px, card or field group 14px; use weight for hierarchy |
| Fonts | Bundled Inter Variable, system fallback for Chinese; shared monospace token for code, IDs, and literal prompts |
| Spacing | 4px scale: 4 / 8 / 12 / 16 / 24 / 32px |
| Control height | Default 36px; explicitly use `sm` at 32px for secondary actions |
| Corners | Keep each Luma component's recipe rather than forcing a single radius |
| Borders and shadows | 1px section boundaries; light overlay shadows; restrained card shadows |
| Motion | Short hover, focus, state, and navigation transitions; respect reduced motion |

Use [semantic theme tokens](https://ui.shadcn.com/docs/theming); source code owns exact values.

| Token | Purpose |
| --- | --- |
| `background` / `foreground` | Page and primary text |
| `card` / `card-foreground` | Cards and panels |
| `popover` / `popover-foreground` | Overlays |
| `primary` / `primary-foreground` | Primary action |
| `secondary` / `secondary-foreground` | Secondary actions and containers |
| `muted` / `muted-foreground` | Supporting information and placeholders |
| `accent` / `accent-foreground` | Hover and selection |
| `border` / `input` / `ring` | Separators, form boundaries, and keyboard focus |
| `destructive` | Errors and destructive actions |
| `success` / `warning` | Success and warning states |
| `favorite` / `favorite-surface` | Personal likes, their controls, and attached image markers |

Pair status colors with text or icons. Shared state styles distinguish success, waiting, error, disabled, and selected states. Page CSS reuses these tokens.

## Image surfaces and visual meaning

Treat the image as the primary surface. Frames, controls, and surrounding panels establish boundaries without competing with it. Thumbnail crops and full-image containment serve different browsing needs; their rules belong in [layout and interaction](layout.md#generate-and-liked). A displayed frame size must not imply that the stored original was resized.

Clip image content and blur to the frame's shape. Keep borders, selection marks, loading states, and feedback outside the blurred content so they remain legible. Avoid edge gaps, corner bleed, and page-specific border or shadow overrides of shared viewers.

Preference, selection, progress, and destructive actions carry different meanings. A heart identifies a personal preference; a checkbox identifies export selection; an error color identifies a problem. Use icon shape and state as well as color. Feedback accents should come from a shared theme recipe, with light and dark variants, rather than unrelated page-local constants.

Liked hearts share the `image-like` recipe across Roam, thumbnails, and large views. Scroll outlines and attached hearts use the same favorite tokens. Image overlays retain a legible surface; export selection remains neutral and error/deletion colors remain destructive.

Separate decorative motion from playback. Same-image feedback and background refresh do not start an image transition. A running transition preserves its position and progress when data updates. Reduced motion removes decorative effects; deliberate Scroll playback remains an explicit Play/Pause interaction with Single playback available as an alternative.
