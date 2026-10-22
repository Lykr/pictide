import { test, expect } from './fixtures.mjs';

const scenarios = [
  { name: 'desktop-light-en', width: 1365, height: 900, theme: 'light', language: 'en' },
  { name: 'phone-dark-zh', width: 390, height: 844, theme: 'dark', language: 'zh-CN' },
  { name: 'wide-dark-en', width: 1920, height: 1080, theme: 'dark', language: 'en' },
];
const center = box => box.x + box.width / 2;
async function withinViewport(page, locator) {
  const box = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
}
async function toolbarLayout(card) {
  const toolbar = card.locator('[data-image-toolbar]');
  const bar = await toolbar.boundingBox();
  const navigation = await toolbar.locator('[data-toolbar-slot=navigation]').boundingBox();
  expect(Math.abs(center(bar) - center(navigation))).toBeLessThan(1);
  const information = await toolbar.locator('[data-toolbar-slot=information]').boundingBox();
  expect(information.x + information.width).toBeLessThanOrEqual(navigation.x);
  return toolbar;
}
async function panelLayout(page, card, panel) {
  await expect(panel).toBeVisible();
  await expect.poll(async () => {
    const toolbar = await card.locator('[data-image-toolbar]').boundingBox();
    const box = await panel.boundingBox();
    return Math.abs(center(toolbar) - center(box));
  }).toBeLessThan(1);
  await withinViewport(page, panel);
  const toolbar = await card.locator('[data-image-toolbar]').boundingBox();
  const box = await panel.boundingBox();
  expect(box.y + box.height).toBeLessThan(toolbar.y);
  const surface = await card.locator('[data-image-toolbar]').evaluate(el => getComputedStyle(el).backgroundColor);
  expect(await panel.evaluate(el => getComputedStyle(el).backgroundColor)).toBe(surface);
  return box.width;
}
async function capture(page, testInfo, name) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, animations: 'disabled' });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

for (const scenario of scenarios) test(`shared layout: ${scenario.name}`, async ({ page, context }, testInfo) => {
  await page.setViewportSize(scenario);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { theme: scenario.theme, language: scenario.language } });
  await page.goto('/#feed');
  await expect(page.locator('#empty-generate:visible, #image-card:visible').first()).toBeVisible();
  if (await page.locator('#empty-generate').isVisible()) await page.locator('#empty-generate').click();
  const card = page.locator('#image-card');
  await expect(page.locator('#main-image')).toHaveAttribute('src', /\/api\/artifacts\/.+\/image/);
  await page.evaluate(() => document.fonts.ready);
  await toolbarLayout(card);
  if (scenario.width <= 640) {
    const sizes = await card.locator('[data-image-toolbar] button').evaluateAll(nodes => nodes.map(el => {
      const { width, height } = el.getBoundingClientRect(); return { width, height };
    }));
    for (const size of sizes) { expect(size.width).toBeGreaterThanOrEqual(44); expect(size.height).toBeGreaterThanOrEqual(44); }
  }
  const initial = await card.boundingBox();
  await card.locator('[data-toolbar-slot=information] button').click();
  await expect(page.locator('.image-info-popover')).toBeVisible();
  expect(await card.boundingBox()).toEqual(initial);
  await page.keyboard.press('Escape');
  await expect(card.locator('[data-toolbar-slot=information] button')).toBeFocused();
  await card.locator('.roam-anchor-trigger').click();
  await expect(card.locator('.roam-anchors')).toBeVisible();
  await toolbarLayout(card);
  await withinViewport(page, card);
  await capture(page, testInfo, 'roam-anchors');
  await card.locator('.roam-anchor-trigger').click();
  await page.locator('#roam-immersive').click();
  await expect(card).toHaveClass(/immersive/);
  const information = card.locator('[data-toolbar-slot=information] button');
  await information.click();
  const infoWidth = await panelLayout(page, card, card.locator('.image-info-popover'));
  await capture(page, testInfo, 'immersive-information');
  await page.keyboard.press('Escape');
  await expect(card).toHaveClass(/immersive/);
  await expect(information).toBeFocused();
  await card.locator('.roam-anchor-trigger').click();
  if (scenario.width > 640) await page.emulateMedia({ reducedMotion: 'no-preference' });
  const anchorWidth = await panelLayout(page, card, card.locator('.roam-anchor-popover'));
  expect(anchorWidth).toBe(infoWidth);
  expect(await card.locator('.roam-anchor-popover').evaluate(el => getComputedStyle(el).animationName))
    .toBe(scenario.width > 640 ? 'image-toolbar-panel-expand' : 'none');
  await capture(page, testInfo, 'immersive-anchors');
  await page.keyboard.press('Escape');
  await expect(card.locator('.roam-anchor-popover')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(card).not.toHaveClass(/immersive/);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  // Follow a real saved image into Liked, which shares Generate's large viewer.
  const image = await page.locator('#main-image').getAttribute('src');
  await page.request.put(image.replace(/\/image$/, '/feedback'), { data: { value: 1 } });
  await page.locator('[data-view=liked]').click();
  await page.locator('#liked-view .generated-card').first().click();
  const viewer = page.locator('.generated-viewer');
  await expect(viewer).toBeVisible();
  await toolbarLayout(viewer);
  await viewer.locator('.generated-viewer-heading button').first().click();
  await expect(viewer).toHaveClass(/immersive/);
  await viewer.locator('[data-toolbar-slot=information] button').click();
  expect(await panelLayout(page, viewer, viewer.locator('.image-info-popover'))).toBe(infoWidth);
  await capture(page, testInfo, 'collection-immersive-information');
  await page.keyboard.press('Escape');
  await expect(viewer).toHaveClass(/immersive/);
  await page.keyboard.press('Escape');
  await expect(viewer).not.toHaveClass(/immersive/);
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
  await expect(viewer.locator('.generated-viewer-heading button').first()).toBeFocused();
  await viewer.locator('.generated-viewer-heading button').last().click();
  await expect(viewer).toBeHidden();
  await page.locator('[data-view=generate]').click();
  await page.locator('#positive').fill('garden, sunlight');
  await page.locator('#generate').click();
  await page.locator('#compose .generated-card').first().click();
  await expect(viewer).toBeVisible();
  await toolbarLayout(viewer);
  await viewer.locator('[data-toolbar-slot=information] button').click();
  await expect(viewer.locator('.image-info-popover')).toContainText('garden, sunlight');
  await withinViewport(page, viewer.locator('.image-info-popover'));
  await capture(page, testInfo, 'generate-information');
  await page.keyboard.press('Escape');
  await viewer.locator('.generated-viewer-heading button').last().click();
  await page.goto('/#settings/general');
  await expect(page.locator('.settings-row')).toHaveCount(6);
  const tourButton = page.locator('.general-settings .settings-row[data-separated=true] button');
  const updateButton = page.locator('[data-application-updates] button').first();
  const tourBox = await tourButton.boundingBox(), updateBox = await updateButton.boundingBox();
  const alignedEdge = box => scenario.width <= 640 ? box.x + box.width : box.x;
  expect(Math.abs(alignedEdge(tourBox) - alignedEdge(updateBox))).toBeLessThan(1);
  expect(updateBox.height).toBe(tourBox.height);
  // A long real-world path must wrap inside the shared row rather than widening it.
  await page.locator('#data-directory').evaluate(el => { el.textContent = 'E:\\Pictide\\' + 'long-directory-name-'.repeat(20); });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const controls = await page.locator('.settings-row-control').evaluateAll(nodes => nodes.map(el => el.getBoundingClientRect().x));
  if (scenario.width > 640) expect(Math.max(...controls) - Math.min(...controls)).toBeLessThan(1);
  await capture(page, testInfo, 'settings-long-path');
});

