import test from "node:test";
import assert from "node:assert/strict";
import { roamGenerationChanged } from "../web/src/controllers/roam-controls.mjs";
test("anchors and preset fixed terms invalidate old roam window", () => {
  const previous = { pinned_positive: ["garden"], preset_base_positive: ["illustration"] };
  assert.equal(roamGenerationChanged(previous, { ...previous, pinned_positive: [] }), true);
  assert.equal(roamGenerationChanged(previous, { ...previous, preset_base_positive: ["illustration", "garden"] }), true);
  assert.equal(roamGenerationChanged(previous, { ...previous, playback_interval_seconds: 8 }), false);
});

import { anchorTerms } from "../web/src/controllers/roam-anchors.mjs";
test("complete preset and anchor entries retain their source", () => {
  assert.deepEqual(anchorTerms("masterpiece, best quality, blue sky, garden", ["blue_sky"], ["masterpiece, best quality"]),
    ["blue sky", "masterpiece, best quality", "garden"]);
});
