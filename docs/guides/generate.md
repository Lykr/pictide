# Generate

[简体中文](generate.zh-CN.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md) / [Liked](liked.md)

Use Generate for manual or preset-based image generation. Its results are browsed and rated separately from Roam and do not count toward the roaming buffer. Images you like also appear in [Liked](liked.md).

## Batch generation and seeds

On Generate, set Images per round and Generation rounds separately (both `1`–`10`, default `1`). For example, 2 images per round and 3 rounds create 3 rounds containing 6 independent tasks in one submission, executed in the existing queue order. With automatic candidate generation enabled, each round draws fresh prompts and updates the candidate seed and sequence frame according to the after-generation controls; tasks within the same round share its positive and negative prompts. Fixed controls stay unchanged. Manual text, or disabling automatic drawing, reuses the current text in each round. The tag library and backend configuration are frozen on submission; later edits do not change queued tasks.

For ComfyUI workflows with seed support, image seed `-1` gives each task an independent random seed. With an explicit seed, images increment it one by one across rounds and safely wrap at the seed limit. After successful submission, the input shows the next seed. Workflows without a seed binding continue using their own settings. All rounds enter the local task queue together. Closing the page does not stop submitted tasks; after an application restart, queued tasks can continue, while recovery of requests already sent depends on the backend. OpenAI Images and Gemini do not support deterministic image seeds or negative prompts. Use an empty negative prompt or preset and let the service control image randomness; the local candidate seed still controls prompt selection. An uncertain cloud submission is not automatically sent again, and each new generation request may incur provider charges. Candidate generation failure or insufficient remaining queue capacity rejects the entire batch. The queue holds at most 100 pending tasks, with capacity shared across submissions.

The count means generation requests (ComfyUI workflow executions): a default single-image workflow run N times yields N images. If a custom workflow returns multiple images per run, all outputs are retained and the final image count can exceed N. The entire batch is queued together after capacity and idempotency checks; insufficient capacity creates no partial tasks. Network retries reuse the original request ID and full batch input.

## Browse generation results

Results appear in a thumbnail grid. Hovering or keyboard focus reveals a like button; touchscreens show it directly. Click an image to open the enlarged view. Blur, image information, keyboard controls, and immersive mode are covered in [Image browsing](images.md).

Older manually generated images are placed in Generate, preserving their images, prompts, and ratings under the shared [history cleanup settings](settings.md).

## Clear generation results

The one-click clear action beside the title covers all generation results: unliked images and their same-named prompt JSON are removed locally, while liked images are only removed from generation results and remain in Liked. Task history, remote ComfyUI outputs, and roaming images are retained. This action cannot be undone. Files in use are retried through the existing pending-deletion queue. New generation results continue to appear in the grid.
