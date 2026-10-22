import { test, expect } from './fixtures.mjs';

test('standalone generation, API creation and preference reset work without randomUUID', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.addInitScript(() => {
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true });
    Object.defineProperty(navigator, 'standalone', { value: true });
    localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' }));
  });
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN' } });
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
  expect(await page.evaluate(() => typeof crypto.randomUUID)).toBe('undefined');
  await page.locator('#edit-backend').click();
  await page.getByRole('option', { name: '＋ 添加 API', exact: true }).click();
  await page.locator('#backend-name').fill('LAN setup');
  const saved = page.waitForResponse(response => /\/api\/backends\/[^/]+$/.test(response.url()) && response.request().method() === 'PUT');
  await page.locator('#save-backend').click();
  const savedResponse = await saved;
  expect(savedResponse.status()).toBe(200);
  expect(new URL(savedResponse.url()).pathname.split('/').at(-1)).toMatch(/^[0-9a-f-]{36}$/);
  await expect(page.locator('#save-backend')).toBeEnabled();
  await page.locator('[data-view=generate]').click();
  await page.locator('#positive').fill('garden, sunlight');
  const requests = [];
  await page.route('**/api/jobs', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    requests.push(route.request().postDataJSON());
    return requests.length === 1
      ? route.fulfill({ status: 503, json: { error: 'Temporary test failure' } })
      : route.fallback();
  });
  await page.locator('#generate').click();
  await expect(page.locator('.notification-card[data-state=open]')).toContainText(['Temporary test failure']);
  await page.locator('#generate').click();
  await expect(page.locator('#compose .generated-card')).toHaveCount(1);
  expect(requests).toHaveLength(2);
  expect(requests[1].request_id).toBe(requests[0].request_id);
  expect(requests[0].request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  await page.goto('/#settings/roam');
  await page.getByRole('button', { name: '重置用户偏好', exact: true }).click();
  const reset = page.waitForResponse(response => response.url().endsWith('/api/recommendation/preferences/reset') && response.request().method() === 'POST');
  await page.getByRole('alertdialog').getByRole('button', { name: '重置偏好', exact: true }).click();
  const resetResponse = await reset;
  expect(resetResponse.status()).toBe(200);
  expect((await resetResponse.json()).request_id).toMatch(/^[0-9a-f-]{36}$/);
  await expect(page.getByRole('alertdialog')).toBeHidden();
});
