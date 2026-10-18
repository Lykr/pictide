import test from 'node:test';
import assert from 'node:assert/strict';
import { loadImagePreferenceScore } from '../web/src/controllers/image-preference-score.mjs';

const settle = () => new Promise(resolve => setImmediate(resolve));
function requests() {
  const pending = [];
  globalThis.fetch = (url, options) => new Promise((resolve, reject) => pending.push({ url, ...options, resolve, reject }));
  return pending;
}
const response = data => ({ ok: true, json: async () => data });

test('closing or switching images ignores late scores and reopening reads fresh preferences', async () => {
  const pending = requests(), received = [];
  const close = loadImagePreferenceScore('old/image', value => received.push(value));
  assert.equal(pending[0].url, '/api/artifacts/old%2Fimage/preference-score');
  close();
  assert.equal(pending[0].signal.aborted, true);
  const switchAway = loadImagePreferenceScore('next', value => received.push(value));
  pending[0].resolve(response({ status: 'scored', love_score: 95 }));
  pending[1].resolve(response({ status: 'scored', love_score: 72.4 }));
  await settle();
  assert.deepEqual(received, [{ status: 'scored', love_score: 72.4 }]);
  switchAway();
  const reopened = loadImagePreferenceScore('next', value => received.push(value));
  pending[2].resolve(response({ status: 'scored', love_score: 68.1 }));
  await settle();
  assert.equal(received.at(-1).love_score, 68.1);
  reopened();
});

test('missing snapshots and undifferentiated scores are kept distinct from request failures', async () => {
  const pending = requests(), received = [];
  const cleanups = [loadImagePreferenceScore('no-snapshot', value => received.push(value)),
    loadImagePreferenceScore('same-scores', value => received.push(value)),
    loadImagePreferenceScore('error', value => received.push(value))];
  pending[0].resolve(response({ status: 'missing_snapshot', love_score: null, reason: 'No snapshot' }));
  pending[1].resolve(response({ status: 'scored', love_score: null, score: 0, score_min: 0, score_max: 0 }));
  pending[2].resolve({ ok: false, json: async () => ({ error: 'Service unavailable' }) });
  await settle();
  assert.equal(received.find(value => value.status === 'missing_snapshot').reason, 'No snapshot');
  assert.equal(received.find(value => value.status === 'scored').love_score, null);
  assert.equal(received.find(value => value.status === 'unavailable').reason, 'Service unavailable');
  for (const cleanup of cleanups) cleanup();
});