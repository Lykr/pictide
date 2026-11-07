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
  const likedColor = await photo.locator('[data-liked-marker]').evaluate(element => getComputedStyle(element).color);
  await expect.poll(() => page.locator('#like').evaluate(element => getComputedStyle(element).color)).toBe(likedColor);
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
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await expect(scroll).toHaveAttribute('data-focus', likedId);
  await page.waitForTimeout(150);
  const resumedDistance = beforeNext.before - await offset();
  expect(resumedDistance).toBeGreaterThan(0);
  expect(resumedDistance).toBeLessThan(35);
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
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

test.describe('PWA privacy surfaces', () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  for (const theme of ['light', 'dark']) test(`blur stays on individual pictures after mode changes in ${theme}`, async ({ page, context }, testInfo) => {
    await page.route(/\/static\/ui\/[^/]+\.css$/, async route => {
      const response = await route.fetch();
      // Desktop engines cannot select iOS's installed-app display mode directly.
      const css = (await response.text()).replaceAll('(display-mode:standalone)', '(min-width:0px)').replaceAll('(display-mode:browser)', '(max-width:0px)');
      await route.fulfill({ response, body: css });
    });
    await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await page.request.put('/api/settings/general', { data: { theme, language: 'en' } });
    const { scroll } = await prepare(page, context, 2);
    const stage = page.locator('#image-card .image-stage');
    const noSharedWash = async () => {
      expect(await stage.evaluate(node => getComputedStyle(node, '::after').content), 'Scroll must not generate a stage-wide privacy wash').toBe('none');
      await expect(stage.locator('.roam-privacy-wash')).toHaveCount(0);
      await expect(scroll.locator('img').first()).toBeHidden();
      await expect(scroll.locator('canvas').first()).toBeVisible();
      expect(await scroll.locator('canvas').first().evaluate(node => getComputedStyle(node).filter)).toBe('none');
      expect(await scroll.locator('.roam-scroll-picture').first().evaluate(node => getComputedStyle(node).filter)).toBe('none');
    };
    await noSharedWash();
    await page.locator('#roam-options').click();
    await page.locator('.roam-options-panel').getByRole('radio', { name: 'Single', exact: true }).click();
    await page.locator('#roam-options').click();
    await expect(page.locator('#main-image')).toBeVisible();
    await expect(stage.locator('.roam-single-image > .roam-privacy-wash')).toBeVisible();
    const privacy = page.locator('#roam-privacy');
    await privacy.click();
    await expect(stage.locator('.roam-privacy-wash')).toHaveCount(0);
    expect(await page.locator('#main-image').evaluate(node => getComputedStyle(node).filter)).toBe('none');
    await privacy.click();
    await page.locator('#roam-options').click();
    await page.locator('.roam-options-panel').getByRole('radio', { name: 'Scroll', exact: true }).click();
    await page.locator('#roam-options').click();
    await expect(scroll).toBeVisible();
    await noSharedWash();
    for (const viewport of [{ width: 844, height: 390 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      await noSharedWash();
    }
    await page.screenshot({ path: testInfo.outputPath('pwa-scroll-blur.png'), animations: 'disabled' });
  });
});

test('scroll privacy covers decoded pictures without seams through reveal, resizing and playback', async ({ page, context }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route(/\/api\/artifacts\/[^/]+\/image$/, route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="2048" height="3072"><defs><pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse"><path fill="#d04c8f" d="M0 0h64v64H0z"/><path fill="#40a3b5" d="M0 0h32v32H0zm32 32h32v32H32z"/></pattern></defs><path fill="url(#grid)" d="M0 0h2048v3072H0z"/></svg>',
  }));
  const { scroll } = await prepare(page, context, 3);
  const covered = async () => {
    await expect.poll(() => scroll.locator('.roam-scroll-picture').evaluateAll(pictures => pictures.every(picture => {
      const canvas = picture.querySelector('canvas'), image = picture.querySelector('img');
      if (!canvas || canvas.width > 192 || canvas.height !== 192 || !image.hidden) return false;
      const frame = picture.getBoundingClientRect(), preview = canvas.getBoundingClientRect();
      if (Math.abs(preview.height - frame.height) > 1 || Math.abs(preview.width - frame.width) > 1) return false;
      const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      // A high-frequency two-color pattern must become a smooth, opaque mix
      // throughout the image, including both sides of the reported lower band.
      for (let y = 0; y < canvas.height; y++) {
        const i = (y * canvas.width + Math.floor(canvas.width / 2)) * 4;
        if (Math.abs(pixels[i] - 136) > 10 || Math.abs(pixels[i + 1] - 120) > 10 || Math.abs(pixels[i + 2] - 162) > 10 || pixels[i + 3] !== 255) return false;
      }
      return true;
    }))).toBe(true);
  };
  await covered();
  const original = await scroll.locator('img').first().elementHandle();
  await page.locator('#roam-privacy').click();
  await expect(scroll.locator('canvas')).toHaveCount(0);
  await expect(scroll.locator('img').first()).toBeVisible();
  expect(await original.evaluate(image => image.isConnected && image.complete && image.naturalHeight === 3072)).toBe(true);
  await page.locator('#roam-privacy').click();
  await covered();
  for (const viewport of [{ width: 844, height: 390 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await covered();
  }
  await page.locator('#roam-playback').click();
  const start = await scroll.getAttribute('data-offset');
  await expect.poll(() => scroll.getAttribute('data-offset')).not.toBe(start);
  await page.locator('#like').click();
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
  await covered();
  await page.locator('#roam-immersive').click();
  await expect(page.locator('#image-card')).toHaveClass(/immersive/);
  await covered();
  await page.screenshot({ path: testInfo.outputPath('scroll-raster-privacy.png'), animations: 'disabled' });
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

test('switching focus does not stall the strip halfway through navigation', async ({ page, context }) => {
  const { scroll } = await prepare(page, context, 4);
  const samples = await scroll.evaluate(element => new Promise(resolve => {
    const photo = element.querySelector('[data-artifact-id]');
    const start = photo.getBoundingClientRect().left;
    const samples = [{ time: performance.now(), distance: 0 }];
    document.querySelector('#next').click();
    const sample = time => {
      samples.push({ time, distance: start - photo.getBoundingClientRect().left });
      if (element.dataset.moving === 'true' && time - samples[0].time < 2000) requestAnimationFrame(sample);
      else resolve(samples);
    };
    requestAnimationFrame(sample);
  }));
  const distance = samples.at(-1).distance;
  expect(distance).toBeGreaterThan(100);
  const velocities = samples.slice(1).map((sample, index) => ({
    progress: sample.distance / distance,
    speed: (sample.distance - samples[index].distance) / (sample.time - samples[index].time),
  })).filter(sample => sample.progress > .35 && sample.progress < .65).map(sample => sample.speed);
  expect(velocities.length).toBeGreaterThanOrEqual(2);
  expect(Math.min(...velocities)).toBeGreaterThan(Math.max(...velocities) * .35);
});

test('editing anchors keeps the centered picture and honors the history limit', async ({ page, context }) => {
  await page.route(/\/api\/artifacts\/[^/]+\/image$/, route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="640"><rect width="320" height="640" fill="#60766a"/></svg>',
  }));
  const { scroll, items } = await prepare(page, context, 5);
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  const visible = await scroll.evaluate(element => {
    const bounds = element.getBoundingClientRect();
    return [...element.querySelectorAll('[data-artifact-id]')].filter(photo => {
      const rect = photo.getBoundingClientRect(); return rect.right > bounds.left && rect.left < bounds.right;
    }).map(photo => photo.dataset.artifactId);
  });
  expect(visible.indexOf(items[2].id)).toBeGreaterThan(0);
  await expect.poll(async () => (await (await page.request.get('/api/roam/view')).json()).artifact_id).toBe(items[2].id);
  expect((await page.request.put('/api/settings/roam', { data: { prefetch_count: 0, max_history_images: 1 } })).ok()).toBe(true);
  await page.locator('.roam-anchor-trigger').click();
  const current = scroll.locator(`[data-artifact-id="${items[2].id}"]`);
  const position = await current.evaluate(element => element.getBoundingClientRect().left);
  const input = page.getByRole('combobox', { name: 'Add anchor', exact: true });
  if (!await input.isVisible()) await page.locator('.roam-anchor-add').getByRole('button', { name: 'Add anchor', exact: true }).click();
  await input.fill('scroll anchor fixture');
  await input.press('Enter');
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).pinned_positive).toContain('scroll anchor fixture');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  const remaining = (await (await page.request.get(`/api/artifacts?source=roam&around=${items[2].id}`)).json()).artifacts.map(item => item.id);
  expect(remaining).toContain(items[2].id);
  expect(remaining).toContain(items[1].id);
  expect(remaining).not.toContain(items[0].id);
  expect(remaining).not.toContain(items[3].id);
  expect(await current.evaluate(element => element.getBoundingClientRect().left)).toBeCloseTo(position, 0);
  await page.locator('.roam-anchor-term').filter({ hasText: 'scroll anchor fixture' }).click({ button: 'right' });
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).excluded_positive).toContain('scroll anchor fixture');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await page.getByRole('button', { name: 'Clear anchors', exact: true }).click();
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).excluded_positive).toEqual([]);
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
});
