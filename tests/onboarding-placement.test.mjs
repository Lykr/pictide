import test from 'node:test';
import assert from 'node:assert/strict';
import { placeGuide } from '../web/src/components/onboarding/placement.mjs';

const overlaps = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;

test('a 4K privacy hint stays beside its button instead of at the screen bottom', () => {
  const target = { x: 3000, y: 140, width: 40, height: 40 };
  const placed = placeGuide({ viewport: { x: 0, y: 0, width: 3840, height: 2160 },
    card: { width: 360, height: 100 }, targets: [target], controls: [target] });
  assert(placed.y >= target.y + target.height && placed.y <= target.y + target.height + 32);
  assert.equal(placed.arrow.side, 'top');
  assert(!overlaps(placed, target));
  assert(placed.arrow.x >= target.x && placed.arrow.x <= target.x + target.width);
});

test('mobile anchor hints leave both editing and image navigation controls usable', () => {
  const clear = { x: 333, y: 723, width: 44, height: 44 };
  const next = { x: 230, y: 618, width: 44, height: 44 };
  const focus = { x: 329, y: 719, width: 52, height: 52 };
  const placed = placeGuide({ viewport: { x: 0, y: 0, width: 390, height: 844 },
    card: { width: 294, height: 98 }, targets: [focus], controls: [clear, next], bottomInset: 56 });
  assert(!overlaps(placed, clear));
  assert(!overlaps(placed, next));
  assert(placed.y >= 12 && placed.y + placed.height <= 788);
  assert(placed.x >= 12 && placed.x + placed.width <= 378);
  assert.equal(placed.arrow.side, 'right');
  assert(clear.x - placed.x - placed.width <= 32);
});

test('an invitation without a target stays above the bottom navigation', () => {
  const placed = placeGuide({ viewport: { x: 0, y: 0, width: 390, height: 844 },
    card: { width: 366, height: 160 }, bottomInset: 56 });
  assert.equal(placed.y + placed.height, 776);
  assert.equal(placed.arrow, null);
});
