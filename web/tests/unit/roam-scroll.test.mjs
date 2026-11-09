import test from 'node:test';
import assert from 'node:assert/strict';
import { createRoamScroll } from '../../src/controllers/roam-scroll.mjs';
import { createRoamPlayback } from '../../src/controllers/roam-playback.mjs';

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

test('manual navigation stays smooth while paused; like resumes in place at continuous speed', () => {
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
  playback.pauseForLike();
  const resumed = fixture();
  resumed.tick(1, true);
  const beforeResume = resumed.freeze().offset;
  assert.equal(playback.resumeFromLike(), true);
  assert.equal(playback.playing, true);
  assert.equal(resumed.snapshot().offset, beforeResume);
  assert.equal(resumed.snapshot().target, null);
  assert.equal(resumed.tick(1 / 60, playback.playing, 'normal').offset, beforeResume - 48 / 60);
  playback.pause();
  assert.equal(playback.resumeFromLike(), false);
  playback.prepareNavigation('newer'); playback.update({ ...state, imageId: '2' });
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

test('focus and readiness refreshes preserve the in-flight easing curve and velocity', () => {
  const control = fixture(), refreshed = fixture();
  control.navigate('newer'); refreshed.navigate('newer');
  for (let frame = 1; frame <= 30; frame++) {
    const expected = control.tick(1 / 60, false);
    if (frame === 8 || frame === 12 || frame === 16) refreshed.layout(pictures(), 600, refreshed.snapshot().focus);
    const actual = refreshed.tick(1 / 60, false);
    assert.ok(Math.abs(actual.offset - expected.offset) < .001, `frame ${frame}: refresh interrupted the original motion`);
  }
});

test('autoplay and repeated navigation carry velocity into each new destination', () => {
  const scroll = fixture([500, 500, 500, 500]);
  const delta = 1e-5;
  const speed = () => {
    const before = scroll.snapshot().offset;
    return (scroll.tick(delta, true, 'fast').offset - before) / delta;
  };
  scroll.tick(.1, true, 'fast');
  let before = speed();
  scroll.navigate('newer');
  assert.ok(Math.abs(speed() - before) < 1, 'first navigation must inherit autoplay speed');
  scroll.tick(.16, true, 'fast');
  for (const direction of ['newer', 'older', 'older']) {
    before = speed();
    scroll.navigate(direction);
    assert.ok(Math.abs(speed() - before) < 1, `${direction} restarted at zero speed`);
  }
});

test('seeking hands off to autoplay without losing the remainder of a frame', () => {
  const whole = fixture([500, 500, 500, 500]);
  const split = fixture([500, 500, 500, 500]);
  whole.tick(.1, true, 'fast'); split.tick(.1, true, 'fast');
  whole.navigate('newer'); split.navigate('newer');
  whole.tick(.8, true, 'fast');
  for (let frame = 0; frame < 80; frame++) split.tick(.01, true, 'fast');
  assert.equal(whole.snapshot().moving, false);
  assert.ok(Math.abs(whole.snapshot().offset - split.snapshot().offset) < 1e-7);
  const before = whole.snapshot().offset;
  assert.ok(Math.abs(whole.tick(1 / 60, true, 'fast').offset - before + 80 / 60) < 1e-7);
});

test('autoplay keeps its native trajectory until a boundary or layout actually changes', () => {
  const scroll = fixture([500, 500, 500, 500], '1');
  const first = scroll.tick(.1, true, 'fast');
  const second = scroll.tick(.1, true, 'fast');
  assert.equal(second.animation.revision, first.animation.revision);
  assert.equal(second.velocity, -80);
  scroll.layout(pictures([500, 500, 500, 500]), 600, '1');
  assert.equal(scroll.snapshot().animation.revision, first.animation.revision);
  scroll.layout(pictures([500, 500, 500, 500]).slice(1), 600, '1');
  assert.notEqual(scroll.snapshot().animation.revision, first.animation.revision);
  assert.equal(scroll.snapshot().offset, second.offset + 512);
  assert.equal(scroll.freeze().animation, null);
  assert.equal(scroll.tick(.1, false).animation, null);
});

test('reserving offscreen leading space keeps coordinates and seek trajectory unchanged', () => {
  const scroll = fixture([300, 300, 300, 300, 300, 300], '3');
  scroll.navigate('newer'); scroll.tick(.12, false);
  const before = scroll.snapshot();
  scroll.layout(pictures([300, 300, 300, 300, 300, 300]).slice(1), 600, before.focus, 12, 312);
  const after = scroll.snapshot();
  assert.equal(after.offset, before.offset);
  assert.equal(after.velocity, before.velocity);
  assert.equal(after.animation.revision, before.animation.revision);
});
