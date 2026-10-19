import test from 'node:test';
import assert from 'node:assert/strict';
import { createAutoHideControls, createImmersiveViewer } from '../web/src/controllers/immersive-controls.mjs';

function clock() {
  let next = 0;
  const pending = new Map();
  return {
    pending,
    schedule(callback, delay) { const id = ++next; pending.set(id, { callback, delay }); return id; },
    cancel(id) { pending.delete(id); },
    tick() { const callbacks = [...pending.values()]; pending.clear(); callbacks.forEach(item => item.callback()); },
  };
}

test('idle controls hide after two seconds; activity resets one timeout and leaving cancels it', () => {
  const timer = clock(), visible = [];
  const controls = createAutoHideControls({ visible: value => visible.push(value), held: () => false, ...timer });
  controls.start();
  assert.equal([...timer.pending.values()][0].delay, 2000);
  controls.wake(); controls.wake();
  assert.equal(timer.pending.size, 1);
  timer.tick(); assert.equal(visible.at(-1), false);
  controls.wake(); assert.equal(visible.at(-1), true);
  controls.stop(); assert.equal(timer.pending.size, 0);
  controls.wake(); assert.equal(timer.pending.size, 0);
});

test('hover or keyboard focus keeps controls visible until the hold ends', () => {
  const timer = clock(), visible = [];
  let held = false;
  const controls = createAutoHideControls({ visible: value => visible.push(value), held: () => held, ...timer });
  controls.start(); held = true; timer.tick();
  assert.equal(visible.at(-1), true);
  controls.wake(); assert.equal(timer.pending.size, 0);
  held = false; controls.wake(); timer.tick();
  assert.equal(visible.at(-1), false);
  controls.stop();
});

class Node extends EventTarget {
  constructor(doc) {
    super(); this.doc = doc; this.children = []; this.attributes = new Map();
    this.hidden = false; this.inert = false; this.disabled = false; this.isConnected = true;
    const classes = new Set();
    this.classList = {
      add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value),
      toggle: (value, enable) => enable ? classes.add(value) : classes.delete(value),
    };
  }
  add(child) { this.children.push(child); child.parentElement = this; return child; }
  setAttribute(key, value) { this.attributes.set(key, value); }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  closest() { for (let node = this; node; node = node.parentElement) if (node.hidden || node.inert) return node; return null; }
  focus() { this.doc.activeElement = this; }
}

function fixture(withExit = true) {
  const document = new EventTarget(), window = new EventTarget();
  document.body = new Node(document);
  const heading = document.body.add(new Node(document));
  const entry = heading.add(new Node(document));
  const preserved = document.body.add(new Node(document)); preserved.inert = true;
  const card = document.body.add(new Node(document));
  const toolbar = card.add(new Node(document)), exit = toolbar.add(new Node(document)); exit.hidden = true;
  let eligible = true;
  const viewer = createImmersiveViewer({ card, toolbar, entry, ...(withExit ? { exit } : {}), eligible: () => eligible, document, window });
  return { document, window, heading, preserved, entry, card, toolbar, exit, viewer, disable: () => { eligible = false; } };
}

test('Escape exits and restores focus without an exit button', () => {
  const f = fixture(false);
  try {
    f.entry.dispatchEvent(new Event('click'));
    assert.equal(f.viewer.active, true);
    const event = new Event('keydown', { cancelable: true }); event.key = 'Escape'; f.document.dispatchEvent(event);
    assert.equal(event.defaultPrevented, true);
    assert.equal(f.viewer.active, false);
    assert.equal(f.heading.inert, false);
    assert.equal(f.document.activeElement, f.entry);
  } finally { f.viewer.leave(); }
});

test('unsupported native fullscreen keeps viewport mode and Escape restores isolation and focus', () => {
  const f = fixture();
  try {
    f.entry.dispatchEvent(new Event('click'));
    assert.equal(f.viewer.active, true); assert.equal(f.card.classList.contains('immersive'), true);
    assert.equal(f.heading.inert, true); assert.equal(f.exit.hidden, false);
    assert.equal(f.document.activeElement, f.card);
    const event = new Event('keydown', { cancelable: true }); event.key = 'Escape'; f.document.dispatchEvent(event);
    assert.equal(event.defaultPrevented, true); assert.equal(f.viewer.active, false);
    assert.equal(f.heading.inert, false); assert.equal(f.preserved.inert, true);
    assert.equal(f.toolbar.inert, false); assert.equal(f.exit.hidden, true);
    assert.equal(f.document.activeElement, f.entry);
  } finally { f.viewer.leave(); }
});

