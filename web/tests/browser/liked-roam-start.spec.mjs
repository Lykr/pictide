import { test, expect } from './fixtures.mjs';

async function prepare(page, context, style = 'single', mode = 'along') {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN' } });
  await page.request.put('/api/settings/roam', { data: { playback_style: style, prompt_mode: mode } });
  await page.request.post('/api/jobs', { data: { request_id: 'liked-origin', backend_id: 'fixture', positive: 'garden', negative: '', seed: 17 } });
  await expect.poll(async () => (await (await page.request.get('/api/artifacts?source=generate')).json()).total).toBe(1);
  const image = (await (await page.request.get('/api/artifacts?source=generate')).json()).artifacts[0];
  await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
  // An old, newer Roam picture must not remain the scroll's pivot after the jump.
  await page.request.post('/api/roam/ensure', { data: { demand: true } });
  await expect.poll(async () => (await (await page.request.get('/api/artifacts?source=roam')).json()).total).toBe(1);
  const previous = (await (await page.request.get('/api/artifacts?source=roam')).json()).artifacts[0];
  await page.request.put('/api/roam/view', { data: { artifact_id: previous.id, viewed_at: Date.now() } });
  expect((await page.request.put('/api/settings/roam', { data: {
    pinned_positive: ['old subject'], excluded_positive: ['old exclusion'],
  } })).ok()).toBe(true);
  await page.goto('/#feed');
  await expect(page.locator('#roam-playback')).toBeEnabled();
  await page.locator('[data-view=liked]').click();
  await page.locator('#liked-view .generated-image-button').click();
  return { image, previous, viewer: page.locator('.generated-viewer') };
}

for (const style of ['single', 'scroll']) for (const width of [1365, 390]) {
  test(`start from liked original in ${style} at ${width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    if (width === 390) await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { get: () => true }));
    const { image, previous, viewer } = await prepare(page, context, style);
    const start = viewer.getByRole('button', { name: '从此漫游', exact: true });
    await expect.poll(() => start.evaluate(node => node.getBoundingClientRect().width)).toBeGreaterThanOrEqual(width < 640 ? 43.9 : 31.9);
    const startBounds = await start.boundingBox();
    const immersiveBounds = await viewer.getByRole('button', { name: '沉浸模式', exact: true }).boundingBox();
    expect(startBounds.x + startBounds.width).toBeLessThanOrEqual(immersiveBounds.x);
    await page.screenshot({ path: testInfo.outputPath('liked-roam-button.png') });
    await start.click();
    await expect(viewer).toHaveCount(0);
    await expect(page).toHaveURL(/#feed$/);
    const assertSelected = async () => {
      if (style === 'scroll') {
        const scroll = page.getByTestId('roam-scroll');
        await expect(scroll).toHaveAttribute('data-focus', image.id);
        const selected = scroll.locator(`[data-artifact-id="${image.id}"]`);
        await expect(selected).toBeVisible();
        const bounds = await selected.boundingBox(), viewport = await scroll.boundingBox();
        expect(bounds.x).toBeLessThan(viewport.x + viewport.width / 2);
        expect(bounds.x + bounds.width).toBeGreaterThan(viewport.x + viewport.width / 2);
        await expect(scroll.locator(`[data-artifact-id="${previous.id}"]`)).toHaveCount(0);
      } else await expect(page.locator('#image-card .roam-single-image img').first()).toHaveAttribute('src', `/api/artifacts/${image.id}/image`);
      await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
    };
    await assertSelected();
    expect((await (await page.request.get('/api/roam/view')).json()).artifact_id).toBe(image.id);
    const settings = await (await page.request.get('/api/settings/roam')).json();
    expect(settings.prompt_mode).toBe('along'); expect(settings.playback_style).toBe(style); expect(settings.prefetch_count).toBe(0);
    expect(settings.pinned_positive).toEqual([]); expect(settings.excluded_positive).toEqual([]); expect(settings.pinned_canvas).toBeNull();
    const anchor = page.locator('#image-card').getByRole('button', { name: '锚点', exact: true });
    await expect(anchor.locator('.roam-anchor-count')).toHaveCount(0);
    await anchor.click();
    await expect(page.getByRole('button', { name: /old subject|old exclusion/ })).toHaveCount(0);
    await anchor.click();
    const original = (await (await page.request.get('/api/artifacts?source=generate&liked=1')).json()).artifacts[0];
    expect(original.id).toBe(image.id); expect(original.source).toBe('generate'); expect(original.feedback).toBe(1);
    await page.reload();
    await assertSelected();
    // The next explicit navigation resumes generation using this image's tags.
    await page.locator('#next').click();
    await expect.poll(async () => (await (await page.request.get('/api/artifacts?source=roam')).json()).total).toBe(2);
    await expect.poll(async () => (await (await page.request.get('/api/roam/view')).json()).artifact_id).not.toBe(image.id);
    await page.locator('[data-view=generate]').click();
    await page.locator('#compose .generated-image-button').click();
    await expect(page.locator('.generated-viewer').getByRole('button', { name: '从此漫游', exact: true })).toHaveCount(0);
  });
}

test('failed start keeps the viewer and a pending start cannot be submitted twice', async ({ page, context }) => {
  const { image, viewer } = await prepare(page, context);
  let calls = 0, release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/roam/start', async route => {
    calls++; await gate;
    await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'Fixture start failed' }) });
  });
  const start = viewer.getByRole('button', { name: '从此漫游', exact: true });
  await start.click();
  await expect(start).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeVisible();
  release();
  await expect(start).toBeEnabled();
  expect(calls).toBe(1);
  await expect(page).toHaveURL(/#liked$/);
  await expect(viewer.locator('.generated-viewer-stage img')).toHaveAttribute('src', `/api/artifacts/${image.id}/image`);
  await expect(page.locator('.notification-card').filter({ hasText: 'Fixture start failed' })).toBeVisible();
  const unchanged = await (await page.request.get('/api/settings/roam')).json();
  expect(unchanged.pinned_positive).toEqual(['old subject']); expect(unchanged.excluded_positive).toEqual(['old exclusion']);
  await page.unroute('**/api/roam/start');
  await start.click();
  await expect(page).toHaveURL(/#feed$/);
});

test('hidden liked Roam image can be restored as the origin with an English label', async ({ page, context }) => {
  const { previous, viewer } = await prepare(page, context);
  await viewer.getByRole('button', { name: '关闭图片', exact: true }).click();
  await page.request.put(`/api/artifacts/${previous.id}/feedback`, { data: { value: 1 } });
  const generated = (await (await page.request.get('/api/artifacts?source=generate')).json()).artifacts[0];
  await page.request.post('/api/roam/start', { data: { artifact_id: generated.id } });
  await page.request.put('/api/settings/general', { data: { language: 'en' } });
  await page.reload();
  await page.locator(`#liked-view .generated-image-button`).filter({ has: page.locator(`img[src*="${previous.id}"]`) }).click();
  await page.locator('.generated-viewer').getByRole('button', { name: 'Roam from here', exact: true }).click();
  await expect(page).toHaveURL(/#feed$/);
  expect((await (await page.request.get('/api/roam/view')).json()).artifact_id).toBe(previous.id);
});
