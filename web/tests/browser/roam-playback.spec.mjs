import { test, expect } from './fixtures.mjs';

test('autoplay keeps advancing after navigation and immersion', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/roam', { data: { playback_interval_seconds: 2 } });
  await page.goto('/#feed');
  await page.locator('#empty-generate').click();
  const image = page.locator('#main-image');
  await expect.poll(() => image.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
  await page.locator('#roam-playback').click();
  for (let i = 0; i < 3; i++) {
    const source = await image.getAttribute('src');
    await expect(image).not.toHaveAttribute('src', source);
  }
  await page.locator('#roam-immersive').click();
  const source = await image.getAttribute('src');
  await expect(image).not.toHaveAttribute('src', source);
  await page.locator('#image-card').hover();
  await page.locator('#roam-immersive-playback').click();
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
});

for (const alreadyPlaying of [false, true]) test(`retained image stays ready after cleanup, already playing: ${alreadyPlaying}`, async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/roam', { data: { playback_interval_seconds: 2 } });
  await page.goto('/#generate');
  await page.locator('#positive').fill('garden, sunlight');
  await page.locator('#generate').click();
  await expect(page.locator('#compose .generated-card').first()).toBeVisible();
  const generated = await (await page.request.get('/api/artifacts?source=generate')).json();
  await page.locator('[data-view=feed]').click();
  await page.locator('#empty-generate').click();
  await expect.poll(() => page.locator('#main-image').evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
  const source = await page.locator('#main-image').getAttribute('src');
  if (alreadyPlaying) await page.locator('#roam-playback').click();
  const refreshed = page.waitForResponse(async response => response.url().includes('/api/artifacts?') && (await response.json()).revision > 0);
  expect((await page.request.delete(`/api/generated/${generated.artifacts[0].id}`, { data: {} })).ok()).toBe(true);
  await refreshed;
  if (!alreadyPlaying) await page.locator('#roam-playback').click();
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => page.locator('#roam-playback .playback-progress-value').evaluate(el => getComputedStyle(el).animationName), { timeout: 1500 }).toBe('playback-progress');
  await expect(page.locator('#main-image')).not.toHaveAttribute('src', source);
  await page.screenshot({ path: test.info().outputPath('autoplay-after-cleanup.png') });
});
