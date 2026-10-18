import test from 'node:test';
import assert from 'node:assert/strict';
import { bindTouchNavigation } from '../web/src/controllers/touch-navigation.mjs';

function fixture(installed = false) {
  const stage = new EventTarget();
  stage.clientWidth = 360;
  const directions = [], ratings = [];
  let enabled = true;
  const dispose = bindTouchNavigation(stage, { navigate: direction => directions.push(direction), adjustFeedback: direction => ratings.push(direction), verticalEnabled: () => installed, enabled: () => enabled });
  const finger = (x, y = 100, id = 1) => ({ identifier: id, clientX: x, clientY: y });
  const touch = (type, touches, changedTouches = touches, blocked = false) => {
    const event = new Event(type, { cancelable: true });
    Object.assign(event, { touches, changedTouches });
    stage.closest = () => blocked ? stage : null;
    stage.dispatchEvent(event);
    return event;
  };
  return { stage, directions, ratings, touch, finger, dispose, browser: () => { installed = false; }, disable: () => { enabled = false; } };
}

test('single-finger image swipes navigate once, leaving taps and vertical scrolling alone', () => {
  const f = fixture();
  f.touch('touchstart', [f.finger(200)]);
  assert.equal(f.touch('touchmove', [f.finger(120)]).defaultPrevented, true);
  f.touch('touchend', [], [f.finger(120)]);
  f.touch('touchstart', [f.finger(100)]);
  f.touch('touchend', [], [f.finger(180)]);
  assert.deepEqual(f.directions, ['newer', 'older']);
  f.touch('touchstart', [f.finger(200)]);
  assert.equal(f.touch('touchmove', [f.finger(195, 150)]).defaultPrevented, false);
  f.touch('touchend', [], [f.finger(100, 150)]);
  f.touch('touchstart', [f.finger(200)]);
  f.touch('touchend', [], [f.finger(190)]);
  assert.equal(f.directions.length, 2);
  f.dispose();
});

test('pinches, cancelled gestures, controls and disabled viewers never navigate', () => {
  const f = fixture();
  f.touch('touchstart', [f.finger(200)]);
  assert.equal(f.touch('touchmove', [f.finger(150), f.finger(220, 150, 2)]).defaultPrevented, false);
  f.touch('touchend', [], [f.finger(80)]);
  f.touch('touchstart', [f.finger(200)]);
  f.touch('touchcancel', []);
  f.touch('touchend', [], [f.finger(80)]);
  f.touch('touchstart', [f.finger(200)], undefined, true);
  f.touch('touchend', [], [f.finger(80)]);
  f.touch('touchstart', [f.finger(200)]);
  f.disable();
  f.touch('touchend', [], [f.finger(80)]);
  f.dispose();
  assert.deepEqual(f.directions, []);
});

test('installed roam swipes rate once per gesture while browser swipes keep scrolling', () => {
  const f = fixture(true);
  for (const dy of [-90, 90]) {
    f.touch('touchstart', [f.finger(150, 200)]);
    assert.equal(f.touch('touchmove', [f.finger(153, 200 + dy)]).defaultPrevented, true);
    f.touch('touchmove', [f.finger(154, 200 + dy * 1.5)]);
    assert.deepEqual(f.ratings, dy < 0 ? [] : [1]);
    f.touch('touchend', [], [f.finger(154, 200 + dy * 1.5)]);
  }
  assert.deepEqual(f.ratings, [1, -1]);
  assert.deepEqual(f.directions, []);
  // A vertical start cannot turn into horizontal navigation.
  f.touch('touchstart', [f.finger(150, 200)]);
  f.touch('touchmove', [f.finger(150, 180)]);
  f.touch('touchend', [], [f.finger(30, 180)]);
  // Pinch, cancellation, buttons and short gestures do not rate.
  f.touch('touchstart', [f.finger(150, 200)]);
  f.touch('touchmove', [f.finger(150, 130), f.finger(180, 130, 2)]);
  f.touch('touchend', [], [f.finger(150, 100)]);
  f.touch('touchstart', [f.finger(150, 200)]);
  f.touch('touchcancel', []);
  f.touch('touchend', [], [f.finger(150, 100)]);
  f.touch('touchstart', [f.finger(150, 200)], undefined, true);
  f.touch('touchend', [], [f.finger(150, 100)]);
  f.touch('touchstart', [f.finger(150, 200)]);
  f.touch('touchend', [], [f.finger(150, 180)]);
  f.browser();
  f.touch('touchstart', [f.finger(150, 200)]);
  assert.equal(f.touch('touchmove', [f.finger(150, 130)]).defaultPrevented, false);
  f.touch('touchend', [], [f.finger(150, 100)]);
  assert.deepEqual(f.ratings, [1, -1]);
  assert.deepEqual(f.directions, []);
  f.dispose();
});
