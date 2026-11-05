import test from 'node:test';
import assert from 'node:assert/strict';
import { createRoamScroll } from '../../src/controllers/roam-scroll.mjs';
import { createRoamPlayback } from '../../src/controllers/roam-playback.mjs';
import { createGalleryCursors } from '../../src/controllers/roam-navigation.mjs';

const pictures = (widths = [300, 300, 300, 300]) => widths.map((width, i) => ({ id: String(i), width, ready: true }));
const fixture = (widths, initial = '0') => { const scroll = createRoamScroll(); scroll.layout(pictures(widths), 600, initial); return scroll; };

test('continuous movement stops at the last decoded image and resumes when the next is ready', () => {
  const scroll = createRoamScroll();
  const items = pictures(); items[1].ready = false;
  scroll.layout(items, 600, '0');
  const first = scroll.snapshot().offset;
  assert.equal(scroll.tick(10, true).offset, first);
  items[1].ready = true;
  scroll.layout(items, 600, '0');
  assert.equal(scroll.tick(1, true, 'normal').offset, first - 48);
  assert.equal(scroll.tick(100, true).focus, '3');
  assert.equal(scroll.tick(1, true).waiting, true);
});

test('arrows retarget from the actual pixel position and rapid presses advance the commanded destination', () => {
  const scroll = fixture();
  scroll.tick(1, true);
  const before = scroll.snapshot().offset;
  scroll.navigate('newer');
  assert.equal(scroll.snapshot().offset, before);
  const halfway = scroll.tick(.15, false).offset;
  assert.ok(halfway < before && halfway > -162);
  scroll.navigate('newer');
  assert.equal(scroll.snapshot().offset, halfway);
  assert.equal(scroll.snapshot().target, '2');
  scroll.tick(1, false);
  assert.equal(scroll.snapshot().offset, 300 - (150 + 312 * 2));
});

test('like freezes the actual center image, then next seeks smoothly; manual pause does not resume play', () => {
  const scroll = fixture();
  scroll.navigate('newer'); scroll.tick(.12, false);
  const paused = scroll.freeze();
  scroll.tick(1, false);
  assert.equal(scroll.snapshot().offset, paused.offset);
  scroll.navigate('newer');
  assert.equal(scroll.snapshot().offset, paused.offset);
  assert.ok(Math.abs(scroll.tick(.02, false).offset - paused.offset) < 10);
  scroll.tick(1, false);
  const settled = scroll.snapshot().offset;
  assert.equal(scroll.tick(1, false).offset, settled);

  const timers = [];
  const playback = createRoamPlayback({ advance() { throw Error('Scroll must not use the single-image timer'); }, schedule: fn => timers.push(fn) });
  playback.setExternal(true);
  const state = { imageId: '0', ready: true, active: true, busy: false, blocked: false };
  playback.update(state); playback.toggle();
  assert.equal(timers.length, 0);
  playback.pauseForLike(); playback.prepareNavigation('newer');
  playback.update({ ...state, imageId: '1' });
  assert.equal(playback.playing, true);
  playback.pause(); playback.prepareNavigation('newer'); playback.update({ ...state, imageId: '2' });
  assert.equal(playback.playing, false);
});

test('wide images own feedback when they cover the center, and pruning preserves their pixel position', () => {
  const scroll = fixture([100, 1200, 100], '1');
  assert.equal(scroll.tick(5, true, 'normal').focus, '1');
  const before = scroll.snapshot().offset;
  scroll.layout(pictures([100, 1200, 100]).slice(1), 600, '1');
  assert.equal(scroll.snapshot().offset, before + 112);
  assert.equal(scroll.snapshot().focus, '1');
});

test('a pending boundary navigation moves smoothly after the new picture arrives', () => {
  const scroll = fixture([300]);
  assert.equal(scroll.navigate('newer'), false);
  const before = scroll.snapshot().offset;
  scroll.layout(pictures([300, 300]), 600, '0');
  assert.equal(scroll.snapshot().offset, before);
  assert.equal(scroll.snapshot().target, '1');
  assert.ok(scroll.tick(.02, false).offset < before);
});

test('view guard protects the oldest visible image independently of the operation focus', () => {
  const cursor = createGalleryCursors(); cursor.restore({ artifact_id: '0', viewed_at: 10 });
  assert.equal(cursor.select('feed', '1', 11, false), null);
  assert.equal(cursor.get('feed'), '1');
  assert.equal(cursor.watch('0', 12), null);
  assert.deepEqual(cursor.watch('1', 12), { artifact_id: '1', viewed_at: 12 });
  assert.deepEqual(cursor.watch('0', 11), { artifact_id: '0', viewed_at: 13 });
});
