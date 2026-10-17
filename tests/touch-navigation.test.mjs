import test from 'node:test';
import assert from 'node:assert/strict';
import { bindTouchNavigation } from '../web/src/controllers/touch-navigation.mjs';

function fixture() {
  const stage = new EventTarget();
  stage.clientWidth = 360;
  const directions = [];
  let enabled = true;
  const dispose = bindTouchNavigation(stage, { navigate: direction => directions.push(direction), enabled: () => enabled });
  const finger = (x, y = 100, id = 1) => ({ identifier: id, clientX: x, clientY: y });
  const touch = (type, touches, changedTouches = touches, blocked = false) => {
    const event = new Event(type, { cancelable: true });
    Object.assign(event, { touches, changedTouches });
    stage.closest = () => blocked ? stage : null;
    stage.dispatchEvent(event);
    return event;
  };
  return { stage, directions, touch, finger, dispose, disable: () => { enabled = false; } };
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
