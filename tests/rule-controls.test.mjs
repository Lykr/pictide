import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { ruleVisibility, counterAfter, nextRuleCounters, submissionDecision, afterPromptEdit } from '../web/src/controllers/rule-controls.mjs';
import { requestIdentity } from '../web/src/controllers/feed-controls.mjs';

test('manual input retains validation; automatic rules can start with empty text', () => {
  assert.deepEqual(ruleVisibility('manual', 'sequence', true), { rules:false, seed:false, sequence:false, positiveRequired:true });
  assert.deepEqual(ruleVisibility('rules', 'random_each_run', true), { rules:true, seed:false, sequence:false, positiveRequired:false });
  assert.equal(ruleVisibility('rules', 'fixed_seed', true).seed, true);
  assert.equal(ruleVisibility('rules', 'fixed_seed', true).sequence, false);
  assert.equal(ruleVisibility('rules', 'sequence', true).sequence, true);
  assert.equal(ruleVisibility('rules', 'sequence', false).positiveRequired, true);
});

test('counter controls honor boundaries and keep integers', () => {
  assert.equal(counterAfter(5, 'fixed', 10), 5);
  assert.equal(counterAfter(5, 'increment', 10), 6);
  assert.equal(counterAfter(10, 'increment', 10), 10);
  assert.equal(counterAfter(0, 'decrement', 10), 0);
  assert.equal(counterAfter(5, 'decrement', 10), 4);
  assert.equal(counterAfter(5, 'randomize', 10, () => .5), 5);
  assert.equal(counterAfter(5, 'randomize', 10, () => 1), 10);
});

test('seed and frame post-generation controls apply only to their modes', () => {
  const controls = { seed:7, step:3, seedControl:'increment', stepControl:'increment' };
  assert.deepEqual(nextRuleCounters({...controls, mode:'random_each_run'}, {seed:900}), {seed:7, step:3});
  assert.deepEqual(nextRuleCounters({...controls, mode:'fixed_seed'}, {seed:7}), {seed:8, step:3});
  assert.deepEqual(nextRuleCounters({...controls, mode:'sequence'}, {seed:7}), {seed:8, step:4});
  assert.deepEqual(nextRuleCounters({...controls, mode:'sequence', seedControl:'fixed'}, {seed:7}), {seed:7, step:4});
});

test('sequence keeps its original seed after nonzero frames use derived frame seeds', () => {
  const controls = {mode:'sequence', seed:7, step:3, seedControl:'fixed', stepControl:'increment'};
  assert.deepEqual(nextRuleCounters(controls, {seed:987654, sequence:{seed:7, step:3}}), {seed:7, step:4});
  assert.deepEqual(nextRuleCounters(controls, {seed:987654, sequence:{step:3}}), {seed:7, step:4});
  assert.deepEqual(nextRuleCounters({...controls, seedControl:'increment'}, {seed:987654, sequence:{seed:7, step:3}}), {seed:8, step:4});
});

test('uncertain automatic submission reuses its exact prompt and id before any new draw', () => {
  const pending = new Map();
  const payload = { backend_id:'local', positive:' a\n', negative:' b ', seed:-1 };
  const operation = requestIdentity(payload, pending, () => 'stable-id'); pending.set(operation.key, operation);
  const retry = submissionDecision({...payload}, pending, true);
  assert.equal(retry.generatePrompts, false);
  assert.equal(retry.retry, operation);
  assert.equal(retry.retry.payload.request_id, 'stable-id');
  assert.equal(retry.retry.payload.positive, ' a\n');
  assert.equal(submissionDecision({...payload, positive:'edited'}, pending, true).generatePrompts, true);
  pending.delete(operation.key);
  assert.deepEqual(submissionDecision(payload, pending, true), {retry:null, generatePrompts:true});
  assert.deepEqual(submissionDecision(payload, pending, false), {retry:null, generatePrompts:false});
});

test('editing generated text disables automatic redraw without affecting manual mode', () => {
  assert.equal(afterPromptEdit('rules', true), false);
  assert.equal(afterPromptEdit('rules', false), false);
  assert.equal(afterPromptEdit('manual', true), true);
});
