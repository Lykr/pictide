# Liked

[简体中文](liked.zh-CN.md)

[Documentation](../README.md) · [Roam](roam.md) / [Generate](generate.md)

Liked brings together images you have liked in Roam and Generate. Use it to revisit your collection, filter by tags, and sort by preference score.

## Browse and manage likes

Images appear in a thumbnail grid. Click an image to open the enlarged view; see [Image browsing](images.md) for blur, image information, keyboard controls, and immersive mode. Hovering or focusing a thumbnail reveals the unlike button; unliking requires confirmation.

Liked does not offer Clear generation results. Clearing [Generate](generate.md#clear-generation-results) keeps liked images here.

## Preference score sorting

Choose Newest or Preference score sorting. Score sorting covers all filtered results: higher scores first, ties by time, and unscorable images last, shown in batches of 100. Entering score sorting or changing filters reuses cached scores. Only a manual refresh recomputes the current filtered results, and order stays fixed while browsing. Computation reuses cached preference weights and deduplicates identical prompt combinations. See [score sorting (Chinese)](../dev/issues/liked-score-sort.md).

## Tag filters

On Liked, search and select multiple historical positive prompt terms to show only liked images containing every selected term. Tags default to ascending alphabetical order. The sort icon switches to descending image count, with alphabetical order for equal counts. Counts cover all liked images, counting each term once per image. See [Liked tag filtering (Chinese)](../dev/issues/liked-tag-filter.md) for details and API information.
