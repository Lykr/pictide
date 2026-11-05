import { test, expect } from './fixtures.mjs';

async function prepare(page, context) {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN' } });
  for (let index = 0; index < 3; index++) {
    expect((await page.request.post('/api/jobs', { data: {
      request_id: `recovery-${index}`, backend_id: 'fixture', positive: 'garden', negative: '', seed: index,
    } })).status()).toBe(202);
  }
  await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).artifacts.length).toBe(3);
  const images = (await (await page.request.get('/api/artifacts')).json()).artifacts;
  for (const image of images) await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
  return images;
}

for (const width of [1365, 390]) {
  test(`toolbar recovery, privacy and silent unlike at ${width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const images = await prepare(page, context);
    const hidden = images[2];
    await page.request.delete(`/api/generated/${hidden.id}`, { data: {} });
    await page.request.put(`/api/artifacts/${hidden.id}/feedback`, { data: { value: null } });
    await page.goto('/#liked');
    const collection = page.locator('#liked-view');
    await expect(collection.locator('.generated-card')).toHaveCount(2);
    const tools = page.locator('#liked-privacy-controls');
    const history = tools.getByRole('button', { name: '最近取消喜欢', exact: true });
    const exportBox = await tools.getByRole('button', { name: '多选导出', exact: true }).boundingBox();
    const historyBox = await history.boundingBox();
    expect(historyBox.x).toBeGreaterThanOrEqual(exportBox.x + exportBox.width);
    expect(historyBox.width).toBe(exportBox.width); expect(historyBox.height).toBe(exportBox.height);
    await history.click();
    const recent = page.getByRole('dialog', { name: '最近取消喜欢', exact: true }).filter({ has: page.locator('.recent-unlikes-grid') });
    const cards = recent.locator('[data-recent-unlike]');
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toHaveAttribute('data-recent-unlike', hidden.id);
    await expect(cards.first()).toContainText('剩余 24 小时');
    expect(await cards.locator('img').evaluate(node => getComputedStyle(node).filter)).toBe('blur(24px)');
    await cards.getByRole('button', { name: `查看图片 ${hidden.id}`, exact: true }).click();
    const viewer = page.locator('.generated-viewer');
    await expect(viewer).toBeVisible();
    await expect(viewer.getByRole('link', { name: '下载原图', exact: true })).toHaveCount(0);
    await viewer.getByRole('button', { name: '关闭毛玻璃 · 空格', exact: true }).click();
    await viewer.getByRole('button', { name: '关闭图片', exact: true }).click();
    await expect(recent).toBeVisible();
    expect(await cards.locator('img').evaluate(node => getComputedStyle(node).filter)).toBe('none');
    const bounds = await recent.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    expect((await cards.getByRole('button', { name: '重新喜欢', exact: true }).boundingBox()).height).toBeGreaterThanOrEqual(44);
    await page.screenshot({ path: testInfo.outputPath('recent-unlikes.png'), animations: 'disabled' });
    await cards.getByRole('button', { name: '重新喜欢', exact: true }).click();
    await expect(recent.getByText('最近 24 小时没有取消喜欢的图片。', { exact: true })).toBeVisible();
    await recent.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(history).toBeFocused();
    await expect(collection.locator('.generated-card')).toHaveCount(3);
    const generated = (await (await page.request.get('/api/artifacts?source=generate')).json()).artifacts;
    expect(generated.some(item => item.id === hidden.id)).toBe(false);

    await collection.locator('.generated-card-like').first().click();
    await expect(page.getByRole('alertdialog')).toBeVisible();
    await page.getByRole('alertdialog').getByRole('button', { name: '确认', exact: true }).click();
    await expect(collection.locator('.generated-card')).toHaveCount(2);
    await expect(page.locator('.notification-card').filter({ hasText: '已取消喜欢' })).toHaveCount(0);
    await history.click();
    await expect(cards).toHaveCount(1);
    await cards.getByRole('button', { name: '重新喜欢', exact: true }).click();
    await expect(cards).toHaveCount(0);
    await recent.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(collection.locator('.generated-card')).toHaveCount(3);
    await page.reload();
    await expect(collection.locator('.generated-card')).toHaveCount(3);
    await history.click();
    await expect(recent.getByText('最近 24 小时没有取消喜欢的图片。', { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(history).toBeFocused();
  });
}

test('recovery stays available with no likes and recovers from a failed read', async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 740 });
  const images = await prepare(page, context);
  for (const image of images) await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: null } });
  await page.goto('/#liked');
  await page.reload();
  await expect(page.locator('#liked-view .generated-card')).toHaveCount(0);
  let failed = false;
  await page.route('**/api/liked/recently-unliked?*', async route => {
    if (failed) return route.continue();
    failed = true;
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Fixture unavailable' }) });
  });
  const history = page.locator('#liked-privacy-controls').getByRole('button', { name: '最近取消喜欢', exact: true });
  await expect(history).toBeEnabled();
  await history.click();
  const recent = page.locator('.recent-unlikes-dialog');
  await expect(recent.locator('.recent-unlikes-more').getByRole('button', { name: '重试', exact: true })).toBeVisible();
  await recent.locator('.recent-unlikes-more').getByRole('button', { name: '重试', exact: true }).click();
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(3);
  expect(await recent.locator('.recent-unlikes-grid').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length)).toBe(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.screenshot({ path: testInfo.outputPath('empty-liked-recovery-320.png'), animations: 'disabled' });
  await recent.getByRole('button', { name: '重新喜欢', exact: true }).first().click();
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(2);
  await recent.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.locator('#liked-view .generated-card')).toHaveCount(1);
  const sort = page.getByRole('combobox', { name: '喜欢图片排序', exact: true });
  await sort.click();
  await page.getByRole('option', { name: '偏好评分', exact: true }).click();
  await expect(sort).toContainText('偏好评分');
  await history.click();
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(2);
  await recent.getByRole('button', { name: '重新喜欢', exact: true }).first().click();
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(1);
  await recent.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.locator('#liked-view .generated-card')).toHaveCount(2);
  await expect(sort).toContainText('偏好评分');
});

test('a long English recovery list scrolls inside the phone safe area in dark mode', async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 480 });
  await prepare(page, context);
  for (let index = 3; index < 12; index++) {
    await page.request.post('/api/jobs', { data: {
      request_id: `recovery-${index}`, backend_id: 'fixture', positive: 'garden', negative: '', seed: index,
    } });
  }
  await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).artifacts.length).toBe(12);
  const images = (await (await page.request.get('/api/artifacts')).json()).artifacts;
  for (const image of images) {
    await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
    await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: null } });
  }
  await page.request.put('/api/settings/general', { data: { language: 'en', theme: 'dark' } });
  await page.goto('/#liked');
  await page.evaluate(() => {
    for (const [side, value] of Object.entries({ top: 20, right: 24, bottom: 34, left: 0 })) document.documentElement.style.setProperty(`--safe-area-${side}`, `${value}px`);
  });
  await page.locator('#liked-privacy-controls').getByRole('button', { name: 'Recently unliked', exact: true }).click();
  const recent = page.locator('.recent-unlikes-dialog');
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(12);
  const bounds = await recent.boundingBox();
  expect(bounds.y).toBeGreaterThanOrEqual(20); expect(bounds.y + bounds.height).toBeLessThanOrEqual(480 - 34);
  expect(bounds.x).toBeGreaterThanOrEqual(16); expect(bounds.x + bounds.width).toBeLessThanOrEqual(390 - 24);
  expect(await recent.locator('.recent-unlikes-scroll').evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  await expect(recent.getByRole('button', { name: 'Close', exact: true })).toBeInViewport();
  const last = recent.getByRole('button', { name: 'Like again', exact: true }).last();
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('long-recovery-dark-phone.png'), animations: 'disabled' });
  await last.click();
  await expect(recent.locator('[data-recent-unlike]')).toHaveCount(11);
  await recent.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.locator('#liked-view .generated-card')).toHaveCount(1);
});
