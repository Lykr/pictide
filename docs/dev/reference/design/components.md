# Component guidelines

[简体中文](../../../zh-CN/dev/reference/design/components.md)

[UI design system](../../design-system.md) · [Layout and interaction](layout.md)

## Buttons

| Variant | Use |
| --- | --- |
| `default` | Primary submission: generate or save |
| `secondary` | Secondary actions such as prompt preview |
| `outline` | Tools such as import, export, or connection test |
| `ghost` | Navigation, close, and low-emphasis tools |
| `destructive` | Explicit deletion or irreversible actions |
| `link` | Help and documentation |

Usually give each action area one primary button. Keep short labels for save, generate, and confirm. Use Lucide icons for familiar tools such as copy, refresh, close, sort, download, and image navigation; keep names alongside navigation icons. Loading shows the running action and prevents duplicate submission.

React icon buttons use `web/src/components/actions.tsx`'s `IconButton`, normally `ghost` / `icon-sm`, with a localized accessible name and tooltip. State changes update both accessible names and tooltips while preserving icons.

## Copy and contextual help

Show task titles, labels, values, short status, and necessary actions. Keep technical explanations and long background in topic documentation. Tooltips explain their own control in one or two sentences; field help, matching rules, source, sorting, and saving explanations belong to the relevant control. Empty states offer one short explanation and a next action.

Use shared `HelpTip` or `data-tooltip` support instead of permanent explanatory paragraphs beneath every input. Radix Tooltip serves both React controls. Hover or keyboard focus reveals help; help icons also accept click and Enter / Space, and Escape closes them. Help uses layer 1200 above image information at 1100, with mounting inside the active dialog when appropriate. Destructive scope and consequences remain discoverable through explicit controls or confirmation.

Unchanged page status, unsaved markers, and current progress stay with their controls. Transient results and detailed errors use notifications.

## Floating notifications

All errors, validation failures, save conflicts, and temporary results share `components/notifications.tsx`. React views and feature actions call `shared/notifications.mjs`; state-driven errors use `useErrorNotice()`.

Notifications sit at the viewport's upper right, respecting safe areas, theme, and locale. They preserve layout, scroll position, drafts, and input focus. Display at most three and merge repeated notices from the same source. Radix Toast provides close, swipe dismissal, F8 focus, and optional retry through the original business action.

Update-check results (up to date, a new version, or manual-update guidance) use this same notification layer only after a user check. Reading cached status or receiving background status events does not repeat the result. The current version, available update actions, and download/install progress stay with their controls.

Success and informational notices default to 4.5 seconds; errors and warnings to 10 seconds. Hover, keyboard focus, and window blur pause the timer. Mount into the active dialog or immersive container; use the native top layer where supported and fixed positioning otherwise. Notices remain interactive in fullscreen and dialogs, and errors preserve immersive mode.

Loading progress, unsaved markers, empty states, unavailable-image placeholders, and historical task error details remain page content. Roam keyboard and standalone swipe feedback keeps its brief icon/text acknowledgement over the image, including in immersive mode; failed feedback requests use error notifications. Other result messages use the shared notification layer rather than inserting banners or changing button labels.

## Forms and editing

General settings, application updates, and the data location use `components/settings-row.tsx`. Its stylesheet owns label/control columns, spacing, mobile stacking, and section separators. Callers provide labels and controls; use `stackOnMobile` for wide controls and `separated` for a new group. Keep state and save operations in the owning feature component.

Place labels above controls and associate them with `label` / `htmlFor`. Place help beside the label. Placeholders illustrate values rather than replacing names. Use 8–12px within compact groups and 16–24px between sections; help icons use `ghost` / `icon-xs`. Fields retain constraints, invalid state, and required focus behavior; detailed errors, including native validation errors, use shared notifications. Frontend input limits complement server validation.

Preset editing groups fixed positive terms with cooccurrence expansion. Negative terms live in a separate, initially collapsed shared Collapsible and save with the same preset. They affect generation and exclude matching expansion terms without participating in PMI calculations. Hidden and collapsed controls retain drafts.

Use one editable Command / Popover combobox for workflow selection and naming. Renaming preserves the selected ID; selecting a custom entry supplies a default name. Stored API keys appear as a fixed mask; clearing and saving removes the secret. Never return the real key to the browser.

Workflow node parameters occupy one panel. JSON mode replaces the parameter controls in that panel and shares their draft. Import replaces the same draft and updates valid bindings. Invalid JSON remains editable until corrected. Keep the JSON and import buttons beside the panel heading.

Show only fields needed by the selected random or continuous mode, retaining hidden drafts and shared controls. Fixed-term entry uses shared vocabulary search or complete free text, keyboard selection and Enter, with no extra add button. Exclude existing terms from suggestions, treat positive and negative matching separately, and preserve IME composition. Drag ordering and move controls remain available; saving persists the complete preset.

## Pagination and lists

Vocabulary, tasks, and preference lists use `components/page-controls.tsx`, normally 15 items per page. Center previous, page input, total pages, jump, and next controls below the list, using shared 32px Button / Input components. Enter or jump accepts an integer in range; disable unavailable directions and loading controls. Live refresh preserves the page input draft.

Continuous image browsing and Load more use cursor windows rather than numbered pages. Their internal window size is independent of list page size.

Cards group complete tasks or data areas. Use spacing and alignment within cards instead of repeated nested borders. Long names wrap or truncate with full text available. Vocabulary search preserves the query, page behavior, and focus. Task entries are initially collapsed, showing status, ID, and time; expanded content contains backend, seed, prompts, timestamps, errors, and cancellation. Refresh preserves expanded entries and current page; failed paging retains the list for retry.

Dialogs have a title, close action, and clear primary action. Long content scrolls internally while actions remain reachable. Keep Radix Dialog's Escape, focus trap, and return-focus behavior. Liked navigation shows its name and icon without a count.

## Image controls

Roam and the Generate/Liked large viewer use `components/image-toolbar.tsx`. Information, navigation/feedback, and optional trailing actions occupy named slots. `styles/image-toolbar.css` owns placement, touch sizes, and the immersive toolbar surface; page styles may position the toolbar within their card but must not redefine its slots, padding, or immersive appearance.

All large-view image information and immersive anchors use `ImageToolbarPopover`. In immersion it anchors to the entire toolbar, centers the panel above it, and shares width, surface, and opening/closing motion. Information remains available in Generate and Liked immersion as well as Roam. The normal Roam anchor editor retains its desktop split and compact mobile layouts.

Preserve aspect ratio in full image views and keep tools clear of important content. Loading, missing, cleaned-up, and failed images have distinct states. Place information at the lower left, Roam anchors at the lower right, and image navigation / feedback centered across the entire frame. Information includes preference score, seed, positive and negative prompts, copy actions, and prompt JSON download. Keep image counters, timestamps, and keyboard-hint icons out of the Roam bottom toolbar.

Roam supports like, dislike, and withdrawal; Generate and Liked large views support liking. Each page owns its image list and privacy state. See [layout and interaction](layout.md) for navigation, blur, immersive panels, anchors, and touch behavior.
