import assert from 'node:assert/strict';
import test from 'node:test';
import { createPictideGuide } from '../../src/onboarding/pictide-adapter.mjs';
import { GUIDE_STORAGE_KEY } from '../../src/onboarding/pictide-flow.mjs';

function harness(overrides = {}, sharedStorage = new Map()) {
  let facts = {
    ready: true, route: 'feed', backendCount: 0, apiDraftRevision: 0,
    apiTestedRevision: -1, apiSavedRevision: -1, apiTestPending: false, apiSavePending: false,
    waiting: false, imageId: null, imageReady: false, imageFeedback: 0,
    roamPrivacy: true, likedPrivacy: true, anchorOpen: false, anchorCount: 0,
    anchorsEditable: true, anchorRevision: 0, likedLoading: false, likedTotal: 0,
    ...overrides,
  };
  const subscribers = new Set();
  const navigations = [];
  const guide = createPictideGuide({
    readFacts: () => facts,
    subscribeFacts(callback) { subscribers.add(callback); return () => subscribers.delete(callback); },
    navigate: route => navigations.push(route),
    storage: { getItem: key => sharedStorage.get(key), setItem: (key, value) => sharedStorage.set(key, value) },
  });
  return {
    guide, sharedStorage, navigations,
    update(patch) { facts = { ...facts, ...patch }; for (const callback of subscribers) callback(); },
    step: () => guide.getSnapshot().stepId,
  };
}

test('API test and save belong to the current draft; stale or failed operations cannot advance', () => {
  const h = harness();
  assert.equal(h.guide.getSnapshot().status, 'invite');
  h.guide.act('start');
  assert.deepEqual(h.navigations, ['settings/backend']);
  h.update({ route: 'settings/backend', apiDraftRevision: 1 });
  assert.equal(h.step(), 'api-config');
  h.update({ apiTestedRevision: 0 });
  assert.equal(h.step(), 'api-config');
  h.update({ apiTestedRevision: 1 });
  assert.equal(h.step(), 'api-save');
  h.update({ apiDraftRevision: 2 });
  assert.equal(h.step(), 'api-config');
  h.update({ apiTestedRevision: 2, apiSavedRevision: 1 });
  assert.equal(h.step(), 'api-save');
  h.update({ apiSavedRevision: 2, apiSavePending: true, backendCount: 1 });
  assert.equal(h.step(), 'api-save');
  h.update({ apiSavePending: false });
  assert.equal(h.step(), 'api-ready');
  assert.equal(h.navigations.length, 1, 'saving does not navigate automatically');
  h.guide.act('back-to-roam');
  assert.equal(h.step(), 'roam-start');
  assert.equal(h.navigations.at(-1), 'feed');
});

test('fast images skip pending; next is optional and a real saved like advances without replaying feedback', () => {
  const h = harness({ backendCount: 1 });
  h.guide.act('start');
  h.update({ imageId: 'first', imageReady: true });
  assert.equal(h.step(), 'roam-reveal');
  h.update({ roamPrivacy: false });
  assert.equal(h.step(), 'roam-feedback');
  h.update({ imageId: 'second', imageFeedback: 0 });
  assert.equal(h.step(), 'roam-feedback');
  assert(!h.guide.getSnapshot().messages.join('').includes('第一张'));
  h.update({ imageFeedback: 1 });
  assert.equal(h.step(), 'anchors-open');
  assert(h.guide.getSnapshot().messages[0].includes('找到喜欢的了'));
  assert.deepEqual(h.navigations, ['feed'], 'the guide only explicitly navigates');
});

test('existing images are current, existing likes do not pretend a new success; liking while blurred is retained', () => {
  const existing = harness({ backendCount: 1, imageId: 'old', imageReady: true, imageFeedback: 1, roamPrivacy: false });
  existing.guide.act('start');
  assert.equal(existing.step(), 'roam-feedback');
  assert(!existing.guide.getSnapshot().messages[0].includes('第一张'));
  existing.update({ imageId: 'another-historically-liked', imageFeedback: 1 });
  assert.equal(existing.step(), 'roam-feedback', 'opening a previously liked image is not a new saved like');
  existing.guide.act('learn-anchors');
  assert.equal(existing.step(), 'anchors-open');
  assert(!existing.guide.getSnapshot().messages[0].includes('找到喜欢的了'));
  const h = harness({ backendCount: 1, imageId: 'current', imageReady: true });
  h.guide.act('start');
  h.update({ imageFeedback: 1 });
  assert.equal(h.step(), 'roam-reveal');
  h.update({ roamPrivacy: false });
  assert.equal(h.step(), 'anchors-open');
});