test('large image frames respect nonzero safe areas across rotation and immersion', async ({ page, context }, testInfo) => {
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'standalone', { value: true });
    localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' }));
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#generate');
  await page.locator('#positive').fill('garden, sunlight');
  await page.locator('#generate').click();
  await page.locator('#compose .generated-card').first().click();
  const viewer = page.locator('.generated-viewer');
  await expect(viewer).toBeVisible();
  const orientations = [
    { name: 'portrait', width: 390, height: 844, top: 59, right: 0, bottom: 34, left: 0 },
    { name: 'landscape', width: 844, height: 390, top: 0, right: 0, bottom: 21, left: 59 },
    { name: 'portrait-return', width: 390, height: 844, top: 59, right: 0, bottom: 34, left: 0 },
  ];
  async function checkSafeFrame(area) {
    const left = Math.max(8, area.left), right = Math.max(8, area.right);
    const top = Math.max(8, area.top), bottom = Math.max(8, area.bottom);
    await expect.poll(async () => {
      const box = await viewer.boundingBox();
      return Math.max(Math.abs(box.x - left), Math.abs(box.y - top),
        Math.abs(box.width - (area.width - left - right)), Math.abs(box.height - (area.height - top - bottom)));
    }).toBeLessThan(1);
    const toolbar = await viewer.locator('[data-image-toolbar]').boundingBox();
    const heading = await viewer.locator('.generated-viewer-heading').boundingBox();
    expect(toolbar.y + toolbar.height).toBeLessThanOrEqual(area.height - bottom);
    expect(heading.y).toBeGreaterThanOrEqual(top);
  }
  for (const area of orientations) {
    await page.setViewportSize(area);
    // Desktop engines expose zero device insets; inject only their values, not layout rules.
    await page.evaluate(area => {
      for (const side of ['top', 'right', 'bottom', 'left']) document.documentElement.style.setProperty(`--safe-area-${side}`, `${area[side]}px`);
    }, area);
    await checkSafeFrame(area);
    await capture(page, testInfo, `safe-frame-${area.name}`);
  }
  const portrait = orientations[0];
  await viewer.locator('.generated-viewer-heading button').first().click();
  await expect(viewer).toHaveClass(/immersive/);
  await expect.poll(() => viewer.boundingBox()).toEqual({ x: 0, y: 0, width: portrait.width, height: portrait.height });
  const bar = await viewer.locator('[data-image-toolbar]').boundingBox();
  expect(bar.y + bar.height).toBeLessThanOrEqual(portrait.height - portrait.bottom);
  expect((await viewer.locator('.immersive-actions').boundingBox()).y).toBeGreaterThanOrEqual(portrait.top);
  await page.keyboard.press('Escape');
  await expect(viewer).not.toHaveClass(/immersive/);
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
  await checkSafeFrame(portrait);
  await viewer.getByRole('button', { name: 'Like image · ↑', exact: true }).click();
  await expect(viewer.getByRole('button', { name: 'Unlike', exact: true })).toBeVisible();
  await viewer.locator('.generated-viewer-heading button').last().click();
  await page.locator('[data-view=liked]').click();
  await page.locator('#liked-view .generated-card').first().click();
  await checkSafeFrame(portrait);
  await viewer.locator('[data-toolbar-slot=information] button').click();
  await expect(viewer.locator('.image-info-popover')).toBeVisible();
  await checkSafeFrame(portrait);
});
