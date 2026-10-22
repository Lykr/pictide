import test from 'node:test';
import assert from 'node:assert/strict';
import { API_KEY_MASK, apiKeyFields, customWorkflowName } from '../../src/controllers/settings-controls.mjs';
import { applyLanguage, language } from '../../src/i18n/index.mjs';

test('untouched saved API key mask never becomes a submitted credential', () => {
  assert.deepEqual(apiKeyFields(API_KEY_MASK, true), {});
  assert.equal(JSON.stringify(apiKeyFields(API_KEY_MASK, true)).includes(API_KEY_MASK), false);
  assert.throws(() => apiKeyFields(API_KEY_MASK.slice(1), true));
  assert.throws(() => apiKeyFields(API_KEY_MASK + 'replacement', true));
  assert.throws(() => apiKeyFields(API_KEY_MASK, false));
});
test('clearing the password field explicitly removes a saved key, while replacement submits only new text', () => {
  assert.deepEqual(apiKeyFields('', true), {api_key: ''});
  assert.deepEqual(apiKeyFields('', false), {api_key: ''});
  assert.deepEqual(apiKeyFields('new-test-key', true), {api_key: 'new-test-key'});
  assert.deepEqual(apiKeyFields('new-test-key', false), {api_key: 'new-test-key'});
});
test('custom workflow defaults avoid existing names without changing existing workflow identity', () => {
  const previous = language();
  try {
    applyLanguage('zh-CN');
    assert.equal(customWorkflowName([]), '自定义工作流');
    assert.equal(customWorkflowName(['自定义工作流', '自定义工作流 2']), '自定义工作流 3');
    assert.equal(customWorkflowName([' 自定义工作流 ', '自定义工作流 ２']), '自定义工作流 3');
    applyLanguage('en');
    assert.equal(customWorkflowName([]), 'Custom workflow');
    assert.equal(customWorkflowName(['Custom workflow', 'custom workflow 2']), 'Custom workflow 3');
  } finally {
    applyLanguage(previous);
  }
});