test('anchor clear remains across further images and collapsed panels; next requires another image', () => {
  const h = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false });
  h.guide.act('start');
  h.guide.act('learn-anchors');
  h.update({ anchorOpen: true });
  assert.equal(h.step(), 'anchors-pick');
  h.update({ anchorCount: 1, anchorRevision: 1 });
  assert.equal(h.step(), 'anchors-next');
  h.update({ imageReady: false });
  assert.equal(h.step(), 'anchors-next');
  h.update({ imageId: 'b', imageReady: true });
  assert.equal(h.step(), 'anchors-clear');
  h.update({ imageId: 'c', anchorOpen: false });
  assert.equal(h.step(), 'anchors-clear');
  assert.deepEqual(h.guide.getSnapshot().targets, ['anchors.trigger']);
  h.update({ anchorOpen: true });
  assert.deepEqual(h.guide.getSnapshot().targets, ['anchors.clear']);
  h.update({ anchorCount: 0, anchorRevision: 2 });
  assert.equal(h.step(), 'cleared-next');
  h.update({ waiting: true });
  assert.equal(h.step(), 'cleared-next', 'current ready image cannot stand for another image');
  h.update({ imageId: 'd', waiting: false });
  assert.equal(h.step(), 'liked-open');
  h.update({ route: 'liked', likedTotal: 1 });
  assert.equal(h.step(), 'liked-reveal');
  h.update({ likedPrivacy: false, likedLoading: true });
  assert.equal(h.step(), 'liked-reveal');
  h.update({ likedLoading: false });
  assert.equal(h.step(), 'finish');
  const navigationsBeforeFinish = [...h.navigations];
  h.guide.act('finish');
  assert.deepEqual(h.navigations, navigationsBeforeFinish, 'finishing preserves the current page instead of navigating away');
  h.update({ likedTotal: 2 });
  assert.equal(h.guide.getSnapshot().status, 'idle');
  const refreshed = harness({ backendCount: 1 }, h.sharedStorage);
  assert.equal(refreshed.guide.getSnapshot().status, 'idle');
});

test('refresh offers resume, handles already-cleared anchors, and stores no secrets or observed draft', () => {
  const h = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false, privateKey: 'secret' });
  h.guide.act('start');
  h.guide.act('learn-anchors');
  h.update({ anchorOpen: true });
  h.update({ anchorCount: 1, anchorRevision: 1 });
  h.update({ imageId: 'b' });
  assert.equal(h.step(), 'anchors-clear');
  const raw = h.sharedStorage.get(GUIDE_STORAGE_KEY);
  assert(!raw.includes('secret'));
  assert(!raw.includes('apiDraftRevision'));
  const refreshed = harness({ backendCount: 1, imageId: 'b', imageReady: true, anchorCount: 0 }, h.sharedStorage);
  assert.equal(refreshed.guide.getSnapshot().status, 'resume');
  assert.deepEqual(refreshed.navigations, []);
  refreshed.update({ likedTotal: 1 });
  const stillResumable = harness({ backendCount: 1 }, h.sharedStorage);
  assert.equal(stillResumable.guide.getSnapshot().status, 'resume', 'refreshing an unanswered resume offer preserves progress');
  refreshed.guide.act('resume');
  assert.equal(refreshed.step(), 'cleared-next');
  assert.deepEqual(refreshed.navigations, ['feed']);
});

test('existing anchors still require a successful edit in this guide before the next image', () => {
  const h = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false, anchorCount: 2, anchorRevision: 4 });
  h.guide.act('start');
  h.guide.act('learn-anchors');
  h.update({ anchorOpen: true });
  assert.equal(h.step(), 'anchors-pick', 'opening existing pins must show the editing instruction');
  h.update({ unrelated: 'rerender' });
  assert.equal(h.step(), 'anchors-pick');
  h.update({ anchorsEditable: false });
  h.update({ anchorsEditable: true });
  assert.equal(h.step(), 'anchors-pick', 'a failed request does not change the confirmed revision');
  h.update({ anchorCount: 3, anchorRevision: 5, anchorsEditable: false });
  assert.equal(h.step(), 'anchors-pick', 'wait for editing to finish');
  h.update({ anchorsEditable: true });
  assert.equal(h.step(), 'anchors-next');
  h.update({ imageId: 'b' });
  assert.equal(h.step(), 'anchors-clear');
});