test('native fullscreen is requested in the click and browser fullscreen exit ends immersion', async () => {
  const f = fixture(); let calls = 0;
  f.card.requestFullscreen = () => { calls++; f.document.fullscreenElement = f.card; f.document.dispatchEvent(new Event('fullscreenchange')); return Promise.resolve(); };
  try {
    f.entry.dispatchEvent(new Event('click'));
    assert.equal(calls, 1); assert.equal(f.viewer.active, true);
    await Promise.resolve();
    f.document.fullscreenElement = null; f.document.dispatchEvent(new Event('fullscreenchange'));
    assert.equal(f.viewer.active, false); assert.equal(f.document.activeElement, f.entry);
  } finally { f.viewer.leave(); }
});

test('a delayed native request cannot reenter after pagehide', async () => {
  const f = fixture(); let resolveRequest, exits = 0;
  f.card.requestFullscreen = () => new Promise(resolve => { resolveRequest = resolve; });
  f.document.exitFullscreen = () => { exits++; f.document.fullscreenElement = null; return Promise.resolve(); };
  try {
    f.entry.dispatchEvent(new Event('click')); f.window.dispatchEvent(new Event('pagehide'));
    assert.equal(f.viewer.active, false); assert.equal(f.heading.inert, false);
    f.document.fullscreenElement = f.card; resolveRequest();
    await Promise.resolve(); await Promise.resolve();
    assert.equal(exits, 1); assert.equal(f.document.fullscreenElement, null);
  } finally { f.viewer.leave(); }
});

test('a denied native request falls back and the exit button still works; empty galleries cannot enter', async () => {
  const f = fixture();
  f.card.requestFullscreen = () => Promise.reject(new Error('not allowed'));
  try {
    f.entry.dispatchEvent(new Event('click')); await Promise.resolve(); await Promise.resolve();
    assert.equal(f.viewer.active, true);
    f.exit.dispatchEvent(new Event('click')); assert.equal(f.viewer.active, false);
    f.disable(); f.entry.dispatchEvent(new Event('click')); assert.equal(f.viewer.active, false);
  } finally { f.viewer.leave(); }
});

test('leaving native fullscreen can finish before a follow-up dialog takes focus', async () => {
  const f = fixture(); let finishExit;
  f.card.requestFullscreen = () => { f.document.fullscreenElement = f.card; return Promise.resolve(); };
  f.document.exitFullscreen = () => new Promise(resolve => { finishExit = () => { f.document.fullscreenElement = null; resolve(); }; });
  try {
    f.entry.dispatchEvent(new Event('click')); await Promise.resolve();
    let ready = false;
    const leaving = f.viewer.leave().then(() => { ready = true; });
    assert.equal(f.viewer.active, false);
    assert.equal(ready, false);
    finishExit(); await leaving;
    assert.equal(ready, true);
    assert.equal(f.document.activeElement, f.entry);
    assert.equal(f.document.fullscreenElement, null);
  } finally { f.viewer.leave(); }
});


test('immediate hiding cancels the idle timer even while controls are held', () => {
  const timer = clock(), visible = [];
  let held = false;
  const controls = createAutoHideControls({ visible: value => visible.push(value), held: () => held, ...timer });
  controls.start(); held = true;
  controls.hide();
  assert.equal(visible.at(-1), false); assert.equal(timer.pending.size, 0);
  controls.wake(); assert.equal(visible.at(-1), true);
  controls.stop();
});

test('image shortcuts hide panels without focus or pointer-leave waking them; pointer and Tab still work', () => {
  const f = fixture();
  const press = key => { const event = new Event('keydown', { cancelable: true }); event.key = key; f.document.dispatchEvent(event); };
  try {
    f.entry.dispatchEvent(new Event('click'));
    f.exit.focus();
    press('ArrowRight');
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), true);
    assert.equal(f.toolbar.inert, true);
    assert.equal(f.document.activeElement, f.card);
    f.card.dispatchEvent(new Event('focusin'));
    f.toolbar.dispatchEvent(new Event('pointerleave'));
    press(' ');
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), true);
    f.card.dispatchEvent(new Event('pointermove'));
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), false);
    press('ArrowUp');
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), true);
    press('Tab');
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), false);
    assert.equal(f.toolbar.inert, false);
  } finally { f.viewer.leave(); }
});


