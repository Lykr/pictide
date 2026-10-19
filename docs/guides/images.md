# Generation and Liked Images

[简体中文](images.zh-CN.md)

[Documentation](../README.md) · [Task API](../dev/reference/api/jobs.md) / [Image API](../dev/reference/api/images.md)

Generate stores manual and preset-based generation results, Roam displays prefetched recommendations, and Liked brings together liked images from both sources.

## Batch generation and seeds

On Generate, set Images per round and Generation rounds separately (both `1`–`10`, default `1`). For example, 2 images per round and 3 rounds create 3 rounds containing 6 independent tasks in one submission, executed in the existing queue order. With automatic candidate generation enabled, each round draws fresh prompts and updates the candidate seed and sequence frame according to the after-generation controls; tasks within the same round share its positive and negative prompts. Fixed controls stay unchanged. Manual text, or disabling automatic drawing, reuses the current text in each round. The tag library and backend configuration are frozen on submission; later edits do not change queued tasks.

For ComfyUI workflows with seed support, image seed `-1` gives each task an independent random seed. With an explicit seed, images increment it one by one across rounds and safely wrap at the seed limit. After successful submission, the input shows the next seed. Workflows without a seed binding continue using their own settings. All rounds enter the local task queue together. Closing the page does not stop submitted tasks; after an application restart, queued tasks can continue, while recovery of requests already sent depends on the backend. OpenAI Images and Gemini do not support deterministic image seeds or negative prompts. Use an empty negative prompt or preset and let the service control image randomness; the local candidate seed still controls prompt selection. An uncertain cloud submission is not automatically sent again, and each new generation request may incur provider charges. Candidate generation failure or insufficient remaining queue capacity rejects the entire batch. The queue holds at most 100 pending tasks, with capacity shared across submissions.

The count means generation requests (ComfyUI workflow executions): a default single-image workflow run N times yields N images. If a custom workflow returns multiple images per run, all outputs are retained and the final image count can exceed N. The entire batch is queued together after capacity and idempotency checks; insufficient capacity creates no partial tasks. Network retries reuse the original request ID and full batch input.

## Browsing and preference scores

Generation results are browsed and rated in a separate image area on Generate, outside the roaming list and roaming buffer count. Roam only shows outputs of recommendation prefetch tasks; Liked includes liked images from every source. Liked uses the same thumbnail grid as Generate, with Newest / Preference score sorting. Score sorting covers all filtered results: higher scores first, ties by time, and unscorable images last, shown in batches of 100. Entering score sorting or changing filters reuses cached scores. Only a manual refresh recomputes the current filtered results, and order stays fixed while browsing. Computation reuses cached preference weights and deduplicates identical prompt combinations. See [score sorting (Chinese)](../dev/issues/liked-score-sort.md). Click an image to open the enlarged view, with previous/next navigation, image information, an independent blur overlay (on by default, toggled with Space), and immersive mode. Hovering or focusing a thumbnail reveals the unlike button; unliking still requires confirmation. Liked does not offer Clear generation results. Older manually generated images are placed in Generate, preserving their images, prompts, and ratings under the shared history cleanup settings.

## Enlarged view controls and privacy

Generation results use a thumbnail grid. Hovering or keyboard focus reveals a like button; touchscreens show it directly. Blur is on by default and can be toggled beside the title. The grid and enlarged image panel share this state, which resets to on after a page refresh. The enlarged view centers Previous, Like, and Next in its action bar. The blur button is at the top right, left of Close; image information is at the bottom left in both Generate and Liked. Image deletion and download buttons are not shown. Navigate images left/right, press ↑ to like, or Space to toggle blur; the down arrow does nothing. Immersive mode automatically hides the action bar. Esc exits immersive mode first, then closes the enlarged view. Roaming images also have no original-image download button; the information panel retains prompt JSON download.

## Clear generation results

The one-click clear action beside the title covers all generation results: unliked images and their same-named prompt JSON are removed locally, while liked images are only removed from generation results and remain in Liked. Task history, remote ComfyUI outputs, and roaming images are retained. This action cannot be undone. Files in use are retried through the existing pending-deletion queue. New generation results continue to appear in the grid.

## Tag filters in Liked

On Liked, search and select multiple historical positive prompt terms to show only liked images containing every selected term. Tags default to ascending alphabetical order. The sort icon switches to descending image count, with alphabetical order for equal counts. Counts cover all liked images, counting each term once per image. See [Liked tag filtering (Chinese)](../dev/issues/liked-tag-filter.md) for details and API information.
