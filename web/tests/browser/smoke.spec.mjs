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
