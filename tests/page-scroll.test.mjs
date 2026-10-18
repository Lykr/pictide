import test from 'node:test';
import assert from 'node:assert/strict';
import { createPageScroll } from '../web/src/controllers/page-scroll.mjs';

function fixture(enabled = true) {
  const frames = [], writes = [];
  const win = {
    scrollY: 180,
    getComputedStyle: () => ({ getPropertyValue: () => enabled ? ' 1 ' : '0' }),
    requestAnimationFrame: frame => frames.push(frame),
    scrollTo: options => { writes.push(options.top); win.scrollY = options.top; },
  };
  const scroll = createPageScroll({ window: win, document: { documentElement: {} } });
  const change = view => { scroll.save(); scroll.restore(view); };
  const flush = () => { while (frames.length) frames.shift()(); };
  return { win, writes, change, flush };
}

test('document scrolling keeps each page position and ignores stale navigation frames', () => {
  const f = fixture();
  // Initial routing must not mistake the default feed state for a visited page.
  f.change('prompts'); f.flush();
  assert.deepEqual(f.writes, [0]);
  f.win.scrollY = 320;
  f.change('settings'); f.flush();
  f.win.scrollY = 90;
  f.change('prompts'); f.flush();
  assert.equal(f.win.scrollY, 320);
  f.change('prompts'); f.flush();
  assert.deepEqual(f.writes, [0, 0, 320]);
  f.change('settings');
  f.change('feed');
  f.flush();
  assert.deepEqual(f.writes, [0, 0, 320, 0]);
  f.change('settings'); f.flush();
  assert.equal(f.win.scrollY, 90);
});

test('desktop and standalone CSS keep their independent containers untouched', () => {
  const f = fixture(false);
  f.change('prompts'); f.flush();
  f.win.scrollY = 75;
  f.change('feed'); f.flush();
  assert.deepEqual(f.writes, []);
  assert.equal(f.win.scrollY, 75);
});
