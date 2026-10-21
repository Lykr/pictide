import test from 'node:test';
import assert from 'node:assert/strict';
import { createLikedRanking } from '../../src/controllers/liked-ranking.mjs';
import { applyArtifactPage, observeArtifactRevision } from '../../src/controllers/history-controls.mjs';

const artifacts = Array.from({ length: 34 }, (_, i) => ({ id: String(i), feedback: 1 }));
test('ranked liked browsing keeps server order and pages locally, including an unlike', async () => {
  const artifacts = Array.from({ length: 234 }, (_, i) => ({ id: String(i), feedback: 1 }));
  let calls = 0, latest;
  const ranked = createLikedRanking({ request: async path => {
    calls++; assert.equal(path, '/api/liked/ranked?tag=blue+sky&tag=solo');
    return { artifacts, scoring_available: true };
  }, changed: value => { latest = value; } });
  await ranked.load(['blue sky', 'solo', 'solo']);
  assert.equal(latest.artifacts.length, 100); assert.equal(latest.total, 234);
  ranked.more(); assert.equal(latest.artifacts.length, 200);
  ranked.update({ id: '2', feedback: null });
  assert.deepEqual(latest.artifacts.map(item => item.id), artifacts.filter(item => item.id !== '2').slice(0, 200).map(item => item.id));
  ranked.update({ id: 'outside', feedback: 1 }); assert.equal(latest.total, 233);
  ranked.more(); assert.equal(latest.hasMore, false); assert.equal(calls, 1);
});

test('only explicit refresh posts the current filter and local pagination keeps scores and server refresh time', async () => {
  const calls = []; let latest;
  const ranked = createLikedRanking({ request: async (path, options) => {
    calls.push({ path, ...options });
    return { artifacts, scoring_available: true, refreshed_at: calls.length > 1 ? "2026-10-18T11:00:00+00:00" : null };
  }, changed: value => { latest = value; } });
  await ranked.load(['solo']);
  assert.equal(calls[0].path, '/api/liked/ranked?tag=solo');
  assert.equal(calls[0].method, undefined);
  assert.equal(latest.refreshedAt, null);
  await ranked.load(['blue sky', 'solo', 'solo'], true);
  assert.equal(calls[1].path, '/api/liked/ranked/refresh');
  assert.equal(calls[1].method, 'POST');
  assert.deepEqual(JSON.parse(calls[1].body), { tags: ['blue sky', 'solo'] });
  ranked.more();
  assert.equal(latest.artifacts.length, 34);
  assert.equal(calls.length, 2);
  assert.equal(latest.refreshedAt, "2026-10-18T11:00:00+00:00");
});

test('filter changes and navigation discard late requests; backend and HTTP errors stay visible', async () => {
  const requests = []; let latest;
  const ranked = createLikedRanking({ request: (path, options) => new Promise((resolve, reject) => requests.push({ path, ...options, resolve, reject })), changed: value => { latest = value; } });
  const old = ranked.load(['old'], true); const current = ranked.load(['new']);
  assert.equal(requests[0].signal.aborted, true);
  requests[1].resolve({ artifacts: artifacts.slice(3, 4), scoring_available: false, error: 'Encoder unavailable' }); await current;
  requests[0].resolve({ artifacts, scoring_available: true, refreshed_at: '2026-10-18T11:00:00+00:00' }); await old;
  assert.equal(latest.refreshedAt, null);
  assert.deepEqual(latest.artifacts.map(item => item.id), ['3']); assert.equal(latest.error, 'Encoder unavailable');
  const failed = ranked.load(); requests[2].reject(new Error('HTTP 503')); await failed;
  assert.equal(latest.error, 'HTTP 503'); assert.equal(latest.loading, false);
  const leaving = ranked.load(); ranked.cancel(); requests[3].resolve({ artifacts, scoring_available: true }); await leaving;
  assert.deepEqual(ranked.snapshot().artifacts.map(item => item.id), ['3']);
});

test('other collections and deletion revisions preserve a ranked liked browsing snapshot', () => {
  const page = { total: 34, hasMore: true, loaded: true, cursor: null };
  const state = { likedSort: 'score', artifactRevision: 1, artifacts: [], likedArtifacts: artifacts.slice(0, 15), generatedArtifacts: [], pages: { feed: {}, liked: page, generate: {} } };
  observeArtifactRevision(state, 2);
  assert.equal(state.pages.liked, page); assert.equal(state.likedArtifacts.length, 15);
  applyArtifactPage(state, 'generate', { artifacts: [], revision: 2, counts: { liked: 99 } });
  assert.equal(state.pages.liked.total, 34);
});
