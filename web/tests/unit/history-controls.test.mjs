import test from 'node:test';
import assert from 'node:assert/strict';
import { applyArtifactPage, observeArtifactRevision, retentionDays } from '../../src/controllers/history-controls.mjs';

function store() {
  return {
    artifactRevision: 4,
    artifacts: [{ id: 'new' }, { id: 'old' }], likedArtifacts: [{ id: 'liked' }],
    activeId: 'old', currentImage: 'old',
    pages: { feed: { total: 3, cursor: 'old', hasMore: true, loadedMore: false }, liked: { total: 1, cursor: 'liked', hasMore: false, loadedMore: false } },
  };
}
const page = (revision, ids, options = {}) => ({ revision, artifacts: ids.map((id) => ({ id })), has_more: false, total: ids.length, ...options });

test('retention setting accepts bounded whole days and zero to disable', () => {
  for (const value of [0, '0', 7, '7', 3650, '3650']) assert.equal(retentionDays(value), Number(value));
  for (const value of ['', '  ', -1, '7.5', 3651, Infinity, NaN, 'abc', true, null, undefined, []]) assert.throws(() => retentionDays(value), /整数/);
});

test('ordinary first-page refresh preserves older loaded pages and cursor', () => {
  const value = store(); value.pages.feed.loadedMore = true;
  const result = applyArtifactPage(value, 'feed', page(4, ['fresh', 'new'], { total: 4, has_more: true, next_cursor: 'new' }));
  assert.equal(result.accepted, true);
  assert.deepEqual(value.artifacts.map((item) => item.id), ['fresh', 'new', 'old']);
  assert.equal(value.pages.feed.cursor, 'old');
  assert.equal(value.pages.feed.loadedMore, true);
});

test('normal load-more merges pages without duplicating rows', () => {
  const value = store();
  applyArtifactPage(value, 'feed', page(4, ['old', 'older'], { total: 3, next_cursor: 'older' }), { append: true, requestRevision: 4 });
  assert.deepEqual(value.artifacts.map((item) => item.id), ['new', 'old', 'older']);
  assert.equal(value.pages.feed.cursor, 'older');
  assert.equal(value.pages.feed.hasMore, false);
});

test('deletion revision replaces current list and clears both pagination caches', () => {
  const value = store(); value.pages.feed.loadedMore = true;
  const result = applyArtifactPage(value, 'feed', page(5, ['new'], { counts: { artifacts: 1, liked: 0 } }));
  assert.equal(result.reset, true);
  assert.deepEqual(value.artifacts, [{ id: 'new' }]);
  assert.deepEqual(value.likedArtifacts, []);
  assert.equal(value.pages.feed.loadedMore, false);
  assert.equal(value.pages.liked.total, 0);
  assert.equal(value.currentImage, 'old'); // Renderer owns the displayed image until it selects a replacement.
  assert.equal(value.activeId, 'old'); // Renderer selects first available if this id is absent.
});

test('list invalidation retains the loaded image state when the current image survives', () => {
  const value = { ...store(), imageReady: true };
  applyArtifactPage(value, 'feed', page(5, ['old']), { replace: true });
  assert.equal(value.currentImage, 'old');
  assert.equal(value.imageReady, true);
  assert.equal(value.activeId, 'old');
  assert.deepEqual(value.artifacts, [{ id: 'old' }]);
});

test('a late old first page cannot resurrect removed artifacts in either list', () => {
  const value = store();
  applyArtifactPage(value, 'feed', page(5, ['new']));
  for (const view of ['feed', 'liked']) {
    const result = applyArtifactPage(value, view, page(4, ['old']));
    assert.equal(result.accepted, false);
  }
  assert.deepEqual(value.artifacts, [{ id: 'new' }]); assert.deepEqual(value.likedArtifacts, []);
});

test('new revision first seen in a tail page invalidates caches and requests a fresh first page', () => {
  const value = store();
  const result = applyArtifactPage(value, 'feed', page(5, ['older']), { append: true, requestRevision: 4 });
  assert.deepEqual(result, { accepted: false, reset: true, refresh: true });
  assert.deepEqual(value.artifacts, []); assert.deepEqual(value.likedArtifacts, []);
  applyArtifactPage(value, 'feed', page(5, ['new']));
  assert.deepEqual(value.artifacts, [{ id: 'new' }]);
});

test('tail requested before cleanup stays invalid even if server response has the latest revision', () => {
  const value = store();
  applyArtifactPage(value, 'feed', page(5, ['fresh']));
  const result = applyArtifactPage(value, 'feed', page(5, ['old-cursor-tail']), { append: true, requestRevision: 4 });
  assert.equal(result.accepted, false); assert.equal(result.refresh, true);
  assert.deepEqual(value.artifacts, [{ id: 'fresh' }]);
});

test('revision notifications are monotonic and repeated observations keep the current cache', () => {
  const value = store();
  for (const revision of [undefined, null, -1, 3, 4]) assert.equal(observeArtifactRevision(value, revision), false);
  assert.deepEqual(value.artifacts.map((item) => item.id), ['new', 'old']);
  assert.equal(observeArtifactRevision(value, 5), true);
  value.artifacts = [{ id: 'fresh' }];
  assert.equal(observeArtifactRevision(value, 5), false);
  assert.deepEqual(value.artifacts, [{ id: 'fresh' }]);
});
