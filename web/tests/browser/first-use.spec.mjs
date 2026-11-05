import { readFile } from 'node:fs/promises';
import { test, expect } from './fixtures.mjs';

async function prepare(page, context) {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN' } });
}

async function favorites(page) {
  for (let index = 0; index < 3; index++) {
    const response = await page.request.post('/api/jobs', { data: {
      request_id: `export-${index}`, backend_id: 'fixture', positive: 'garden', negative: '', seed: index,
    } });
    expect(response.status()).toBe(202);
  }
  await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).artifacts.length).toBe(3);
  const images = (await (await page.request.get('/api/artifacts')).json()).artifacts;
  for (const image of images.slice(0, 2)) await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
  return images;
}

for (const width of [1365, 390]) {
  test(`liked original and selected ZIP export at ${width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await prepare(page, context);
    const images = await favorites(page);
    await page.goto('/#liked');
    const collection = page.locator('#liked-view');
    await expect(collection.locator('.generated-card')).toHaveCount(2);
    await collection.locator('.generated-image-button').first().click();
    const original = page.getByRole('link', { name: '下载原图', exact: true });
    await expect(original).toBeVisible();
    const originalDownload = page.waitForEvent('download');
    await original.click();
    const downloaded = await originalDownload;
    const source = await page.request.get(`/api/artifacts/${images[0].id}/image`);
    expect(await readFile(await downloaded.path())).toEqual(await source.body());
    await page.getByRole('button', { name: '关闭图片', exact: true }).click();
    const header = page.locator('#liked-privacy-controls');
    const exportButton = header.getByRole('button', { name: '多选导出', exact: true });
    const blurBox = await header.locator('[data-collection=liked]').boundingBox();
    const exportBox = await exportButton.boundingBox();
    expect(exportBox.x).toBeGreaterThanOrEqual(blurBox.x + blurBox.width);
    expect(exportBox.width).toBe(blurBox.width);
    expect(exportBox.height).toBe(blurBox.height);
    await exportButton.click();
    await expect(header.getByRole('button', { name: '退出选择', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await collection.getByRole('checkbox').first().check();
    await header.getByRole('button', { name: '退出选择', exact: true }).click();
    await expect(collection.getByRole('checkbox')).toHaveCount(0);
    await exportButton.click();
    await expect(collection.getByText('已选 0 张', { exact: true })).toBeVisible();
    await collection.getByRole('checkbox').first().check();
    await collection.getByRole('button', { name: '全选已加载', exact: true }).click();
    await expect(collection.getByText('已选 2 张', { exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('liked-selection.png'), animations: 'disabled' });
    const zipDownload = page.waitForEvent('download');
    await collection.getByRole('button', { name: '导出 ZIP', exact: true }).click();
    const zip = await zipDownload;
    expect(zip.suggestedFilename()).toBe('pictide-liked.zip');
    const bytes = await readFile(await zip.path());
    expect(bytes.subarray(0, 4)).toEqual(Buffer.from([0x50, 0x4b, 0x03, 0x04]));
    expect(bytes.includes(Buffer.from(images[0].id + '.png'))).toBe(true);
    expect(bytes.includes(Buffer.from(images[1].id + '.png'))).toBe(true);
    expect(bytes.includes(Buffer.from(images[2].id + '.png'))).toBe(false);
    await collection.locator('.generated-card-like').first().click();
    await page.getByRole('alertdialog').getByRole('button', { name: '确认', exact: true }).click();
    await expect(collection.getByText('已选 1 张', { exact: true })).toBeVisible();
    await page.goto('/#generate');
    await page.locator('#compose .generated-image-button').first().click();
    await expect(page.getByRole('link', { name: '下载原图', exact: true })).toHaveCount(0);
  });

  test(`runtime LAN access and recommended workflow at ${width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await prepare(page, context);
    await page.goto('/#settings/general');
    const enabled = page.locator('#network-enabled');
    await expect(enabled).toBeEnabled();
    await enabled.click();
    await expect(enabled).toBeChecked();
    const qr = page.locator('[data-network-settings] svg:has(title)');
    await expect(qr).toBeVisible();
    const status = await (await page.request.get('/api/settings/network')).json();
    expect(status.enabled).toBe(true);
    expect(status.urls.length).toBeGreaterThan(0);
    await expect(page.locator('[data-network-settings] a')).toHaveAttribute('href', status.urls[0]);
    await qr.scrollIntoViewIfNeeded();
    const box = await qr.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: testInfo.outputPath('lan-settings.png'), animations: 'disabled' });
    await enabled.click();
    await expect(enabled).not.toBeChecked();
    await expect(qr).toHaveCount(0);
    expect((await (await page.request.get('/api/settings/network')).json()).enabled).toBe(false);
    await page.goto('/#settings/backend');
    await page.locator('#recommended-workflow').click();
    await expect(page.locator('#workflow-name--control')).toHaveValue('Anima Turbo v1.1');
    const settings = page.locator('#settings-backend');
    await expect(settings.getByText('28 · Empty Latent Image → width', { exact: true }).first()).toBeVisible();
  });
}
