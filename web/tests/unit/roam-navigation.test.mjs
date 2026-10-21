import test from 'node:test';
import assert from 'node:assert/strict';
import { createGalleryCursors, createNextImageWait, roamArtifactPath, roamBoundaryAction, resolveGalleryCursor } from '../../src/controllers/roam-navigation.mjs';
import { applyArtifactPage, observeArtifactRevision } from '../../src/controllers/history-controls.mjs';

test('restoration precedes selection and likes never overwrite the persisted roam cursor', () => {
  const gallery = createGalleryCursors();
  assert.equal(gallery.select('feed', 'newest', 1), null);
  gallery.restore({ artifact_id: 'last-watched', viewed_at: 100 });
  assert.equal(gallery.get('feed'), 'last-watched');
  assert.equal(gallery.select('liked', 'favorite', 200), null);
  assert.equal(gallery.get('liked'), 'favorite');
  assert.equal(gallery.get('feed'), 'last-watched');
  gallery.restore({ artifact_id: 'newest' });
  assert.equal(gallery.get('feed'), 'last-watched');
});

test('only changed cursors produce writes, with increasing stamps even if the clock moves backwards', () => {
  const gallery = createGalleryCursors(); gallery.restore({ artifact_id: 'a', viewed_at: 500 });
  assert.equal(gallery.select('feed', 'a', 1000), null);
  assert.deepEqual(gallery.select('feed', 'b', 600), { artifact_id: 'b', viewed_at: 600 });
  assert.deepEqual(gallery.select('feed', 'c', 550), { artifact_id: 'c', viewed_at: 601 });
  assert.equal(gallery.select('feed', 'c', 5000), null);
});

test('a new gallery can persist its first image and a cleanup can persist the replacement', () => {
  const gallery = createGalleryCursors(); gallery.restore();
  assert.deepEqual(gallery.select('feed', 'first', 1), { artifact_id: 'first', viewed_at: 1 });
  assert.deepEqual(gallery.select('feed', 'neighbor', 2), { artifact_id: 'neighbor', viewed_at: 2 });
});

test('duplicate right presses share one intent and task events advance exactly once to the closest next image', () => {
  const wait = createNextImageWait();
  const first = wait.begin('a'); assert.ok(first);
  assert.equal(wait.begin('a'), null);
  assert.equal(wait.consume([{ id: 'a' }], 'a', true), null);
  assert.equal(wait.consume([{ id: 'far' }, { id: 'next' }, { id: 'a' }], 'a', true), 'next');
  assert.equal(wait.consume([{ id: 'far' }, { id: 'next' }, { id: 'a' }], 'a', true), null);
  assert.equal(wait.current, null);
});

test('leaving or moving away cancels the intended automatic advance', () => {
  const wait = createNextImageWait(); wait.begin('a');
  assert.equal(wait.consume([{ id: 'b' }, { id: 'a' }], 'a', false), null);
  assert.equal(wait.consume([{ id: 'b' }, { id: 'a' }], 'different', true), null);
  wait.cancel();
  assert.equal(wait.consume([{ id: 'b' }, { id: 'a' }], 'a', true), null);
});

test('empty roam selects the first chronological image in a multi-image result', () => {
  const wait = createNextImageWait(); wait.begin(null);
  assert.equal(wait.consume([{ id: 'second' }, { id: 'first' }], null, true), 'first');
});

test('oldest boundary is silent and only the actual newest boundary demands generation', () => {
  assert.equal(roamBoundaryAction('older', { hasMore: false }), 'idle');
  assert.equal(roamBoundaryAction('older', { hasMore: true }), 'load');
  assert.equal(roamBoundaryAction('newer', { hasNewer: true }), 'load');
  assert.equal(roamBoundaryAction('newer', { hasNewer: false }), 'generate');
  const path = new URL(roamArtifactPath('watched/id'), 'http://local');
  assert.equal(path.searchParams.get('around'), 'watched/id');
  assert.equal(path.searchParams.has('before'), false);
});

test('roam windows replace rather than splice disjoint history, and cleanup retains cursor ownership', () => {
  const store = { artifactRevision: 0, artifacts: [{ id: 'far-newest' }, { id: 'old' }], likedArtifacts: [], activeId: 'middle', pages: {
    feed: { loadedMore: true }, liked: {},
  } };
  applyArtifactPage(store, 'feed', { revision: 0, artifacts: [{ id: 'near-newer' }, { id: 'middle' }, { id: 'near-older' }], total: 900, has_more: true, has_newer: true, next_cursor: 'near-older' }, { replace: true });
  assert.deepEqual(store.artifacts.map(item => item.id), ['near-newer', 'middle', 'near-older']);
  assert.equal(store.pages.feed.hasNewer, true);
  assert.equal(store.pages.feed.cursor, 'near-older');
  assert.equal(store.pages.feed.total, 900);
  assert.equal(store.pages.feed.loadedMore, false);
  observeArtifactRevision(store, 1);
  assert.equal(store.activeId, 'middle');
  assert.equal(store.pages.feed.loaded, false);
  assert.deepEqual(resolveGalleryCursor(store.artifacts, store.activeId, store.pages.feed.loaded), { loading: true, id: 'middle' });
  applyArtifactPage(store, 'feed', { revision: 1, artifacts: [{ id: 'middle' }], total: 899 }, { replace: true });
  assert.deepEqual(resolveGalleryCursor(store.artifacts, store.activeId, store.pages.feed.loaded), { loading: false, id: 'middle' });
  assert.deepEqual(resolveGalleryCursor([], 'favorite', false), { loading: true, id: 'favorite' });
  assert.deepEqual(resolveGalleryCursor([], 'deleted', true), { loading: false, id: null });
});
