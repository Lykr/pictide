import test from 'node:test';
import assert from 'node:assert/strict';
import { createButtonFeedback } from '../../src/controllers/button-feedback.mjs';

function setup(iconOnly = false) {
  const attrs = new Map(iconOnly ? [['aria-label', '刷新配置'], ['data-tooltip', '刷新配置']] : []);
  const original = [{ nodeName: 'svg', name: 'original icon' }, ...(iconOnly ? [] : [{ nodeName: '#text', textContent: '生成图片' }])];
  const button = {
    id: iconOnly ? 'refresh' : 'generate', childNodes: [...original], textContent: iconOnly ? '' : '生成图片', disabled: true,
    dataset: {}, ownerDocument: { createElement: () => ({ setAttribute() {} }) },
    getAttribute: name => attrs.get(name) ?? null,
    setAttribute: (name, value) => attrs.set(name, value), removeAttribute: name => attrs.delete(name),
    replaceChildren(...nodes) { this.childNodes = nodes; }, append(node) { this.childNodes.push(node); },
  };
  const notices = [];
  const feedback = createButtonFeedback(button, name => ({ name, classList: { add() {} } }), {
    announce: (message, options) => notices.push({ message, ...options }),
  });
  return { button, feedback, notices, attrs, original };
}

test('pending feedback preserves the button caption and disabled state', () => {
  const { button, feedback, attrs, original, notices } = setup();
  feedback.show('pending', '正在提交…');
  assert.equal(button.childNodes[0].name, 'LoaderCircle');
  assert.equal(button.childNodes[1], original[1]);
  assert.equal(attrs.get('aria-busy'), 'true');
  assert.equal(button.disabled, true);
  assert.deepEqual(notices, []);
});

test('operation results restore the button and send their details to the floating notice', () => {
  const { button, feedback, notices, attrs, original } = setup();
  feedback.show('pending', '正在提交…');
  feedback.show('success', '已提交', '任务已接收，尚未完成');
  assert.deepEqual(button.childNodes, original);
  assert.equal(attrs.has('aria-label'), false);
  assert.equal(attrs.has('aria-busy'), false);
  assert.equal(button.disabled, true);
  assert.deepEqual(notices, [{ message: '任务已接收，尚未完成', kind: 'success', id: 'button-generate' }]);
  feedback.show('warning', '结果待确认 · 重试', '再次点击复用请求 ID');
  assert.deepEqual(button.childNodes, original);
  assert.equal(notices.at(-1).message, '再次点击复用请求 ID');
  assert.equal(notices.at(-1).kind, 'warning');
});

test('icon actions restore their original accessible names after a failure', () => {
  const { button, feedback, notices, attrs, original } = setup(true);
  feedback.show('pending', '正在刷新…');
  feedback.show('error', '刷新失败', '刷新失败：连接断开');
  assert.deepEqual(button.childNodes, original);
  assert.equal(attrs.get('aria-label'), '刷新配置');
  assert.equal(attrs.get('data-tooltip'), '刷新配置');
  assert.equal(attrs.has('aria-busy'), false);
  assert.deepEqual(notices, [{ message: '刷新失败：连接断开', kind: 'error', id: 'button-refresh' }]);
});
