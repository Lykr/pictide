import test from 'node:test';
import assert from 'node:assert/strict';

test('system follows appearance changes; explicit themes stay fixed and the choice stays distinct', async () => {
  const media = new EventTarget();
  media.matches = true;
  const classes = new Set();
  const doc = new EventTarget();
  doc.documentElement = { classList: { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); } } };
  globalThis.window = { matchMedia: query => query === '(prefers-reduced-motion: reduce)' ? Object.assign(new EventTarget(), { matches: false }) : media };
  globalThis.document = doc;
  let chromeColor;
  doc.querySelector = query => { assert.equal(query, 'meta[name="theme-color"]'); return { setAttribute(name, color) { assert.equal(name, 'content'); chromeColor = color; } }; };
  let writes = 0;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/settings/general');
    if (options.method === 'PUT') writes++;
    return { ok: true, json: async () => ({ theme: options.method === 'PUT' ? JSON.parse(options.body).theme : 'system' }) };
  };
  const { currentTheme, applyTheme, saveTheme, loadTheme } = await import('../web/src/controllers/theme.mjs');
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), true);
  assert.equal(chromeColor, '#0a0a0a');
  media.matches = false; media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), false);
  assert.equal(chromeColor, '#ffffff');
  applyTheme('dark'); media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), true);
  assert.equal(chromeColor, '#0a0a0a');
  applyTheme('light'); media.matches = true; media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), false);
  assert.equal(chromeColor, '#ffffff');
  await saveTheme('system');
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), true);
  assert.equal(chromeColor, '#0a0a0a');
  media.matches = false; media.dispatchEvent(new Event('change'));
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), false);
  assert.equal(chromeColor, '#ffffff');
  assert.equal(writes, 1);
  await loadTheme();
  assert.equal(currentTheme(), 'system');
});


test('an old settings read cannot undo a newly saved language', async () => {
  const { applyLanguage, locale } = await import('../web/src/i18n/index.mjs');
  const { loadTheme, saveLanguage } = await import('../web/src/controllers/theme.mjs');
  applyLanguage('en');
  let completeOldRead;
  globalThis.fetch = (url, options) => options.method === 'PUT'
    ? Promise.resolve({ ok: true, json: async () => ({ theme: 'system', language: 'zh-CN' }) })
    : new Promise(resolve => { completeOldRead = resolve; });
  const oldRead = loadTheme();
  await saveLanguage('zh-CN');
  completeOldRead({ ok: true, json: async () => ({ theme: 'system', language: 'en' }) });
  await oldRead;
  assert.equal(locale(), 'zh-CN');
});

test('an old settings read cannot re-enable a newly disabled image transition preference', async () => {
  const { loadTheme, saveImageTransitions } = await import('../web/src/controllers/theme.mjs');
  const { imageTransitionsEnabled, applyImageTransitions } = await import('../web/src/controllers/image-transitions.mjs');
  applyImageTransitions(true);
  let completeOldRead;
  globalThis.fetch = (url, options) => options.method === 'PUT'
    ? Promise.resolve({ ok: true, json: async () => ({ theme: 'system', language: 'en', image_transitions: false }) })
    : new Promise(resolve => { completeOldRead = resolve; });
  const oldRead = loadTheme();
  await saveImageTransitions(false);
  completeOldRead({ ok: true, json: async () => ({ theme: 'system', language: 'en', image_transitions: true }) });
  await oldRead;
  assert.equal(imageTransitionsEnabled(), false);
});
