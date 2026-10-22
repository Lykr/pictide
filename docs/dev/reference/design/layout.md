# Layout and interaction

[简体中文](../../../zh-CN/dev/reference/design/layout.md)

[UI design system](../../design-system.md) · [Components](components.md)

## Application shell

Ordinary pages share `.workspace-content`: centered, at most 1200px wide, with 24px desktop padding and 16px at widths up to 1024px. Roam and Prompts share the same horizontal boundaries. Reserve scrollbar space to avoid jumps between sections. The desktop sidebar is 144px wide with short names and icons; narrower layouts adapt navigation rather than widening it on large screens.

Desktop and standalone windows use a fixed `100dvh` shell with independent section scrolling. Keep navigation visible, retain each section's scroll position, and place headings above scrolling content. Leave 16px after scrolling content, or 8px on narrow screens, including internal prompt areas. Flex and Grid columns use `min-width: 0`; long paths, IDs, and prompts wrap or scroll within their own region.

| Viewport | Layout |
| --- | --- |
| Above 1024px | Desktop columns with flexible primary content |
| 768–1024px | Tighter spacing and fewer simultaneous secondary panels |
| 640–768px | Stack primary panels; allow horizontal navigation |
| Up to 640px | Single-column forms and fixed five-item bottom navigation |

Phones show Roam, Generate, Liked, Prompts, and Settings in a 48px bottom navigation row, plus the safe area. The top content row is 44px, or 40px in landscape. Ordinary iPhone WebKit browsers use document scrolling with a sticky header and fixed bottom navigation; save and restore document scroll per section. Dialogs and immersive mode lock the document. Browser chrome collapse depends on genuine user scrolling and content height; avoid blank spacers or artificial scrolling.

Standalone windows hide the Pictide brand bar, retain the top safe area, and use section titles for orientation. Dialogs, menus, and immersive views retain their own scrolling behavior.

## Roam

The upper-right tools are Play / Pause, Blur, Immersive mode, and Roam options, using shared 32px controls. Playback includes its timing ring. Options explain the function of display interval, preference scope, roam mode, and recommendation strength briefly. Use a shared Popover and ToggleGroup controls. The popover sizes to content with a normal 320px minimum, constrained by the viewport and Radix available width, with at least 12px outer clearance. Narrow layouts allow whole option groups to wrap.

The display interval label and seconds InputGroup share a row; Enter or blur saves it. Roam settings and the popover share saved configuration without overwriting unrelated drafts. Changes to scope, mode, backend, or active candidate preset pause automatic advance and obsolete window merging; reread the revised window after saving, then restore playback intent. Failed changes retain the current selection and image. Background prefetch does not repeatedly notify about an empty liked-term pool.

Restore the last viewed Roam image independently of Liked. While its initial or refreshed window loads, keep the viewing position rather than selecting the latest image. Read contiguous windows around the current image; load adjacent windows when crossing boundaries. The older boundary stops quietly. At the newer boundary, demand generation only through the existing operation and event path, retain the current image, and advance once when ready. Repeated input does not submit duplicate work. Leaving Roam or browsing backward cancels UI waiting; submitted work may finish. Failures end loading and show a useful notification.

Normal Roam waiting uses a 16px spinner beside the heading without an image-covering mask. Immersive loading has its own indicator below.

## Privacy and image browsing

Blur defaults on at page initialization and applies from the first image paint. It affects the image rather than tools, errors, or progress. Keep blur state while navigating within the page; refresh restores protection. Roam and Generate maintain separate states, and each page synchronizes its toolbar and large-view controls.

Space toggles the active image area's blur in Roam, Generate results, and large views. Tooltips and `aria-keyshortcuts` expose the shortcut. Ignore editable inputs, dialogs with their own handling, modifiers, and repeated keydown. Prevent accidental scrolling or feedback activation, and avoid double handling in large views.

