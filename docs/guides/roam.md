# Roam

[简体中文](../zh-CN/guides/roam.md)

[Documentation](../README.md)

Start roaming even when you are not sure what you want to see. Pictide prepares images without asking you to write prompts. Leave feedback on what catches your eye and gradually find your direction.

## Start browsing

After [connecting an image API](getting-started.md), select it under Settings → Roam, then open Roam to begin. Move to the next image to explore. Like or dislike an image to express your preferences; click again to undo. Feedback influences future recommendations, though images already prepared may still follow the earlier direction.

Automatic prefetch prepares images ahead to reduce waiting. Set it to `0` to generate only when you request the next image. Selecting a new cloud image API turns prefetch off by default; enable it when you want it.

## Choose how to explore

Open Roam options at the top right:

- **Drift**: draw a fresh prompt combination for each image and discover more possibilities.
- **Flow**: gradually vary the current combination to follow a direction you enjoy.
- **Anchor**: keep the entire prompt and try other images with different random seeds.

Preference scope offers All, which explores the full vocabulary, or Liked, which draws tags from images you have liked. Standard recommendation strength is the default; try Strong to focus more on your existing preferences.

## Anchors

To keep an element from the current image, open Anchors at the bottom right, select a prompt term, or enter your own description. It carries into later roaming prompts while other elements can change. How closely an image follows it depends on the model.

After editing, move to the next image to continue in the new direction. Anchors are remembered between visits; deselect one to remove it. Locked terms come from your [preset](prompts.md#libraries-and-presets) and can be edited on Prompts. Anchor mode keeps the entire prompt; switch modes to edit individual anchors.

## Browsing and autoplay

Turn on autoplay for relaxed browsing and adjust each image's display time in Roam options. Playback waits if generation is unfinished. Liking an image pauses on it; moving to the next resumes playback. Leaving Roam pauses playback.

Use ← / → to browse and ↑ / ↓ to move between Disliked, Unrated, and Liked. Immersive mode fills the screen with the image, with a loading ring at the top left while waiting. Open Anchors in a floating panel to guide the next images. Blur changes only the display; the original stays clear.

Roam remembers where you left off. Like images you want to keep; older unliked images are handled according to your [cleanup settings](settings.md).
