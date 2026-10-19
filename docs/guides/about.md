# About Pictide

[简体中文](about.zh-CN.md)

[User documentation](../README.md#user-documentation) · [Getting started](getting-started.md)

**Discover images you love as you roam.**

Pictide is a local generative image exploration app that gradually adapts to your preferences through feedback. Browse, express what you like, and guide the next image.

## What it helps with

“I want to see images I like, even when I do not know how to describe them.”

Once setup is complete, you can start roaming without a specific creative goal or a carefully written prompt. Likes, dislikes, and anchors let you guide future images as you discover your preferences and find visual inspiration. When you have a clear idea, you can enter specific prompts and generate images directly.

The core experience is an ongoing exploration of images, with room for surprise and a way to steer what comes next. The interface should let you begin without first learning PMI, prompt seeds, or sampling parameters; those controls remain available when you need them.

## Discover, guide, collect

| Experience | How Pictide supports it |
| --- | --- |
| Discover | Co-occurrence generation supplies image concepts, and the recommendation system selects candidates using your preferences to keep browsing fresh. |
| Guide | Express preferences through likes and dislikes, preserve image elements with anchors, and control variation through Drift, Flow, and Anchor modes. |
| Collect | Keep images you happen to love, then browse your likes using tag filters and preference-score sorting. |

## Roaming is the core experience

Roaming connects generation, browsing, and feedback so you can focus on images. Generation, prompts, and settings give you control over this experience:

| Section | Role in the product |
| --- | --- |
| Roam | Discover images, express preferences, and guide exploration. |
| Generate | Generate images from a specific idea or preset. |
| Liked | Save and organize images worth keeping. |
| Prompts | Manage fixed terms and co-occurrence presets, and preview possible combinations. |
| Settings | Configure generation backends, roaming behavior, and data management. |

## Local and personal

Images, tag libraries, and preferences are stored locally, giving you control over your generation resources and data. ComfyUI provides image generation; Pictide organizes candidates, recommendations, and browsing. Currently, one instance shares a single image collection and set of preferences. LAN access uses the same data, with no separate user accounts.

## Product scope

Pictide focuses on discovering, guiding, and collecting images through roaming. Its scope guides which features receive priority:

| Related product category | Pictide's scope |
| --- | --- |
| ComfyUI replacement or full frontend | Connect to ComfyUI and accept API workflows with the controls needed for exploration. Node-graph editing, custom-node management, and inference optimization belong to the generation backend. |
| Prompt-engineering workspace | Libraries, presets, and prompt controls support roaming. Users should be able to start exploring with prepared defaults and open these controls when they want more direction. |
| Model installer or model-management platform | Backend setup and a usable starting model can reduce first-use friction. They support onboarding; a model marketplace and general environment management are outside the core experience. |
| Professional production workspace | Manual generation supports a specific idea or preset. Complex image editing, compositing, and production pipelines are outside the current product focus. |

This scope describes product priorities. It does not announce new features or change the current setup requirements.

## Current approach and learning limits

Danbooru tag co-occurrence is the current way to build candidate prompts. Recommendation scores complete prompt combinations using feedback associated with the generated images. It learns associations between prompts and preferences; it does not directly analyze visual image features or fully understand a person's aesthetic.

Likes and dislikes provide explicit feedback, unrated images remain unknown, and withdrawing feedback removes that rating. Learning runs in the background, so saving a rating does not mean the next image will immediately change or match your taste. Anchors and roaming modes give you a separate way to guide the direction and amount of variation.

The product identity is image exploration. The current tag library, candidate algorithm, and generation model are implementation choices. Future approaches should preserve the experience of expressing preferences and steering exploration; changes to those mechanisms still require their own design and validation. See the [recommendation architecture](../dev/architecture/recommendation.md) for current implementation details.

## Experience goals

Help you easily encounter images you enjoy while continuing to find something fresh. Prioritize:

- A clear path from initial setup to the first image, with understandable defaults.
- Short, predictable waits and clear generation, waiting, and failure states.
- Reliable feedback and anchors, with controls that make the direction and amount of change understandable.
- A balance of familiar elements and new possibilities, while keeping user guidance available.
- Easy collection and rediscovery of liked images.

When evaluating a feature, ask: **Does it help people encounter images they enjoy more easily, or guide the next part of their exploration more naturally?** Model selection, candidate algorithms, prefetching, and interface controls should be judged by their contribution to this experience. These are design goals, not guarantees about generation time or image quality.

Continue reading: [Roam](roam.md) · [Generation and likes](images.md) · [Prompts and presets](prompts.md)
