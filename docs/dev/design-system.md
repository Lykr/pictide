# UI design system

[简体中文](../zh-CN/dev/design-system.md)

[Developer documentation](README.md) · [Development workflow](development.md)

Keep browsing and guiding images simple. Use compact controls, a clear hierarchy, and progressive disclosure so images remain the focus across Roam, Generate, Liked, Prompts, and Settings.

## Shared foundation

The [shadcn preset](https://ui.shadcn.com/create?preset=b1VlIttI) uses Radix, Luma, Neutral, Inter, and Lucide. Its configuration lives in `web/shadcn-preset.json` and `web/components.json`. Reuse `web/src/components/ui/`; shared tokens and recipes belong in `web/src/styles/theme.css`. Page styles own layout and business presentation.

| Topic | Reference |
| --- | --- |
| Theme, typography, spacing, and state colors | [Visual foundation](reference/design/visual.md) |
| Controls, help, notifications, forms, and lists | [Components](reference/design/components.md) |
| Pages, responsive behavior, image controls, and accessibility | [Layout and interaction](reference/design/layout.md) |
| Implementation and verification | [Development and validation](reference/design/validation.md) |

## Product terminology

Vocabulary tags are complete labels from the dataset. Ratings are `general`, `sensitive`, `questionable`, and `explicit`; the interface does not invent separate author, character, or work categories. A preset combines fixed positive terms, negative terms, and cooccurrence settings over a read-only SQLite vocabulary. Prompts groups vocabulary, composition, and preview; it does not expose an editable tag library or slot solver.

Blocked keywords use a shared Textarea, one per line. Preserve editing line breaks; normalize and deduplicate on save. Matching is case-insensitive substring matching with equivalent spaces and underscores. Blocking affects newly drawn terms, not fixed terms, negative terms, or retained terms.

Fixed terms support search, free text, keyboard selection, removal, and ordering by drag handle or move controls. Enter adds a selected or complete term, while IME composition remains editable. Adding a term clears the entry. Unknown free text is allowed and contributes no vocabulary cooccurrence statistics. Term badges distinguish vocabulary and free-text states using normalized exact matching; loading and unresolved states remain distinct. Reuse the existing related-term data rather than adding a second query contract.

## Implementation

React, TypeScript, Tailwind, and shared shadcn components serve the single `web/index.html → web/src/main.tsx` entry. The React shell and existing DOM controllers share component recipes through `dom-primitives.ts`. Preserve controller IDs, event wiring, drafts, and save behavior when changing presentation.

Visible Select, Checkbox, Radio, Toggle, Dialog, and Collapsible controls use the shared Radix components. Hidden native controls may bridge controller state. Preserve keyboard focus, disabled states, form constraints, and validation.

Node.js is a development and build dependency. Runtime serves built assets through aiohttp, with bundled fonts and no CDN or Node process. Third-party notices live in `web/src/THIRD_PARTY_NOTICES.md`.

Before adding a primitive, check the shared library and official shadcn Vite instructions. Apply preset changes in an isolated checkout, review the diff, and retain dynamic DOM recipes. Use the pinned pnpm version and commit its lockfile. Follow the [development workflow](development.md) for builds and publishing assets.
