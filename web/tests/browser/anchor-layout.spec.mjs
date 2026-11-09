import { test, expect } from './fixtures.mjs';

async function prepare(page, context, width, immersive) {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'en', theme: immersive ? 'dark' : 'light' } });
  const backend = (await (await page.request.get('/api/bootstrap')).json()).backends[0];
  backend.workflow['4'] = { class_type: 'EmptyLatentImage', inputs: { width: 832, height: 1216 } };
  for (const dimension of ['width', 'height']) backend.bindings[dimension] = { node_id: '4', input: dimension };
  await page.request.put('/api/backends/fixture', { data: backend });
  await page.route('**/api/artifacts/*/image', route => route.fulfill({ contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="832" height="1216"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#adb8af"/><stop offset="1" stop-color="#626c87"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>' }));
  const tags = ['illustration', 'Garden', 'blue sky', 'sunlight', 'quiet evening light', 'trees', 'flowers', 'clouds',
    'landscape', 'soft shadows', 'green leaves', 'distant mountains', 'stone path', 'warm colors', 'mist', 'water'];
  await page.request.post('/api/jobs', { data: { request_id: 'anchor-layout', backend_id: 'fixture', positive: tags.join(', '), negative: '', seed: 1 } });
  await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).total).toBe(1);
  const image = (await (await page.request.get('/api/artifacts')).json()).artifacts[0];
  await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
  await page.request.post('/api/roam/start', { data: { artifact_id: image.id } });
  await page.request.put('/api/settings/roam', { data: { pinned_positive: [], excluded_positive: [] } });
  await page.goto('/#feed');
  await expect(page.locator('#main-image')).toHaveAttribute('src', `/api/artifacts/${image.id}/image`);
  if (immersive) {
    await page.locator('#roam-immersive').click();
    await expect(page.locator('#image-card')).toHaveClass(/immersive/);
  }
  await page.locator('.roam-anchor-trigger').click();
  const panel = page.locator('.roam-anchors:visible');
  await expect(panel).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  return panel;
}

async function positions(panel) {
  return panel.locator('.roam-anchor-terms').evaluate(container => {
    const parent = container.getBoundingClientRect();
    return { scroll: container.scrollTop, tags: [...container.querySelectorAll('.roam-anchor-term')].map(node => {
      const box = node.getBoundingClientRect();
      return { text: node.textContent, x: box.x - parent.x, y: box.y - parent.y, width: box.width, height: box.height };
    }) };
  });
}

function stable(before, after) {
  expect(after.tags.map(tag => tag.text)).toEqual(before.tags.map(tag => tag.text));
  expect(after.scroll).toBe(before.scroll);
  for (let index = 0; index < before.tags.length; index++) for (const field of ['x', 'y', 'width', 'height']) {
    expect(Math.abs(after.tags[index][field] - before.tags[index][field]), `${before.tags[index].text}: ${field}`).toBeLessThan(.5);
  }
}

for (const width of [1365, 390]) for (const immersive of [false, true]) {
  test(`anchor chips retain geometry through pin, pending and exclusion at ${width}px immersive=${immersive}`, async ({ page, context }, testInfo) => {
    const panel = await prepare(page, context, width, immersive);
    const term = text => panel.locator('.roam-anchor-term').filter({ hasText: new RegExp(`^${text}$`, 'i') });
    const garden = term('garden');
    const unpinnedColor = await garden.evaluate(node => getComputedStyle(node).backgroundColor);
    const before = await positions(panel);
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/settings/roam', async route => {
      if (route.request().method() === 'PUT') await gate;
      await route.continue();
    });
    await garden.click();
    await expect(garden).toHaveAttribute('data-pending', 'true');
    stable(before, await positions(panel));
    release();
    await expect(garden).toHaveAttribute('aria-pressed', 'true');
    await expect(garden).toBeEnabled();
    stable(before, await positions(panel));
    expect(await garden.evaluate(node => getComputedStyle(node).backgroundColor)).not.toBe(unpinnedColor);
    await page.screenshot({ path: testInfo.outputPath('compact-pinned-anchors.png'), animations: 'disabled' });
    await term('sunlight').click({ button: 'right' });
    await expect(term('sunlight')).toHaveAttribute('data-excluded', 'true');
    await expect(garden).toBeEnabled();
    stable(before, await positions(panel));
    await term('sunlight').click({ button: 'right' });
    await expect(term('sunlight')).toHaveAttribute('data-excluded', 'false');
    await expect(garden).toBeEnabled();
    stable(before, await positions(panel));
    await garden.focus();
    await page.keyboard.press('Space');
    await expect(garden).toHaveAttribute('aria-pressed', 'false');
    await expect(garden).toBeEnabled();
    stable(before, await positions(panel));
    const select = await panel.locator('#roam-canvas-size').boundingBox();
    const pin = await panel.getByRole('button', { name: 'Pin current', exact: true }).boundingBox();
    expect(Math.abs(select.y + select.height / 2 - pin.y - pin.height / 2)).toBeLessThan(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 390 && !immersive) expect((await panel.boundingBox()).height).toBeLessThanOrEqual(176);
    await page.screenshot({ path: testInfo.outputPath('compact-stable-anchors.png'), animations: 'disabled' });
  });
}
