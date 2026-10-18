import test from 'node:test';
import assert from 'node:assert/strict';
import { createRoamPlayback, playbackInterval } from '../web/src/controllers/roam-playback.mjs';

function fixture() {
  const timers = new Map(); let serial = 0, calls = 0, cancelledWaits = 0, current;
  const playback = createRoamPlayback({
    advance: guard => { calls++; current = guard; },
    cancelWait: () => cancelledWaits++,
    schedule: (run, delay) => { timers.set(++serial, { run, delay }); return serial; },
    cancel: id => timers.delete(id),
  });
  const update = changes => { Object.assign(state, changes); playback.update(state); };
  const state = { imageId: 'first', ready: false, active: true, busy: false, blocked: false };
  update({});
  return { playback, timers, update,
    get calls() { return calls; }, get cancelledWaits() { return cancelledWaits; }, get guard() { return current; },
    async fire() { const [id, timer] = timers.entries().next().value; timers.delete(id); timer.run(); await Promise.resolve(); },
  };
}

test('loaded pictures get one interval, pending generation waits and resumes on the next loaded picture', async () => {
  const f = fixture(); f.playback.toggle();
  assert.equal(f.timers.size, 0);
  f.update({ ready: true });
  const firstTimer = [...f.timers.keys()][0];
  f.update({ ready: true });
  assert.equal([...f.timers.keys()][0], firstTimer); // Refreshes do not postpone the deadline.
  assert.equal([...f.timers.values()][0].delay, 8000);
  await f.fire();
  assert.equal(f.calls, 1);
  f.update({ busy: true }); f.playback.retry();
  assert.equal(f.calls, 1); assert.equal(f.timers.size, 0);
  f.update({ imageId: 'second', ready: false, busy: false });
  assert.equal(f.timers.size, 0);
  f.update({ ready: true });
  assert.equal(f.timers.size, 1);
  await f.fire();
  assert.equal(f.calls, 2);
});

test('pause cancels its pending advance, manual navigation restarts, hidden/blocked pages stop', async () => {
  const f = fixture(); f.update({ ready: true }); f.playback.toggle();
  await f.fire(); assert.equal(f.guard(), true);
  f.playback.pause();
  assert.equal(f.cancelledWaits, 1); assert.equal(f.guard(), false);
  f.playback.toggle();
  const old = [...f.timers.keys()][0];
  f.playback.restart();
  assert.notEqual([...f.timers.keys()][0], old);
  f.playback.setInterval(2);
  assert.equal([...f.timers.values()][0].delay, 2000);
  f.update({ active: false });
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
  f.update({ active: true }); f.playback.toggle();
  f.update({ blocked: true });
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
});

test('interval accepts integers from 1 to 600 and rejects blanks and invalid values', () => {
  assert.equal(playbackInterval('1'), 1); assert.equal(playbackInterval(600), 600);
  for (const value of ['', ' ', 0, 601, 1.5, true, null]) assert.throws(() => playbackInterval(value));
});

test('progress shares the deadline, restarts on manual navigation, and stays full while awaiting a next image', async () => {
  let clock = 100, state;
  const timers = new Map(); let serial = 0, cancelled = 0;
  const playback = createRoamPlayback({ now: () => clock, changed: next => state = next,
    advance: () => {}, cancelWait: () => cancelled++,
    schedule: run => { timers.set(++serial, run); return serial; }, cancel: id => timers.delete(id) });
  const picture = { imageId: 'a', ready: true, active: true, busy: false, blocked: false };
  playback.update(picture); playback.toggle();
  assert.equal(state.startedAt, 100); assert.equal(state.durationMs, 8000);
  const firstCycle = state.cycle;
  clock = 1100; playback.update(picture);
  assert.equal(state.startedAt, 100); assert.equal(state.cycle, firstCycle);
  playback.restart();
  assert.equal(state.startedAt, 1100); assert.equal(state.cycle, firstCycle + 1); assert.equal(timers.size, 1);
  clock = 2100; playback.restart();
  assert.equal(state.startedAt, 2100); assert.equal(timers.size, 1);
  const [id, run] = timers.entries().next().value; timers.delete(id); run(); await Promise.resolve();
  assert.equal(state.waiting, true); assert.equal(state.startedAt, null);
  clock = 8000; playback.restart();
  assert.equal(cancelled, 1); assert.equal(state.waiting, false); assert.equal(state.startedAt, 8000);
  playback.pause(); assert.equal(state.playing, false); assert.equal(state.startedAt, null); assert.equal(timers.size, 0);
});

test('liking holds playback, repeats do not restart it, and the next loaded picture resumes', async () => {
  const f = fixture(); f.update({ ready: true }); f.playback.toggle();
  f.playback.pauseForLike();
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
  f.playback.pauseForLike(); f.update({ ready: true });
  assert.equal(f.timers.size, 0);
  // Previous images do not resume; the next image does, even when returning from history.
  f.playback.prepareNavigation('older'); f.update({ imageId: 'older' });
  assert.equal(f.playback.playing, false);
  f.playback.prepareNavigation('newer'); f.playback.restart();
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
  f.update({ busy: true }); f.playback.retry();
  assert.equal(f.calls, 0); assert.equal(f.timers.size, 0);
  f.update({ imageId: 'first', ready: false, busy: false });
  assert.equal(f.playback.playing, true); assert.equal(f.timers.size, 0);
  f.update({ ready: true });
  assert.equal(f.timers.size, 1);
  assert.equal([...f.timers.values()][0].delay, 8000);
});

test('like cancels an automatic wait; explicit pause and leaving the page cancel automatic resumption', async () => {
  const f = fixture(); f.update({ ready: true }); f.playback.toggle();
  await f.fire(); assert.equal(f.guard(), true);
  f.playback.pauseForLike();
  assert.equal(f.cancelledWaits, 1); assert.equal(f.guard(), false);
  f.playback.prepareNavigation('newer'); f.playback.pause();
  f.update({ imageId: 'second' });
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
  f.playback.toggle(); f.playback.pauseForLike(); f.playback.prepareNavigation('newer');
  f.update({ active: false }); f.update({ active: true, imageId: 'third' });
  assert.equal(f.playback.playing, false); assert.equal(f.timers.size, 0);
});
