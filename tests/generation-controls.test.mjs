import test from 'node:test';
import assert from 'node:assert/strict';
import { generationCount, generationRepetitions, artifactPath } from '../web/src/controllers/generation-controls.mjs';
import { requestIdentity } from '../web/src/controllers/feed-controls.mjs';
import { submissionDecision } from '../web/src/controllers/rule-controls.mjs';
import { applyArtifactPage, observeArtifactRevision } from '../web/src/controllers/history-controls.mjs';

test('generation count accepts 1–10 whole executions and rejects empty, fractional or unbounded values', () => {
  for (const value of [1, '1', 4, '10', 10]) assert.equal(generationCount(value), Number(value));
  for (const value of ['', ' ', 0, -1, 11, 1.5, 'a', NaN, Infinity, null, undefined, true, []]) assert.throws(() => generationCount(value), /整数/);
});

test('repetitions accepts whole rounds within the plan limit', () => {
  assert.equal(generationRepetitions('10'), 10);
  assert.equal(generationCount('10') * generationRepetitions('10'), 100);
  for (const value of ['', 0, 11, 1.5, null, true, Infinity]) assert.throws(() => generationRepetitions(value), /生成次数/);
});

test('uncertain multi-round retries retain initial rule controls and distinguish changed plans', () => {
  const payload = { backend_id: 'local', positive: '', negative: '', seed: 100, count: 2, repetitions: 3,
    rules: { config: 'default.json', mode: 'sequence', seed: 5, sequence_step: 0, seed_control: 'fixed', step_control: 'increment' } };
  const pending = new Map();
  const first = requestIdentity(payload, pending, () => 'rounds-1'); pending.set(first.key, first);
  assert.equal(requestIdentity(structuredClone(payload), pending, () => 'wrong'), first);
  for (const patch of [{ repetitions: 4 }, { count: 3 }, { rules: { ...payload.rules, sequence_step: 1 } }, { rules: { ...payload.rules, step_control: 'fixed' } }]) {
    assert.equal(submissionDecision({ ...payload, ...patch }, pending, true).retry, null);
  }
  assert.equal(first.payload.rules.sequence_step, 0);
  assert.equal(first.payload.repetitions, 3);
});

test('artifact requests separate generated and roaming images while likes span both sources', () => {
  for (const [view, source] of [['generate', 'generate'], ['feed', 'roam'], ['liked', 'all']]) {
    const query = new URL(artifactPath(view, 'id ?&'), 'http://localhost').searchParams;
    assert.equal(query.get('source'), source);
    assert.equal(query.get('liked'), view === 'liked' ? '1' : null);
    assert.equal(query.get('before'), 'id ?&');
  }
});

test('uncertain batch retry retains the exact count and request ID without advancing automatic prompts', () => {
  const payload = { backend_id: 'local', positive: 'scene', negative: '', seed: -1, count: 3 };
  const pending = new Map();
  const first = requestIdentity(payload, pending, () => 'batch-1'); pending.set(first.key, first);
  const retry = submissionDecision({ ...payload }, pending, true);
  assert.equal(retry.retry, first); assert.equal(retry.generatePrompts, false);
  assert.equal(retry.retry.payload.count, 3); assert.equal(retry.retry.payload.request_id, 'batch-1');
  const changed = submissionDecision({ ...payload, count: 4 }, pending, true);
  assert.equal(changed.retry, null); assert.equal(changed.generatePrompts, true);
  assert.equal(requestIdentity({ ...payload, count: 4 }, pending, () => 'batch-2').payload.request_id, 'batch-2');
  const defaultSingle = requestIdentity({ ...payload, count: undefined }, pending, () => 'single'); pending.set(defaultSingle.key, defaultSingle);
  assert.equal(requestIdentity({ ...payload, count: 1 }, pending, () => 'wrong'), defaultSingle);
});

function store() {
  const page = () => ({ hasMore: true, cursor: 'older', total: 6, loadedMore: true });
  return { artifactRevision: 2, artifacts: [{ id: 'roam' }], generatedArtifacts: [{ id: 'manual-old' }], likedArtifacts: [{ id: 'liked' }], pages: { feed: page(), generate: page(), liked: page() }, currentImage: 'roam' };
}

test('generated refresh and tail pages leave roaming images and pagination untouched', () => {
  const value = store();
  applyArtifactPage(value, 'generate', { revision: 2, artifacts: [{ id: 'manual-new' }], total: 3, has_more: true, counts: { artifacts: 20, roam: 15, generate: 3, liked: 2 } });
  assert.deepEqual(value.generatedArtifacts.map(item => item.id), ['manual-new', 'manual-old']);
  assert.deepEqual(value.artifacts, [{ id: 'roam' }]);
  assert.equal(value.pages.feed.total, 15); assert.equal(value.pages.generate.total, 3); assert.equal(value.pages.liked.total, 2);
  assert.equal(value.pages.feed.cursor, 'older');
  applyArtifactPage(value, 'generate', { revision: 2, artifacts: [{ id: 'manual-old' }, { id: 'oldest' }], total: 3 }, { append: true, requestRevision: 2 });
  assert.equal(value.pages.generate.hasMore, false);
});

test('cleanup invalidates all three image lists and rejects stale generated pages', () => {
  const value = store();
  assert.equal(observeArtifactRevision(value, 3), true);
  for (const list of ['artifacts', 'generatedArtifacts', 'likedArtifacts']) assert.deepEqual(value[list], []);
  for (const view of ['feed', 'generate', 'liked']) assert.equal(value.pages[view].loadedMore, false);
  assert.equal(applyArtifactPage(value, 'generate', { revision: 2, artifacts: [{ id: 'removed' }] }).accepted, false);
  assert.equal(applyArtifactPage(value, 'generate', { revision: 3, artifacts: [{ id: 'old-cursor' }] }, { append: true, requestRevision: 2 }).refresh, true);
  assert.deepEqual(value.generatedArtifacts, []);
});
