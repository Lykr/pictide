# Generate

[简体中文](../zh-CN/guides/generate.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md) / [Liked](liked.md)

Try several images around an idea and compare the results in Generate. Use a preset to compose prompts automatically, or write your own.

## Canvas size

Choose an image API, then pick **Canvas size** from its linked [canvas pool](settings.md#canvas-pools). Choices show exact pixel widths and heights. **API default size** uses the saved workflow or service settings.

Every task in the batch uses the chosen size. Navigation and pool refreshes retain the current choice; switching APIs selects that API's default. Retrying an uncertain submission keeps the same request ID and dimensions.

## Batch generation and seeds

**Images per round** sets how many images share a prompt; **Generation rounds** sets how often to repeat. For example, 2 images per round and 3 rounds submit 6 generation requests. With automatic prompt generation enabled, each round uses a fresh prompt.

An image seed controls randomness; the default `-1` chooses a random seed. This requires support from your image service; OpenAI Images and Gemini do not support it.

## Browse generation results

Results appear in an image grid. Click to view an image in full, and like your favorites to keep them in [Liked](liked.md). See [Image browsing](images.md) for viewing prompts and browsing enlarged images.

## Clear generation results

Clearing permanently deletes local, unliked generation images and their prompts. Liked images leave Generate but remain in Liked. Roaming images are unaffected.
