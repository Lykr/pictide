# Generate

[简体中文](../zh-CN/guides/generate.md)

[Documentation](../README.md) · [Prompts and presets](prompts.md) / [Liked](liked.md)

Try several images around an idea and compare the results in Generate. Use a preset to compose prompts automatically, or write your own.

## Batch generation and seeds

**Images per round** sets how many images share a prompt; **Generation rounds** sets how often to repeat. For example, 2 images per round and 3 rounds submit 6 generation requests. With automatic prompt generation enabled, each round uses a fresh prompt.

An image seed controls randomness; the default `-1` chooses a random seed. This requires support from your image service; OpenAI Images and Gemini do not support it.

## Browse generation results

Results appear in an image grid. Click to view an image in full, and like your favorites to keep them in [Liked](liked.md). See [Image browsing](images.md) for viewing prompts and browsing enlarged images.

## Clear generation results

Clearing permanently deletes local, unliked generation images and their prompts. Liked images leave Generate but remain in Liked. Roaming images are unaffected.
