import test from 'node:test';
import assert from 'node:assert/strict';
import { createButtonFeedback } from '../web/src/controllers/button-feedback.mjs';

function setup(iconOnly = false) {
  const attrs = new Map(iconOnly ? [['aria-label', '刷新配置'], ['data-tooltip', '刷新配置']] : []);
  const button = {
    childNodes: ['original icon', ...(iconOnly ? [] : ['生成图片'])], textContent: iconOnly ? '' : '生成图片', disabled: true,
    dataset: {}, ownerDocument: {
      createTextNode: text => ({ text }), createElement: () => ({ setAttribute() {} }),
    },
    getAttribute: name => attrs.get(name) ?? null,
    setAttribute: (name, value) => attrs.set(name, value), removeAttribute: name => attrs.delete(name),
    replaceChildren(...nodes) { this.childNodes = nodes; }, append(node) { this.childNodes.push(node); },
  };
  const callbacks = [];
  const feedback = createButtonFeedback(button, name => ({ name, classList: { add() {} } }), {
    schedule: callback => { callbacks.push(callback); return callbacks.length; }, cancel() {},
  });
  return { button, feedback, callbacks, attrs };
}

test('button feedback restores original content and attributes without enabling a disabled action', () => {
  const { button, feedback, callbacks, attrs } = setup();
  feedback.show('pending', '正在提交…');
  assert.equal(button.childNodes[0].name, 'LoaderCircle');
  assert.equal(attrs.get('aria-busy'), 'true');
  feedback.show('success', '已提交', '任务已接收，尚未完成');
  assert.equal(button.childNodes[0].name, 'Check');
  assert.equal(button.dataset.tooltip, '任务已接收，尚未完成');
  assert.equal(button.childNodes.at(-1).textContent, '任务已接收，尚未完成');
  callbacks[0]();
  assert.deepEqual(button.childNodes, ['original icon', '生成图片']);
  assert.equal(attrs.has('aria-label'), false);
  assert.equal(attrs.has('aria-busy'), false);
  assert.equal(button.disabled, true);
});

test('an earlier success timer cannot erase a later pending or uncertain submission', () => {
  const { button, feedback, callbacks } = setup();
  feedback.show('success', '已提交');
  feedback.show('pending', '正在提交…');
  callbacks[0](); assert.equal(button.dataset.feedback, 'pending');
  feedback.show('warning', '结果待确认 · 重试', '再次点击复用请求 ID');
  callbacks[0]();
  assert.equal(button.dataset.feedback, 'warning');
  assert.equal(button.dataset.tooltip, '再次点击复用请求 ID');
  assert.equal(callbacks.length, 1);
});

test('icon actions retain their size and provide persistent failure details and accessible names', () => {
  const { button, feedback, callbacks, attrs } = setup(true);
  feedback.show('error', '刷新失败', '刷新失败：连接断开');
  assert.equal(button.childNodes.length, 2); // icon + hidden announcement, no visible caption
  assert.equal(attrs.get('aria-label'), '刷新配置：刷新失败：连接断开');
  assert.equal(callbacks.length, 0);
  feedback.reset();
  assert.equal(attrs.get('aria-label'), '刷新配置');
  assert.equal(attrs.get('data-tooltip'), '刷新配置');
  assert.deepEqual(button.childNodes, ['original icon']);
});
