import test from 'node:test';
import assert from 'node:assert/strict';

const motion = Object.assign(new EventTarget(), { matches: false });
globalThis.window = { matchMedia: () => motion };
globalThis.document = new EventTarget();
const { imageTransitionsEnabled, playImageTransition, cancelImageTransition, applyImageTransitions } =
  await import('../../src/controllers/image-transitions.mjs');
function image() {
  const calls = [];
  return { calls, animate(frames, timing) {
    const animation = Object.assign(new EventTarget(), { frames, timing, cancelled: 0,
      cancel() { this.cancelled++; this.dispatchEvent(new Event('cancel')); } });
    calls.push(animation);
    return animation;
  } };
}
test('rapid switching and disabling stop active image-only fades', () => {
  assert.equal(imageTransitionsEnabled(), true);
  const target = image();
  playImageTransition(target);
  assert.equal(target.calls[0].timing.duration, 180);
  assert.deepEqual(target.calls[0].frames, [{ opacity: 0 }, { opacity: 1 }]);
  playImageTransition(target);
  assert.equal(target.calls[0].cancelled, 1);
  applyImageTransitions(false);
  assert.equal(target.calls[1].cancelled, 1);
  playImageTransition(target);
  assert.equal(target.calls.length, 2);
  applyImageTransitions(true);
  playImageTransition(target);
  cancelImageTransition(target);
  assert.equal(target.calls[2].cancelled, 1);
});
test('system reduced motion immediately stops fades without changing the saved choice', () => {
  const target = image();
  playImageTransition(target);
  motion.matches = true;
  motion.dispatchEvent(new Event('change'));
  assert.equal(target.calls[0].cancelled, 1);
  assert.equal(imageTransitionsEnabled(), true);
  playImageTransition(target);
  assert.equal(target.calls.length, 1);
  motion.matches = false;
  playImageTransition(target);
  target.calls[1].dispatchEvent(new Event('finish'));
  cancelImageTransition(target);
  assert.equal(target.calls[1].cancelled, 0);
});
