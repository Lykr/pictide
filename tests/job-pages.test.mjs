import test from 'node:test';
import assert from 'node:assert/strict';
import { createJobPager, jobPageNumber } from '../web/src/controllers/job-pages.mjs';
const result = (page, total = 65, jobs = [{ id: `page-${page}`, status: 'completed' }]) => ({ jobs, page, page_size: 15, total, total_pages: Math.max(1, Math.ceil(total / 15)) });
const pending = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('page input accepts bounded integers and rejects malformed jumps', () => {
  assert.equal(jobPageNumber(' 2 ', 3), 2);
  for (const value of ['', ' ', '1.5', '1e1', 'x', '0', '-1', 4, Infinity, 9007199254740992]) assert.throws(() => jobPageNumber(value, 3));
});
test('older responses cannot replace a newer navigation or its page count', async () => {
  const first = pending(), second = pending();
  const pager = createJobPager({ request: page => page === 1 ? first.promise : second.promise, changed: () => {} });
  const old = pager.load(1), next = pager.load(2);
  second.resolve(result(2)); await next;
  first.resolve(result(1, 300)); await old;
  assert.equal(pager.state.page, 2); assert.equal(pager.state.totalPages, 5); assert.equal(pager.state.items[0].id, 'page-2');
});
test('background updates preserve the chosen page and coalesce overlapping requests', async () => {
  let calls = [], wait = pending();
  const pager = createJobPager({ request: page => { calls.push(page); return calls.length === 2 ? wait.promise : Promise.resolve(result(page)); }, changed: () => {} });
  await pager.load(2);
  const refresh = pager.load(); pager.load(); pager.load();
  wait.resolve(result(2)); await refresh;
  assert.deepEqual(calls, [2, 2, 2]); assert.equal(pager.state.page, 2);
});
test('failed jumps preserve the previous rows and can retry', async () => {
  let fail = true;
  const pager = createJobPager({ request: page => page === 3 && fail ? Promise.reject(new Error('offline')) : Promise.resolve(result(page)), changed: () => {} });
  await pager.load(2); await pager.load(3);
  assert.equal(pager.state.page, 2); assert.equal(pager.state.items[0].id, 'page-2'); assert.match(pager.state.error, /offline/);
  fail = false; await pager.load(3);
  assert.equal(pager.state.page, 3); assert.equal(pager.state.error, ''); assert.equal(pager.state.loading, false);
});
test('server page correction and empty lists remain usable', async () => {
  const pager = createJobPager({ request: () => Promise.resolve(result(1, 0, [])), changed: () => {} });
  await pager.load(9);
  assert.equal(pager.state.page, 1); assert.equal(pager.state.totalPages, 1); assert.deepEqual(pager.state.items, []); assert.equal(pager.state.loaded, true);
});
test('leaving the task view suppresses a queued refresh', async () => {
  let active = true, calls = 0; const wait = pending();
  const pager = createJobPager({ request: () => { calls++; return wait.promise; }, active: () => active, changed: () => {} });
  const load = pager.load(); pager.load(); active = false; wait.resolve(result(1)); await load;
  assert.equal(calls, 1);
});
