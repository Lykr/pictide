import { test, expect } from './fixtures.mjs';

async function prepare(page, context, count = 4) {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/roam', { data: { playback_style: 'scroll', scroll_speed: 'fast' } });
  let anchor = null;
  for (let i = 0; i < count; i++) {
    expect((await page.request.post('/api/roam/ensure', { data: { anchor_id: anchor, demand: true } })).ok()).toBe(true);
    await expect.poll(async () => (await (await page.request.get('/api/artifacts?source=roam')).json()).artifacts.length).toBeGreaterThan(i);
    anchor = (await (await page.request.get('/api/artifacts?source=roam')).json()).artifacts[0].id;
    await page.request.put('/api/roam/view', { data: { artifact_id: anchor, viewed_at: Date.now() + i } });
  }
  const items = (await (await page.request.get('/api/artifacts?source=roam')).json()).artifacts.reverse();
  await page.request.put('/api/roam/view', { data: { artifact_id: items[0].id, viewed_at: Date.now() + count + 100 } });
  await page.goto('/#feed');
  const scroll = page.getByTestId('roam-scroll');
  await expect(scroll).toBeVisible();
  await expect(page.locator('#roam-playback')).toBeEnabled();
  await expect.poll(() => scroll.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
  return { scroll, items };
}

for (const width of [1365, 390]) test(`scroll arrows, like pause and smooth continuation at ${width}px`, async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  const { scroll, items } = await prepare(page, context);
  const offset = () => scroll.evaluate(el => Number(el.dataset.offset));
  await page.locator('#roam-playback').click();
  const playingStart = await offset();
  await expect.poll(offset).toBeLessThan(playingStart - 8);
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-moving', 'true');
  await expect(scroll).toHaveAttribute('data-focus', items[1].id);
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await page.locator('#like').click();
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
  const likedId = await scroll.getAttribute('data-focus');
  const photo = scroll.locator(`[data-artifact-id="${likedId}"]`);
  await expect(photo).toHaveAttribute('data-liked', 'true');
  await expect(photo.locator('[data-liked-marker]')).toBeVisible();
  const paused = await offset();
  await page.waitForTimeout(120);
  expect(await offset()).toBeCloseTo(paused, 1);
  await page.screenshot({ path: testInfo.outputPath(`scroll-liked-${width}.png`) });
  // Capture the synchronous result of click: the transform must still equal its paused value.
  const beforeNext = await scroll.evaluate(el => {
    const before = Number(el.dataset.offset);
    document.querySelector('#next').click();
    return { before, after: Number(el.dataset.offset) };
  });
  expect(beforeNext.after).toBeCloseTo(beforeNext.before, 1);
  await expect(scroll).toHaveAttribute('data-moving', 'true');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await page.locator('#roam-playback').click();
  await page.keyboard.press('ArrowLeft');
  await expect(scroll).toHaveAttribute('data-focus', items[1].id);
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
  await page.locator('#roam-immersive').click();
  await expect(page.locator('#image-card')).toHaveClass(/immersive/);
  await expect(photo.locator('[data-liked-marker]')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`scroll-immersive-${width}.png`) });
});

test('scroll waits for new images, preserves settings and switches back to single-image playback', async ({ page, context }) => {
  const { scroll, items } = await prepare(page, context, 1);
  await page.locator('#roam-playback').click();
  await expect.poll(async () => (await (await page.request.get('/api/artifacts?source=roam')).json()).artifacts.length).toBeGreaterThan(1);
  await expect(scroll.locator('img')).toHaveCount(2);
  await expect.poll(() => scroll.evaluate(el => Number(el.dataset.offset))).toBeLessThan(-1);
  await page.locator('[data-view=settings]').click();
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
  await page.locator('[data-settings-section=roam]').click();
  await page.locator('#roam-form').getByRole('radio', { name: 'Slow', exact: true }).click();
  await page.locator('#roam-save').click();
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).scroll_speed).toBe('slow');
  await page.reload();
  await page.locator('[data-view=feed]').click();
  await page.locator('#roam-options').click();
  const panel = page.locator('.roam-options-panel');
  await expect(panel.getByRole('radio', { name: 'Scroll', exact: true })).toHaveAttribute('data-state', 'on');
  await expect(panel.getByRole('radio', { name: 'Slow', exact: true })).toHaveAttribute('data-state', 'on');
  await panel.getByRole('radio', { name: 'Single', exact: true }).click();
  await expect(page.locator('#main-image')).toHaveAttribute('src', /\/api\/artifacts\/.+\/image/);
  await expect(page.locator('#roam-playback')).toBeEnabled();
  expect(items).toHaveLength(1);
});

test('rapid navigation and feedback during motion target the visible center, including wide images', async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.route(/\/api\/artifacts\/[^/]+\/image$/, async route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="600"><rect width="1600" height="600" fill="#60766a"/></svg>',
  }));
  const { scroll, items } = await prepare(page, context, 4);
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await page.locator('#roam-playback').click();
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-moving', 'true');
  const feedback = page.waitForRequest(request => request.method() === 'PUT' && request.url().endsWith('/feedback'));
  const focused = await scroll.evaluate(element => {
    const center = element.getBoundingClientRect().x + element.clientWidth / 2;
    const photo = [...element.querySelectorAll('[data-artifact-id]')].find(item => {
      const rect = item.getBoundingClientRect(); return rect.left <= center && rect.right >= center;
    });
    document.querySelector('#like').click();
    return photo.dataset.artifactId;
  });
  expect((await feedback).url()).toContain(`/api/artifacts/${focused}/feedback`);
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  const marker = scroll.locator(`[data-artifact-id="${focused}"] [data-liked-marker]`);
  await expect(marker).toBeVisible();
  const box = await marker.boundingBox(), stage = await scroll.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(stage.x);
  expect(box.x + box.width).toBeLessThanOrEqual(stage.x + stage.width);
  await page.screenshot({ path: testInfo.outputPath('scroll-wide-liked.png') });
});

test('scroll restores a middle picture and retains focus across hidden page measurements', async ({ page, context }) => {
  const { scroll, items } = await prepare(page, context, 5);
  await page.request.put('/api/roam/view', { data: { artifact_id: items[2].id, viewed_at: Date.now() + 500 } });
  await page.reload();
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await page.locator('[data-view=liked]').click();
  await page.locator('[data-view=feed]').click();
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
});
