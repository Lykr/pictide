import test from 'node:test';
import assert from 'node:assert/strict';
import { applyLanguage, language, locale, resolveLanguage, subscribe, t, tr } from '../../src/i18n/index.mjs';

test('system resolves supported Simplified Chinese and falls back to English', () => {
  for (const value of ['zh', 'zh-CN', 'zh-SG', 'zh-Hans', 'zh-Hans-CN']) assert.equal(resolveLanguage(value), 'zh-CN');
  for (const value of ['en-US', 'fr-FR', 'ja-JP', 'zh-TW', 'zh-Hant', 'zh-HK', '']) assert.equal(resolveLanguage(value), 'en');
  applyLanguage('system'); assert.equal(language(), 'system');
  assert.equal(locale(), resolveLanguage(globalThis.navigator?.language));
});

test('switching translations interpolates values and notifies without changing user text', () => {
  let notifications = 0;
  const unsubscribe = subscribe(() => notifications++);
  applyLanguage('en');
  assert.equal(t('漫游'), 'Roam');
  assert.equal(tr`已取消 ${3} 个`, 'Cancelled 3');
  assert.equal(t('custom user prompt, 黑色头发'), 'custom user prompt, 黑色头发');
  applyLanguage('zh-CN');
  assert.equal(t('漫游'), '漫游');
  assert.equal(tr`已取消 ${3} 个`, '已取消 3 个');
  assert.equal(notifications, 2);
  unsubscribe();
});
