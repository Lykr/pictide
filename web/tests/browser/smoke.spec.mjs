import { test, expect } from './fixtures.mjs';

const dismissTour = context => context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
const notice = page => page.locator('.notification-card[data-state="open"]').first();

test('connection results stay in the top corner without moving the settings form', async ({ page, context }) => {
  await dismissTour(context);
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
  await page.evaluate(() => document.fonts.ready);
  let ok = true;
  await page.route('**/api/backends/*/check', route => route.fulfill({ json: { ok, message: ok ? 'Connection successful' : 'Connection failed' } }));
  await page.locator('#test-backend').scrollIntoViewIfNeeded();
  const before = await page.locator('#settings-form').boundingBox();
  await page.locator('#test-backend').click();
  await expect(notice(page)).toContainText('Connection successful');
  await expect.poll(() => page.locator('#settings-form').boundingBox()).toEqual(before);
  const position = await notice(page).boundingBox();
  expect(position.y).toBeLessThanOrEqual(32);
  expect(position.x).toBeGreaterThan(900);
  await notice(page).getByRole('button', { name: 'Dismiss notification', exact: true }).click();
  ok = false;
  await page.locator('#test-backend').click();
  await expect(notice(page)).toContainText('Connection failed');
  await expect.poll(() => page.locator('#settings-form').boundingBox()).toEqual(before);
  await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
});

test('modal failures remain accessible and retry the same failed operation', async ({ page, context }) => {
  await dismissTour(context);
  let reads = 0;
  await page.route('**/api/recommendation/preferences?*', route => {
    reads++;
    return route.fulfill({ status: 503, json: { error: 'Preference fixture unavailable' } });
  });
  await page.goto('/#settings/roam');
  await page.getByRole('button', { name: 'View preferences', exact: true }).click();
  await expect(notice(page)).toContainText('Preference fixture unavailable');
  await expect.poll(() => page.locator('.notification-layer').evaluate(element => !!element.closest('[role="dialog"]'))).toBe(true);
  await notice(page).getByRole('button', { name: 'Retry', exact: true }).click();
  await expect.poll(() => reads).toBe(2);
  await expect(notice(page)).toContainText('Preference fixture unavailable');
  await notice(page).getByRole('button', { name: 'Dismiss notification', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toBeVisible();
});

test('mobile tour requires a saved anchor edit before generating the next image', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#feed');
  const guide = step => page.locator(`.guide-card[data-guide-step="${step}"]`);
  await page.getByRole('button', { name: 'Show me around', exact: true }).click();
  await expect(guide('roam-start')).toBeVisible();
  await page.locator('#empty-generate').click();
  await expect(guide('roam-reveal')).toBeVisible();
  await page.locator('#roam-privacy').click();
  await expect(guide('roam-feedback')).toBeVisible();
  await page.locator('#like').click();
  await expect(guide('anchors-open')).toBeVisible();
  await page.locator('[data-guide-focus="anchors.trigger"]').waitFor();
  await page.locator('.roam-anchor-trigger').click();
  await expect(guide('anchors-pick')).toBeVisible();
  await page.locator('.roam-anchor-terms').getByRole('button').filter({ hasText: /^garden$/ }).click();
  await expect(guide('anchors-next')).toBeVisible();
  const before = await page.locator('#main-image').getAttribute('src');
  await page.locator('#next').click();
  await expect(guide('anchors-clear')).toBeVisible();
  await expect(page.locator('#main-image')).not.toHaveAttribute('src', before);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

async function prepareUnratedImage(page, context) {
  await dismissTour(context);
  await page.goto('/#feed');
  await expect(page.locator('#empty-generate:visible, #image-card:visible').first()).toBeVisible();
  if (await page.locator('#empty-generate').isVisible()) await page.locator('#empty-generate').click();
  await expect(page.locator('#main-image')).toHaveAttribute('src', /\/api\/artifacts\/.+\/image/);
  const image = await page.locator('#main-image').getAttribute('src');
  const response = await page.request.put(image.replace(/\/image$/, '/feedback'), { data: { value: null } });
  expect(response.ok()).toBe(true);
  await page.reload();
  await expect(page.locator('#image-card')).toBeVisible();
  await expect(page.locator('#like')).toHaveAttribute('aria-pressed', 'false');
}

test('Roam feedback keys keep image acknowledgements and leave failures in notifications', async ({ page, context }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await prepareUnratedImage(page, context);
  const overlay = page.locator('#immersive-feedback');
  const stage = page.locator('#image-card .image-stage');
  const before = await stage.boundingBox();
  await page.locator('#image-card').focus();
  for (const [key, message] of [['ArrowUp', 'Liked'], ['ArrowDown', 'Like removed'], ['ArrowDown', 'Disliked'], ['ArrowUp', 'Dislike removed']]) {
    await page.keyboard.press(key);
    await expect(overlay).toBeVisible();
    await expect(overlay).toHaveText(message);
    await expect(page.locator('.notification-card[data-kind="success"][data-state="open"]')).toHaveCount(0);
  }
  expect(await stage.boundingBox()).toEqual(before);
  const image = await stage.boundingBox(), feedback = await overlay.boundingBox();
  expect(Math.abs(feedback.x + feedback.width / 2 - image.x - image.width / 2)).toBeLessThan(1);
  await expect(overlay).toBeHidden();

  await page.locator('#roam-immersive').click();
  await expect(page.locator('#image-card')).toHaveClass(/immersive/);
  await page.keyboard.press('ArrowUp');
  await expect(overlay).toBeVisible();
  await expect(overlay).toHaveText('Liked');
  await expect(page.locator('#image-card')).toHaveClass(/immersive-controls-hidden/);
  await expect(page.locator('.notification-card[data-state="open"]')).toHaveCount(0);

  await page.route('**/api/artifacts/*/feedback', route => route.fulfill({ status: 503, json: { error: 'Feedback fixture unavailable' } }));
  await page.keyboard.press('ArrowDown');
  await expect(notice(page)).toContainText('Feedback fixture unavailable');
  await expect(overlay).toBeHidden();
  await expect(page.locator('#image-card')).toHaveClass(/immersive/);
});

test('Roam feedback standalone swipes use the image acknowledgement', async ({ page, context }) => {
  await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
  await page.setViewportSize({ width: 390, height: 844 });
  await prepareUnratedImage(page, context);
  const stage = page.locator('#image-card .image-stage');
  for (const [delta, message] of [[-100, 'Liked'], [100, 'Like removed'], [100, 'Disliked']]) {
    await stage.evaluate((element, delta) => {
      const rect = element.getBoundingClientRect();
      const touch = y => new Touch({ identifier: 1, target: element, clientX: rect.x + rect.width / 2, clientY: y });
      const start = touch(rect.y + rect.height / 2), end = touch(start.clientY + delta);
      element.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [start], changedTouches: [start] }));
      element.dispatchEvent(new TouchEvent('touchmove', { bubbles: true, cancelable: true, touches: [end], changedTouches: [end] }));
      element.dispatchEvent(new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [end] }));
    }, delta);
    await expect(page.locator('#immersive-feedback')).toBeVisible();
    await expect(page.locator('#immersive-feedback')).toHaveText(message);
    await expect(page.locator('.notification-card[data-state="open"]')).toHaveCount(0);
  }
});

