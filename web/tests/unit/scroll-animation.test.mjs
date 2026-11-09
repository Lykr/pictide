import test from 'node:test';
import assert from 'node:assert/strict';
import { createScrollAnimation } from '../../src/components/scroll-animation.mjs';

function fixture() {
  let created = 0, cancelled = 0;
  const frames = [], timings = [];
  const native = { effect: { setKeyframes: value => frames.push(value), updateTiming: value => timings.push(value) },
    pause() {}, play() {}, cancel() { cancelled++; } };
  const view = createScrollAnimation({ animate() { created++; return native; } });
  const path = { revision: 1, from: 100, to: -400, velocity: 0, endVelocity: 0, duration: .6, elapsed: .2 };
  return { view, path, frames, timings, created: () => created, cancelled: () => cancelled };
}

test('joining or rebasing a trajectory starts at the currently displayed position', () => {
  const f = fixture();
  f.view.paint({ offset: -80, velocity: -500, animation: f.path }, 1000);
  assert.equal(f.frames.at(-1)[0].transform, 'translate3d(-80px,0,0)');
  assert.equal(f.frames.at(-1)[1].transform, 'translate3d(-400px,0,0)');
  assert.ok(Math.abs(f.timings.at(-1).duration - 400) < 1e-8);
  f.view.paint({ offset: 200, velocity: -500, animation: { ...f.path, revision: 2, from: 500, to: 0 } }, 1100);
  assert.equal(f.frames.at(-1)[0].transform, 'translate3d(200px,0,0)');
  assert.equal(f.created(), 1);
  assert.equal(f.cancelled(), 0);
});

test('retargets, pauses, and autoplay share one effect without exposing the base style', () => {
  const f = fixture();
  f.view.paint({ offset: 100, velocity: 0, animation: null }, 0);
  f.view.paint({ offset: -80, velocity: -500, animation: f.path }, 1000);
  const writes = f.frames.length;
  f.view.paint({ offset: -100, velocity: -500, animation: { ...f.path, elapsed: .25 } }, 1050);
  assert.equal(f.frames.length, writes, 'ordinary sampling must not rebuild the effect');
  f.view.paint({ offset: -100, velocity: 0, animation: null }, 1100);
  assert.deepEqual(f.frames.at(-1), [{ transform: 'translate3d(-100px,0,0)' }, { transform: 'translate3d(-100px,0,0)' }],
    'a hold needs both endpoints; one keyframe starts from the underlying style');
  f.view.paint({ offset: -102, velocity: -80, animation: { ...f.path, revision: 3, endVelocity: -80 } }, 1200);
  assert.equal(f.created(), 1);
  assert.equal(f.cancelled(), 0);
  f.view.dispose();
  assert.equal(f.cancelled(), 1);
});
