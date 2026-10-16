import test from 'node:test';
import assert from 'node:assert/strict';
import { prefetchCount, maxHistoryImages, createRefillCoordinator, isTemporaryRefillError } from '../web/src/controllers/roam-controls.mjs';

test('prefetch counts accept disabled or bounded integer targets', () => {
  for (const value of [0, '0', 3, '20']) assert.equal(prefetchCount(value), Number(value));
  for (const value of ['', ' ', -1, 21, 1.5, 'no', Infinity, null, true, []]) assert.throws(() => prefetchCount(value));
});
test('roam history limit accepts disabled, minimum and maximum retention counts', () => {
  for (const value of [0, '0', 1, '1', 100, 100000, '100000']) assert.equal(maxHistoryImages(value), Number(value));
});
test('roam history limit rejects values outside its bounds and invalid numeric inputs', () => {
  for (const value of [-1, '-1', 100001, '100001', 1.5, '1.5', '', ' ', 'no', NaN, Infinity, null, undefined, true, false, [], {}]) {
    assert.throws(() => maxHistoryImages(value), /历史图片数量上限/);
  }
});
test('overlapping refill events coalesce and follow the latest anchor', async () => {
  let cursor = 'a', release;
  const calls = [], results = [];
  const refill = createRefillCoordinator({ active: () => true, anchor: () => cursor,
    request: anchor => { calls.push(anchor); return calls.length === 1 ? new Promise(resolve => { release = resolve; }) : Promise.resolve('latest'); },
    result: value => results.push(value), error: error => { throw error; } });
  const first = refill(); cursor = 'b'; await refill(); await refill();
  release('stale'); await first;
  assert.deepEqual(calls, ['a', 'b']); assert.deepEqual(results, ['latest']);
});
test('leaving roam stops queued refill events and ignores the in-flight response', async () => {
  let active = true, release, calls = 0;
  const results = [];
  const refill = createRefillCoordinator({ active: () => active, anchor: () => 'a',
    request: () => { calls++; return new Promise(resolve => { release = resolve; }); },
    result: value => results.push(value), error: () => assert.fail() });
  const first = refill(); await refill(); active = false; release('done'); await first; await refill();
  assert.equal(calls, 1); assert.deepEqual(results, []);
});
test('settings changes invalidate old results, and failures do not self-retry', async () => {
  let revision = 0, release;
  const results = [], errors = [];
  const refill = createRefillCoordinator({ active: () => true, anchor: () => 'a', version: () => revision,
    request: () => new Promise(resolve => { release = resolve; }), result: value => results.push(value), error: error => errors.push(error) });
  const pending = refill(); revision++; release('old settings'); await pending;
  assert.deepEqual(results, []);
  let calls = 0;
  const failure = new Error('offline');
  const failing = createRefillCoordinator({ active: () => true, anchor: () => 'a', request: async () => { calls++; throw failure; }, result: () => assert.fail(), error: error => errors.push(error) });
  await failing(); assert.equal(calls, 1); assert.deepEqual(errors, [failure]);
});

test('temporary refill failure resumes on a later event without self-retry', async () => {
  let blocked = false, calls = 0;
  const results = [];
  const refill = createRefillCoordinator({ active: () => !blocked, anchor: () => 'a',
    request: async () => { if (++calls === 1) throw Object.assign(new Error('restarting'), { status: 503 }); return { ready: 2 }; },
    result: response => results.push(response), error: failure => { blocked = !isTemporaryRefillError(failure); } });
  await refill();
  assert.equal(calls, 1); assert.equal(blocked, false);
  await refill(); // A subsequent healthy page refresh / SSE event.
  assert.equal(calls, 2); assert.deepEqual(results, [{ ready: 2 }]);
  assert.equal(isTemporaryRefillError(new TypeError('Failed to fetch')), true);
  assert.equal(isTemporaryRefillError({ status: 429 }), true);
  assert.equal(isTemporaryRefillError({ status: 400 }), false);
});

test('explicit server pause continues to block automatic refill', async () => {
  let blocked = false, calls = 0;
  const refill = createRefillCoordinator({ active: () => !blocked, anchor: () => 'a',
    request: async () => { calls++; return { paused: true }; },
    result: response => { blocked = response.paused; }, error: () => assert.fail() });
  await refill(); await refill();
  assert.equal(calls, 1); assert.equal(blocked, true);
});
