import { test, expect } from './fixtures.mjs';

for (const width of [1365, 390]) {
  test(`grids request previews and large views keep originals at ${width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
    await page.request.put('/api/settings/general', { data: { language: 'zh-CN' } });
    for (let index = 0; index < 3; index++) {
      expect((await page.request.post('/api/jobs', { data: {
        request_id: `thumbnail-${index}`, backend_id: 'fixture', positive: 'garden', negative: '', seed: index,
      } })).status()).toBe(202);
    }
    await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).artifacts.length).toBe(3);
    const artifacts = (await (await page.request.get('/api/artifacts')).json()).artifacts;
    for (const item of artifacts.slice(0, 2)) await page.request.put(`/api/artifacts/${item.id}/feedback`, { data: { value: 1 } });
    const images = [];
    page.on('request', request => { if (/\/api\/artifacts\/[^/]+\/image/.test(request.url())) images.push(new URL(request.url())); });
    await page.goto('/#liked');
    const liked = page.locator('#liked-view');
    await expect(liked.locator('.generated-card')).toHaveCount(2);
    const previews = liked.locator('.generated-thumbnail img');
    await expect(previews.first()).toHaveAttribute('src', /\/image\?thumbnail=1$/);
    await expect.poll(() => previews.evaluateAll(nodes => nodes.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
    expect(images.length).toBeGreaterThan(0);
    expect(images.every(url => url.searchParams.get('thumbnail') === '1')).toBe(true);
    const first = await previews.first().getAttribute('src');
    const thumb = await page.request.get(first);
    expect(thumb.headers()['content-type']).toBe('image/webp');
    expect((await thumb.body()).subarray(0, 4).toString()).toBe('RIFF');
    const originalRequest = page.waitForRequest(request => new URL(request.url()).pathname === first.split('?')[0] && !new URL(request.url()).search);
    await liked.locator('.generated-image-button').first().click();
    await originalRequest;
    const viewer = page.locator('.generated-viewer');
    await expect(viewer.locator('.generated-viewer-stage img')).toHaveAttribute('src', first.split('?')[0]);
    await expect(viewer.getByRole('link', { name: '下载原图', exact: true })).toHaveAttribute('href', first.split('?')[0] + '?download=1');
    await viewer.getByRole('button', { name: '关闭图片', exact: true }).click();
    await page.goto('/#generate');
    const generated = page.locator('#compose .generated-thumbnail img');
    await expect(generated).toHaveCount(3);
    expect(await generated.evaluateAll(nodes => nodes.every(image => new URL(image.src).searchParams.get('thumbnail') === '1'))).toBe(true);
    await page.request.put(`/api/artifacts/${artifacts[1].id}/feedback`, { data: { value: null } });
    await page.goto('/#liked');
    await page.locator('#liked-privacy-controls').getByRole('button', { name: '最近取消喜欢', exact: true }).click();
    const recent = page.locator('.recent-unlikes-dialog');
    await expect(recent.locator('[data-recent-unlike]')).toHaveCount(1);
    await expect(recent.locator('.generated-thumbnail img')).toHaveAttribute('src', `/api/artifacts/${artifacts[1].id}/image?thumbnail=1`);
    await expect.poll(() => recent.locator('img').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('thumbnail-grid.png'), animations: 'disabled' });
    await recent.getByRole('button', { name: '关闭', exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await expect(page.getByText('图片已清理或读取失败', { exact: true })).toHaveCount(0);
  });
}