test('saved API settings reach Generate and navigation retains its draft', async ({ page, context }) => {
  await dismissTour(context);
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
  await page.locator('#backend-name').fill('Saved browser API');
  await page.locator('#save-backend').click();
  await expect(notice(page)).toContainText('saved');
  await page.locator('[data-view="generate"]').click();
  await page.locator('#positive').fill('garden, sunlight');
  await page.locator('[data-view="settings"]').click();
  await page.locator('[data-view="generate"]').click();
  await expect(page.locator('#positive')).toHaveValue('garden, sunlight');
  const submitted = page.waitForResponse(response => response.url().endsWith('/api/jobs') && response.request().method() === 'POST');
  await page.locator('#generate').click();
  expect((await submitted).status()).toBe(202);
  await expect(page.locator('#compose .generated-card')).toHaveCount(1);
  await page.locator('[data-view="settings"]').click();
  await page.getByRole('tab', { name: 'History', exact: true }).click();
  const job = page.locator('#job-list .job').first();
  await job.locator('.collapsible-label').click();
  await expect(job.locator('.job-meta')).toContainText('Saved browser API');
  await expect(job.locator('.job-meta dt')).toHaveText(['Status', 'Time', 'Image API', 'Seed', 'Task ID']);
  await expect(job.locator('.job-prompt').first()).toHaveText('garden, sunlight');
  await page.locator('[data-view="generate"]').click();
  await page.locator('[data-view="settings"]').click();
  await expect(job.locator('.job-body')).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('task-history.png') });
});
