import test from 'node:test';
import assert from 'node:assert/strict';

test('system follows appearance changes; explicit themes stay fixed and the choice stays distinct', async () => {
  const media = new EventTarget();
  media.matches = true;
  const classes = new Set();
  const doc = new EventTarget();
  doc.documentElement = { classList: { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); } } };
  globalThis.window = { matchMedia: query => { assert.equal(query, '(prefers-color-scheme: dark)'); return media; } };
  globalThis.document = doc;
  let writes = 0;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/settings/general');
    if (options.method === 'PUT') writes++;
    return { ok: true, json: async () => ({ theme: options.method === 'PUT' ? JSON.parse(options.body).theme : 'system' }) };
  };
  const { currentTheme, applyTheme, saveTheme, loadTheme } = await import('../web/src/controllers/theme.mjs');
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), true);
  media.matches = false; media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), false);
  applyTheme('dark'); media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), true);
  applyTheme('light'); media.matches = true; media.dispatchEvent(new Event('change'));
  assert.equal(classes.has('dark'), false);
  await saveTheme('system');
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), true);
  media.matches = false; media.dispatchEvent(new Event('change'));
  assert.equal(currentTheme(), 'system');
  assert.equal(classes.has('dark'), false);
  assert.equal(writes, 1);
  await loadTheme();
  assert.equal(currentTheme(), 'system');
});