test('standalone touch wakes hidden panels only after a tap; four-way swipes stay hidden', () => {
  const f = fixture();
  f.window.matchMedia = () => ({ matches: true });
  const pointer = (type, x, y, extra = {}) => {
    const event = new Event(type);
    Object.assign(event, { pointerType: 'touch', pointerId: 1, isPrimary: true, clientX: x, clientY: y }, extra);
    f.card.dispatchEvent(event);
  };
  const hide = () => { const event = new Event('keydown'); event.key = 'ArrowRight'; f.document.dispatchEvent(event); };
  const hidden = () => f.card.classList.contains('immersive-controls-hidden');
  try {
    f.entry.dispatchEvent(new Event('click')); hide();
    // Fullscreen changes the media query without changing how the app was opened.
    f.window.matchMedia = () => ({ matches: false });
    for (const [x, y] of [[100, 200], [300, 200], [200, 100], [200, 300]]) {
      pointer('pointerdown', 200, 200);
      f.card.dispatchEvent(new Event('focusin'));
      assert.equal(hidden(), true);
      pointer('pointermove', x, y);
      pointer('pointerup', x, y);
      f.toolbar.dispatchEvent(new Event('pointerleave'));
      assert.equal(hidden(), true);
      assert.equal(f.toolbar.inert, true);
    }
    // Returning to the start, cancelling or adding a second finger is not a tap.
    pointer('pointerdown', 200, 200); pointer('pointermove', 200, 240); pointer('pointerup', 200, 200);
    pointer('pointerdown', 200, 200); pointer('pointercancel', 200, 200); pointer('pointerup', 200, 200);
    pointer('pointerdown', 200, 200); pointer('pointerdown', 210, 210, { pointerId: 2, isPrimary: false }); pointer('pointerup', 200, 200);
    assert.equal(hidden(), true);
    pointer('pointerdown', 200, 200);
    assert.equal(hidden(), true);
    pointer('pointerup', 203, 204);
    assert.equal(hidden(), false);
    assert.equal(f.toolbar.inert, false);
  } finally { f.viewer.leave(); }
});

test('ordinary browser touch keeps existing immediate wake behavior', () => {
  const f = fixture(); f.window.matchMedia = () => ({ matches: false });
  try {
    f.entry.dispatchEvent(new Event('click'));
    const key = new Event('keydown'); key.key = 'ArrowLeft'; f.document.dispatchEvent(key);
    const down = new Event('pointerdown'); down.pointerType = 'touch'; f.card.dispatchEvent(down);
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), false);
  } finally { f.viewer.leave(); }
});


test('editing an immersive anchor keeps focus and controls while Escape still exits', () => {
  const f = fixture();
  try {
    f.entry.dispatchEvent(new Event('click'));
    const input = { closest: () => input };
    f.document.activeElement = input;
    for (const key of [' ', 'ArrowLeft', 'ArrowDown']) {
      const event = new Event('keydown', { cancelable: true });
      event.key = key;
      Object.defineProperty(event, 'target', { value: input });
      f.document.dispatchEvent(event);
      assert.equal(f.card.classList.contains('immersive-controls-hidden'), false);
      assert.equal(f.document.activeElement, input);
      assert.equal(event.defaultPrevented, false);
    }
    const escape = new Event('keydown', { cancelable: true }); escape.key = 'Escape';
    Object.defineProperty(escape, 'target', { value: input });
    f.document.dispatchEvent(escape);
    assert.equal(f.viewer.active, false);
    assert.equal(f.document.activeElement, f.entry);
  } finally { f.viewer.leave(); }
});

test('image shortcuts keep controls available while the anchor dock is open', () => {
  const f = fixture();
  let open = true;
  f.card.matches = () => open;
  try {
    f.entry.dispatchEvent(new Event('click'));
    const key = new Event('keydown'); key.key = 'ArrowRight';
    f.document.dispatchEvent(key);
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), false);
    open = false;
    const next = new Event('keydown'); next.key = 'ArrowRight';
    f.document.dispatchEvent(next);
    assert.equal(f.card.classList.contains('immersive-controls-hidden'), true);
  } finally { f.viewer.leave(); }
});
