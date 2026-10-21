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

Pair status colors with text or icons. Shared state styles distinguish success, waiting, error, disabled, and selected states. Page CSS reuses these tokens.
