import { test, expect } from './fixtures.mjs';

const gradient = '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><defs><linearGradient id="color"><stop stop-color="#b94a70"/><stop offset="1" stop-color="#458bb7"/></linearGradient></defs><path fill="url(#color)" d="M0 0h300v400H0z"/></svg>';

async function checkboxAppearance(control) {
  return control.evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, color: style.color, radius: style.borderRadius,
      width: style.width, height: style.height, border: style.borderColor };
  });
}

async function fillsCard(card) {
  const imageButton = card.locator('.generated-image-button');
  const thumbnail = card.locator('.generated-thumbnail');
  const frame = await card.boundingBox();
  const image = await thumbnail.boundingBox();
  for (const property of ['x', 'y', 'width', 'height']) {
    expect(Math.abs(frame[property] - image[property]), `${property} fills the card`).toBeLessThan(.6);
  }
  const edges = await imageButton.evaluate(element => {
    const style = getComputedStyle(element);
    return [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth];
  });
  expect(edges).toEqual(['0px', '0px', '0px', '0px']);
}

for (const width of [1365, 390]) for (const theme of ['light', 'dark']) {
  test(`collection images and shared checkboxes at ${width}px ${theme}`, async ({ page, context }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
    await page.request.put('/api/settings/general', { data: { language: 'zh-CN', theme } });
    const submitted = await page.request.post('/api/jobs', { data: {
      request_id: 'collection-appearance', backend_id: 'fixture', positive: 'garden', negative: '', seed: 1,
    } });
    expect(submitted.status()).toBe(202);
    await expect.poll(async () => (await (await page.request.get('/api/artifacts')).json()).artifacts.length).toBe(1);
    const image = (await (await page.request.get('/api/artifacts')).json()).artifacts[0];
    await page.request.put(`/api/artifacts/${image.id}/feedback`, { data: { value: 1 } });
    await page.route('**/api/artifacts/*/image', route => route.fulfill({ contentType: 'image/svg+xml', body: gradient }));
    await page.goto('/#settings/general');
    await expect(page.locator('#network-enabled')).toBeEnabled();
    const uncheckedStyle = await checkboxAppearance(page.locator('#network-enabled'));
    const checkedStyle = await checkboxAppearance(page.locator('#image-transitions'));

    await page.goto('/#liked');
    const collection = page.locator('#liked-view');
    const card = collection.locator('.generated-card').first();
    await expect(card.locator('img')).toBeVisible();
    await fillsCard(card);
    await collection.getByRole('button', { name: '多选导出', exact: true }).click();
    const checkbox = card.getByRole('checkbox');
    expect(await checkboxAppearance(checkbox)).toEqual(uncheckedStyle);
    await page.screenshot({ path: testInfo.outputPath('liked-unchecked.png'), animations: 'disabled' });
    await checkbox.check();
    expect(await checkboxAppearance(checkbox)).toEqual(checkedStyle);
    const inset = await checkbox.boundingBox();
    const frame = await card.boundingBox();
    expect(inset.x - frame.x).toBe(12);
    expect(inset.y - frame.y).toBe(12);
    await page.screenshot({ path: testInfo.outputPath('liked-checked.png'), animations: 'disabled' });
    await page.getByRole('button', { name: '关闭毛玻璃 · 空格', exact: true }).click();
    await fillsCard(card);
    await page.screenshot({ path: testInfo.outputPath('liked-clear.png'), animations: 'disabled' });

    await page.goto('/#generate');
    const generated = page.locator('#compose .generated-card').first();
    await fillsCard(generated);
    const button = generated.locator('.generated-image-button');
    await button.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(button).toBeFocused();
    expect(await button.evaluate(element => getComputedStyle(element).outlineOffset)).toBe('-2px');
  });
}