Image information uses the same field layout across Roam, Generate, and Liked: preference score, seed, positive prompt, and negative prompt. Each copyable field has a heading and right-aligned copy tool above softly filled monospace content. Disable copying unavailable seeds or empty prompts. Long text scrolls internally and wraps on narrow screens. Prompt JSON download sits beside the panel title. Scores use one decimal and distinct loading, unavailable, and undifferentiated states; raw score and relative-scale explanations belong in help. See [image scores](../api/images.md#like-filters-and-image-preference-scores).

Clipboard helpers prefer the Clipboard API and fall back to browser copy commands for ordinary LAN HTTP. Preserve selectable text when copying fails; operation results use [notifications](components.md#floating-notifications).

## Generate and Liked

Generate places the form beside independent results on desktop and stacks them on narrow screens. Cooccurrence preset and draw mode share two columns; preset refresh sits in its label row. Pair seed or sequence values with their post-generation behavior. Keep advanced search settings collapsed and retain drafts for hidden modes. Batch size and generation count are bounded integers from 1 to 10, initially 1. Help explains per-round prompts, within-round sharing, cross-round seeds, sequential execution, and workflow outputs.

Generate's cancel-pending action only cancels that page's queued work. Submission and cancellation disable each other. Generation progress remains in results and task history; submitting successfully means a task was accepted. Transient results and errors use the shared notification layer.

Generate and Liked share a compact responsive thumbnail grid and large-image viewer, with separate data and blur state. Thumbnail images use centered `cover`; full images use `contain`. Like controls appear on hover or focus and stay visible on touch devices. Thumbnails omit permanent seed and tool rows. Results tools offer blur and clear; clearing explains which unliked images are deleted and which liked images only leave Generate.

Large views use a shared Dialog with previous, like, and next controls centered; information sits at the lower left, and blur sits beside the upper-right close action. Full image downloads are absent; information retains prompt JSON download. Preserve the image during pagination waits and cache rereads; close only when no image remains. Escape exits immersive mode before closing the viewer.

The Generate/Liked dialog frame is sized and centered inside the viewport minus its four safe-area insets; internal padding is not a substitute for keeping the frame above the Home indicator. Shared `--safe-area-*` tokens read the browser's device insets. Rotation recalculates the safe rectangle. Immersive images may fill the viewport, while floating controls remain inside the safe area.


Liked offers Latest / Preference score sorting and a searchable multi-select tag filter above the grid. The tag filter shows matching liked-image counts, supports individual removal and clear, and scrolls independently. Default tag order is alphabetical; count order is descending with alphabetical ties. Preference-score mode offers manual refresh beside blur, with the last successful refresh time in its tooltip. Use neutral Load more wording. Removing a like uses the shared confirmation dialog. Liked omits generation configuration and task controls.

## Prompts

Vocabulary selection, upload, and refresh form one management row; full-width tag search follows. Keep controls grouped on narrow screens, constrain long filenames, and page the read-only vocabulary rather than mounting it all.

Preview follows controls → result → collapsed report. Group prompt seed and post-generation behavior, and separately group continuous-frame position and its behavior. Keep advanced search limits collapsed. Status, seed, and continuous-change information appear above results. Positive and negative prompts have soft backgrounds and aligned copy actions; short results do not reserve a fixed empty area.

Positive terms support PMI and cooccurrence inspection through the shared Tooltip on hover, keyboard focus, or touch. Related-term highlighting affects positives only. Use anchor emphasis, success styling for positive associations, warning styling for negative associations, destructive dotted styling for relationships absent from the retained library, and muted dotted styling for unknown terms. Show numerical statistics or the reason they are unavailable; a negative PMI is an association value rather than a conflict verdict. Negative prompts remain plain text with copy support.

## Settings

Use General, Roam, Image API, and History tabs under a single Settings heading. Forms share a 780px content width, `.settings-field`, and `.settings-stack`: label rows at least 24px high, 8px to controls, 16px between related fields, and 24px between sections. Two-column groups stack on narrow screens. Default Input / Select height is 36px; units use InputGroup. Place save actions at the lower right and connection tests at the left.

General uses aligned rows for language, theme, image transitions, onboarding, and data location. Show only the data directory path with a soft background and monospace body text; wrap long paths and stack label/value on narrow screens. Avoid nested decorative cards.

Roam includes prefetching, history limit, backend, playback, preference scope, mode, and recommendation strength. The active prompt preset is selected on Prompts rather than duplicated in Settings. History limit is an integer from 0 to 100000, initially 0; help explains disabled limits, older-image counting, exclusion of current/prefetched images, oldest-first pruning, deletion of unliked local images/JSON, and retention of liked images outside Roam.

Image API uses one editable workflow selection/name control. Node parameters use a shared, initially collapsed Collapsible, reset to collapsed when switching backends. Opening the heading remains visually light. JSON, import, loading defaults, and validation errors expand it as needed. Preserve all drafts while collapsed; group fields by node, with single fields full-width and multiple fields in two columns. Input bindings and output selection stack on narrow screens.

History combines task records with initially collapsed image cleanup. Keep task pagination at 15 items and preserve mounted forms across tabs. The sidebar has no independent tasks entry. The top-level availability indicator reflects read-only checks of saved backends at configuration load/save rather than periodic probing. Global Settings uses Lucide Settings; Roam options uses Settings2.

## Immersive views and anchors

Prefer the Fullscreen API and fall back to filling the browser viewport. Reuse the current image and controls, preserving its aspect ratio, blur, and loading behavior. The upper-right menu contains blur and exit; Roam also includes Play / Pause with its progress ring. The compact bottom toolbar contains image navigation and feedback, plus information and Roam anchors where applicable.

Hide idle controls after about two seconds. Mouse movement or a short touch tap wakes them; hover or keyboard focus keeps them visible. Direction keys and Space hide controls immediately, without navigation or focus changes waking them again. Hidden controls leave pointer, Tab, and accessibility interaction; Tab first wakes the toolbar. Touch swipes, multi-touch, and cancelled gestures do not wake menus. Escape, leaving Roam, or leaving the page cleans up immersive state and returns focus to the entry. Errors stay in the shared notification layer while retaining the view.

Roam normal-mode anchors open in the same image card. Desktop uses image left / anchors right, with a draggable separator whose ratio is saved locally and supports arrow keys and Home / End. Opening and closing preserve image/card height; dragging changes only the width ratio. Phones stack the compact editor beneath the image: normally 112px capped at 25dvh, or 156px capped at 32dvh while adding a term. Adding collapses the entry. Terms scroll independently; hide redundant heading, count, and help on phones, with lock icons identifying fixed terms.

Immersive information and anchors use matching-width floating panels centered above the bottom toolbar, opening upward from the toolbar and closing downward with matching opacity. The image remains fullscreen. Panels share draft and save behavior with normal mode, preserve editing while navigating images, and keep controls visible while open. Opening immersive anchors replaces the information panel; closing returns focus. Escape closes the panel first. Editor input and touch interactions do not trigger image shortcuts or gestures. See the [Roam anchor guide](../../../guides/roam.md#anchors) for behavior.

Immersive loading has an upper-left ring independent of menu visibility. Roam covers next-image waiting and image reads; Generate / Liked cover image and pagination reads. End the indicator on success or failure, respecting reduced motion.

## Keyboard and touch

All controls remain reachable by keyboard with visible `focus-visible` rings. Image containers receive programmatic focus for shortcuts without showing an outer selection border; internal buttons, inputs, and separators retain focus indicators.

Left / Right browse images. Roam Up / Down move feedback one step through dislike ↔ unrated ↔ like, stopping at the ends and ignoring key repeat. Buttons select or withdraw their feedback directly. Generate / Liked large views use Up to like and leave Down unassigned. Inputs, editable regions, selects, and dialogs retain their own key handling.

Single-finger horizontal swipes in the image area browse without changing feedback; vertical starts, pinches, and control clicks do not. Standalone Roam Up / Down swipes use the same one-step feedback rule. Ordinary browser scrolling remains available. Roam keyboard and standalone swipe feedback briefly shows a centered icon and label near 68% image height for about 900ms, in both ordinary and immersive views. This acknowledgement includes withdrawals, remains separate from upper-right notifications, and does not intercept touches or wake controls. Failed requests use error notifications and do not show success. Changing images clears the acknowledgement; reduced motion retains a static message.

Phone image frames use a two-row Grid with an explicitly bounded, absolutely positioned image region. Use one flexible column, symmetric safe-area margins, centered `contain`, rounded clipping, and a light border. Standalone Roam fills remaining height; ordinary browsers use a 2:3 frame capped at 72svh. Toolbars sit outside the ordinary image region with symmetric flexible side columns so information and anchors do not displace centered navigation. Narrow/touch controls have at least 44×44px targets; text and numeric inputs use 16px to reduce focus zoom while retaining user scaling. Phone grids retain two thumbnail columns.

## Standalone metadata and localization

`web/public/manifest.webmanifest` defines identity, root scope, and `/#feed` startup, served through `/static/ui/`. `web/index.html` supplies the manifest, iOS standalone metadata, and touch icon. Bundled 180 / 192 / 512 icons share the official P outline and opaque background. Keep scope and startup at the application root. Theme changes update `theme-color`. The current application registers no Service Worker and still connects to the running Pictide service.

React and DOM controllers share `web/src/i18n/index.mjs`'s `t` / `tr`. Simplified Chinese source strings are keys; English messages are grouped under `messages/en/`. Named or positional placeholders allow translated word order. Default locale follows the browser; unsupported languages use English, and manual selection takes precedence. User content, actual prompts, tags, and technical model/workflow identifiers remain literal. Dates and numbers use the selected locale; switching language preserves values and page state.

Image changes can use the shared approximately 180ms opacity transition. Initial images, same-image feedback, and ordinary redraws do not animate; toolbars and blur remain unaffected. Respect the General setting and reduced-motion preference, cancelling a previous transition during rapid navigation.
