import test from 'node:test';
import assert from 'node:assert/strict';
import { createRecentUnlikes } from '../../src/controllers/recent-unlikes.mjs';

const serverTime = Date.parse('2026-11-05T00:00:00Z');
const image = (id, minutes = 120) => ({ id, feedback: null, unliked_protected_until: new Date(serverTime + minutes * 60000).toISOString() });
const window = (items, extra = {}) => ({ artifacts: items, total: items.length, has_more: false, next_cursor: null, server_time: new Date(serverTime).toISOString(), ...extra });
const flush = () => new Promise(resolve => setImmediate(resolve));
const create = options => createRecentUnlikes({ schedule: () => 1, unschedule() {}, ...options });

test('recovery opens fresh independently of liked filters; failed pagination retries the same cursor', async () => {
  const calls = [];
  const service = create({ request: async path => {
    calls.push(path);
    if (calls.length === 1) return window([image('a')], { total: 2, has_more: true, next_cursor: '["time","a"]' });
    if (calls.length === 2) throw new Error('Offline');
    return window([image('a'), image('b')], { total: 2 });
  } });
  await service.invalidate(); assert.equal(calls.length, 0);
  service.setOpen(true); await flush();
  await service.more(); assert.equal(service.model.data.error, 'Offline');
  assert.equal(service.model.data.artifacts.length, 1);
  await service.retry();
  assert.equal(calls[1], calls[2]);
  assert.equal(new URL(calls[1], 'http://local').searchParams.get('before'), '["time","a"]');
  assert.deepEqual(service.model.data.artifacts.map(item => item.id), ['a', 'b']);
  assert.equal(service.model.data.error, '');
  service.setOpen(false); service.setOpen(true);
  assert.equal(service.model.data.artifacts.length, 0);
  await flush(); assert.equal(calls.length, 4);
  service.dispose();
});

test('closing or restoring discards late responses instead of resurrecting recovered images', async () => {
  const requests = [];
  const service = create({ request: (path, { signal }) => new Promise(resolve => requests.push({ resolve, signal })) });
  service.setOpen(true);
  service.setOpen(false);
  assert.equal(requests[0].signal.aborted, true);
  requests[0].resolve(window([image('old')])); await flush();
  assert.equal(service.model.data.artifacts.length, 0);
  service.setOpen(true);
  requests[1].resolve(window([image('new')])); await flush();
  const pending = service.invalidate();
  service.remove('new');
  requests[2].resolve(window([image('new')])); await pending;
  assert.equal(requests[2].signal.aborted, true);
  assert.equal(service.model.data.artifacts.length, 0);
  assert.equal(service.model.data.loading, false);
  service.dispose();
});

test('remaining protection uses server time despite a skewed device clock and expires in an open dialog', async () => {
  let local = 1, tick, cleared;
  const service = createRecentUnlikes({ clock: () => local, schedule: callback => { tick = callback; return 7; }, unschedule: id => { cleared = id; },
    request: async () => window([image('short', 1), image('long', 120)]) });
  service.setOpen(true); await flush();
  assert.equal(service.model.data.now, serverTime);
  local += 60000; tick();
  assert.deepEqual(service.model.data.artifacts.map(item => item.id), ['long']);
  assert.equal(service.model.data.total, 1);
  service.setOpen(false); assert.equal(cleared, 7);
  service.dispose();
});

test('a feedback refresh cancels an older page request and keeps its newer authoritative state', async () => {
  const requests = [];
  const service = create({ request: (path, { signal }) => new Promise(resolve => requests.push({ resolve, signal })) });
  service.setOpen(true);
  requests[0].resolve(window([image('a')], { total: 2, has_more: true, next_cursor: 'cursor' })); await flush();
  const more = service.more();
  const refreshed = service.invalidate();
  requests[2].resolve(window([image('b')])); await refreshed;
  requests[1].resolve(window([image('a')])); await more;
  assert.deepEqual(service.model.data.artifacts.map(item => item.id), ['b']);
  assert.equal(service.model.data.hasMore, false);
  service.dispose();
});
