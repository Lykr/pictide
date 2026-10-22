import { test } from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { createRequestId } from '../../src/shared/request-id.mjs';
import { requestIdentity } from '../../src/controllers/feed-controls.mjs';

test('native UUID generation preserves its crypto receiver', t => {
  const crypto = { randomUUID() { assert.equal(this, crypto); return 'native-id'; } };
  t.mock.getter(globalThis, 'crypto', () => crypto);
  assert.equal(createRequestId(), 'native-id');
});

test('LAN fallback creates v4 IDs and uncertain retries keep their original identity', t => {
  t.mock.getter(globalThis, 'crypto', () => ({ getRandomValues: value => webcrypto.getRandomValues(value) }));
  const ids = Array.from({ length: 100 }, createRequestId);
  for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(new Set(ids).size, ids.length);
  const pending = new Map();
  const first = requestIdentity({ positive: 'garden' }, pending, createRequestId);
  pending.set(first.key, first);
  assert.equal(requestIdentity({ positive: 'garden' }, pending, createRequestId), first);
  assert.notEqual(requestIdentity({ positive: 'sunlight' }, pending, createRequestId).payload.request_id, first.payload.request_id);
});
