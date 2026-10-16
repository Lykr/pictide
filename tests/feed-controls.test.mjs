import test from 'node:test';
import assert from 'node:assert/strict';
import { destinationIndex, keyboardAction, feedbackValue, mergeArtifacts, requestIdentity, configuredWorkflowMode, effectiveWorkflowMode } from '../web/src/controllers/feed-controls.mjs';

const context = { editing: false, dialogOpen: false, view: 'feed', feedbackPending: false };

test('left goes older and right goes newer in newest-first order', () => {
  assert.equal(keyboardAction({ key: 'ArrowLeft' }, context), 'older');
  assert.equal(keyboardAction({ key: 'ArrowRight' }, context), 'newer');
  assert.equal(destinationIndex(2, 5, 'older'), 3);
  assert.equal(destinationIndex(2, 5, 'newer'), 1);
});

test('navigation stops at both boundaries and on empty feed', () => {
  assert.equal(destinationIndex(0, 5, 'newer'), null);
  assert.equal(destinationIndex(4, 5, 'older'), null);
  assert.equal(destinationIndex(-1, 0, 'older'), null);
  assert.equal(destinationIndex(0, 1, 'older'), null);
  assert.equal(destinationIndex(0, 1, 'newer'), null);
});

test('up likes and down dislikes only in roam, including immersive mode', () => {
  assert.equal(keyboardAction({ key: 'ArrowUp' }, context), 'like');
  assert.equal(keyboardAction({ key: 'ArrowDown' }, context), 'dislike');
  assert.equal(keyboardAction({ key: 'ArrowDown' }, { ...context, immersive: true }), 'dislike');
  assert.equal(keyboardAction({ key: 'ArrowDown' }, { ...context, view: 'generate' }), null);
  assert.equal(keyboardAction({ key: 'ArrowDown' }, { ...context, view: 'liked' }), null);
});

test('hotkeys ignore repeated or modified presses', () => {
  for (const property of ['repeat', 'ctrlKey', 'altKey', 'metaKey', 'shiftKey']) {
    assert.equal(keyboardAction({ key: 'ArrowRight', [property]: true }, context), null);
  }
});

test('space toggles privacy in normal and immersive roam and respects input guards', () => {
  const immersive = { ...context, immersive: true };
  for (const key of [' ', 'Spacebar']) {
    assert.equal(keyboardAction({ key }, immersive), 'privacy');
    assert.equal(keyboardAction({ key }, context), 'privacy');
    assert.equal(keyboardAction({ key }, { ...context, view: 'generate' }), 'privacy');
    assert.equal(keyboardAction({ key }, { ...immersive, view: 'liked' }), 'privacy');
    for (const property of ['repeat', 'ctrlKey', 'altKey', 'metaKey', 'shiftKey']) {
      assert.equal(keyboardAction({ key, [property]: true }, immersive), null);
    }
    for (const patch of [{ editing: true }, { dialogOpen: true }, { feedbackPending: true }]) {
      assert.equal(keyboardAction({ key }, { ...immersive, ...patch }), null);
    }
  }
  assert.equal(keyboardAction({ key: 'ArrowLeft' }, { ...context, view: 'generate' }), null);
  assert.equal(keyboardAction({ key: ' ', editing: false }, { ...context, view: 'generate', editing: true }), null);
});

test('hotkeys ignore edit fields, dialogs, records and pending feedback', () => {
  for (const patch of [{ editing: true }, { dialogOpen: true }, { view: 'jobs' }, { feedbackPending: true }]) {
    assert.equal(keyboardAction({ key: 'ArrowUp' }, { ...context, ...patch }), null);
    assert.equal(keyboardAction({ key: 'ArrowDown' }, { ...context, ...patch }), null);
  }
  assert.equal(keyboardAction({ key: 'Enter' }, context), null);
});

test('keyboard feedback is idempotent while buttons can withdraw', () => {
  assert.equal(feedbackValue(1, 1, false), 1);
  assert.equal(feedbackValue(1, 1, true), null);
  assert.equal(feedbackValue(null, 1), 1);
  assert.equal(feedbackValue(-1, -1, false), -1);
  assert.equal(feedbackValue(-1, -1, true), null);
  assert.equal(feedbackValue(null, -1), -1);
  assert.equal(feedbackValue(1, -1), -1);
  assert.equal(feedbackValue(-1, 1), 1);
  assert.throws(() => feedbackValue(1, 0), TypeError);
  assert.throws(() => feedbackValue(-1, null), TypeError);
});

test('first-page refresh retains loaded older pages and updates overlapping artifacts', () => {
  const merged = mergeArtifacts([{id:'b', feedback:null}, {id:'c'}, {id:'d'}], [{id:'a'}, {id:'b', feedback:1}]);
  assert.deepEqual(merged.map((item) => item.id), ['a','b','c','d']);
  assert.equal(merged[1].feedback, 1);
});

test('load more appends unique old artifacts without replacing visible records', () => {
  assert.deepEqual(mergeArtifacts([{id:'a'}, {id:'b'}], [{id:'b'}, {id:'c'}], true).map((item) => item.id), ['a','b','c']);
});

test('uncertain retry preserves request id and exact payload; edits create a new operation', () => {
  const pending = new Map();
  const payload = {backend_id:'local', positive:' a\n', negative:' b ', seed:-1};
  const first = requestIdentity(payload, pending, () => 'first'); pending.set(first.key, first);
  assert.equal(requestIdentity({...payload}, pending, () => 'wrong').payload.request_id, 'first');
  assert.equal(first.payload.positive, ' a\n');
  const changed = requestIdentity({...payload, positive:'different'}, pending, () => 'second');
  assert.equal(changed.payload.request_id, 'second');
  assert.equal(changed.payload.positive, 'different');
  pending.delete(first.key);
  assert.equal(requestIdentity(payload, pending, () => 'third').payload.request_id, 'third');
});

test('new backend defaults to built-in workflow while legacy graphs remain custom', () => {
  assert.equal(configuredWorkflowMode(), 'default');
  assert.equal(configuredWorkflowMode({ workflow: {} }), 'default');
  assert.equal(configuredWorkflowMode({ workflow: {'6': {class_type:'CLIPTextEncode'}} }), 'custom');
});

test('explicit default mode wins over materialized workflow', () => {
  assert.equal(configuredWorkflowMode({workflow_mode:'default', workflow:{'6':{class_type:'CLIPTextEncode'}}}), 'default');
  assert.equal(configuredWorkflowMode({workflow_mode:'custom', workflow:{}}), 'custom');
});

test('empty custom JSON falls back to default without parsing or binding requirements', () => {
  assert.equal(effectiveWorkflowMode('custom', ''), 'default');
  assert.equal(effectiveWorkflowMode('custom', ' \n\t'), 'default');
  assert.equal(effectiveWorkflowMode('custom', '{"6":{}}'), 'custom');
  assert.equal(effectiveWorkflowMode('default', 'not JSON'), 'default');
});

test('liked grid leaves arrow navigation to its opened image viewer', () => {
  const liked = { ...context, view: 'liked' };
  for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']) {
    assert.equal(keyboardAction({ key }, liked), null);
  }
  assert.equal(keyboardAction({ key: ' ' }, liked), 'privacy');
  assert.equal(keyboardAction({ key: ' ', dialogOpen: true }, { ...liked, dialogOpen:true }), null);
});