test('clearing anchors during selection requires a later successful selection and remains skippable', () => {
  const h = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false, anchorCount: 1, anchorRevision: 2 });
  h.guide.act('start');
  h.guide.act('learn-anchors');
  h.update({ anchorOpen: true });
  h.update({ anchorCount: 0, anchorRevision: 3 });
  assert.equal(h.step(), 'anchors-pick', 'clearing is not selecting an element to preserve');
  h.update({ anchorCount: 1 });
  assert.equal(h.step(), 'anchors-pick', 'count alone cannot stand for a confirmed edit');
  h.update({ anchorRevision: 4 });
  assert.equal(h.step(), 'anchors-next');
  h.update({ anchorCount: 0, anchorRevision: 5 });
  assert.equal(h.step(), 'anchors-pick');
  h.guide.act('skip-anchors');
  assert.equal(h.step(), 'liked-open');
});

test('resuming anchor selection uses a fresh live revision baseline without storing local counters', () => {
  const h = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false, anchorCount: 1, anchorRevision: 8 });
  h.guide.act('start');
  h.guide.act('learn-anchors');
  h.update({ anchorOpen: true });
  assert.equal(h.step(), 'anchors-pick');
  const record = JSON.parse(h.sharedStorage.get(GUIDE_STORAGE_KEY));
  assert(!('anchorPickRevision' in record.context));
  assert(!('anchorRevision' in record.context));
  // Inject an old local counter to ensure restoration does not trust it.
  record.context.anchorPickRevision = 8;
  h.sharedStorage.set(GUIDE_STORAGE_KEY, JSON.stringify(record));
  const refreshed = harness({ backendCount: 1, imageId: 'a', imageReady: true, roamPrivacy: false, anchorOpen: true, anchorCount: 1, anchorRevision: 0 }, h.sharedStorage);
  refreshed.guide.act('resume');
  assert.equal(refreshed.step(), 'anchors-pick', 'a page-local counter reset is not an edit');
  refreshed.update({ anchorCount: 2, anchorRevision: 1 });
  assert.equal(refreshed.step(), 'anchors-next');
});

test('dismiss persists and cached snapshots remain stable until visible content changes', () => {
  const h = harness();
  const before = h.guide.getSnapshot();
  h.update({ irrelevant: 'changed' });
  assert.equal(h.guide.getSnapshot(), before);
  h.guide.act('dismiss');
  h.update({ imageId: 'unrelated' });
  const refreshed = harness({}, h.sharedStorage);
  assert.equal(refreshed.guide.getSnapshot().status, 'idle');
  refreshed.guide.act('restart');
  assert.equal(refreshed.step(), 'api-config');
});

test('early component publications and undecided invitations never suppress the ready invitation', () => {
  const h = harness({ ready: false });
  h.update({ roamPrivacy: false });
  h.update({ anchorOpen: true });
  assert.equal(h.guide.getSnapshot().status, 'idle');
  assert.equal(h.sharedStorage.size, 0);
  h.update({ ready: true });
  assert.equal(h.guide.getSnapshot().status, 'invite');
  h.update({ likedPrivacy: false });
  assert.equal(h.sharedStorage.size, 0);
  const refreshed = harness({}, h.sharedStorage);
  assert.equal(refreshed.guide.getSnapshot().status, 'invite');
  const staleInvite = new Map([[GUIDE_STORAGE_KEY, JSON.stringify({ version: 1, status: 'invite' })]]);
  const old = harness({ ready: false }, staleInvite);
  old.update({ anchorOpen: false });
  old.update({ ready: true });
  assert.equal(old.guide.getSnapshot().status, 'invite');
});

test('resuming after the saved API was removed returns to configuration without replaying operations', () => {
  for (const stepId of ['roam-start', 'roam-pending', 'anchors-clear', 'liked-reveal']) {
    const sharedStorage = new Map([[GUIDE_STORAGE_KEY, JSON.stringify({
      version: 1, status: 'active', stepId, context: { firstImage: true, imageId: 'old' },
    })]]);
    const h = harness({ ready: true, backendCount: 0 }, sharedStorage);
    assert.equal(h.guide.getSnapshot().status, 'resume');
    assert.deepEqual(h.navigations, [], 'restoration itself does not navigate or replay requests');
    h.guide.act('resume');
    assert.equal(h.step(), 'api-config');
    assert.deepEqual(h.guide.getSnapshot().targets, ['api.form', 'api.test']);
    assert.deepEqual(h.navigations, ['settings/backend'], 'confirmation only navigates to API settings');
  }
  const fresh = harness({ backendCount: 1 });
  fresh.guide.act('start');
  assert.equal(fresh.guide.getSnapshot().messages[0], '点「开始漫游」，看看第一张。');
});
