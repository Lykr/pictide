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
    return { before, after: Number(el.dataset.offset), time: performance.now() };
  });
  expect(beforeNext.after).toBeCloseTo(beforeNext.before, 1);
  await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await expect(scroll).toHaveAttribute('data-focus', likedId);
  await page.waitForTimeout(150);
  const resumed = await scroll.evaluate(el => new Promise(resolve => requestAnimationFrame(time => resolve({ time, offset: Number(el.dataset.offset) }))));
  const resumedDistance = beforeNext.before - resumed.offset;
  expect(resumedDistance).toBeGreaterThan(0);
  expect(Math.abs(resumedDistance - 80 * (resumed.time - beforeNext.time) / 1000)).toBeLessThan(2);
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

test.describe('PWA picture gestures', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  for (const [name, width, height] of [['portrait', 800, 1200], ['wide', 1600, 600]]) test(`active ${name} Scroll picture stays fully inside the PWA stage`, async ({ page, context }, testInfo) => {
    await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await page.route(/\/static\/ui\/[^/]+\.css$/, async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('(display-mode:standalone)', '(min-width:0px)').replaceAll('(display-mode:browser)', '(max-width:0px)') });
    });
    await page.route(/\/api\/artifacts\/[^/]+\/image$/, route => route.fulfill({
      contentType: 'image/svg+xml',
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="${width}" height="${height}" fill="#52796f"/></svg>`,
    }));
    const { scroll } = await prepare(page, context, 2);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
    await expect(scroll).toHaveAttribute('data-focus', /.+/);
    const bounds = await scroll.evaluate(element => {
      const stage = element.getBoundingClientRect();
      const picture = element.querySelector(`[data-artifact-id="${element.dataset.focus}"]`).getBoundingClientRect();
      return {
        left: picture.left - stage.left,
        right: stage.right - picture.right,
        top: picture.top - stage.top,
        bottom: stage.bottom - picture.bottom,
        aspect: picture.width / picture.height,
      };
    });
    expect(bounds.left).toBeGreaterThanOrEqual(11);
    expect(bounds.right).toBeGreaterThanOrEqual(11);
    expect(bounds.top).toBeGreaterThanOrEqual(11);
    expect(bounds.bottom).toBeGreaterThanOrEqual(11);
    expect(Math.abs(bounds.aspect - width / height)).toBeLessThan(.01);
    await page.screenshot({ path: testInfo.outputPath(`pwa-scroll-${name}-bounds.png`), animations: 'disabled' });
  });
  for (const style of ['single', 'scroll']) test(`image taps toggle immersive menus in ${style}`, async ({ page, context }) => {
    await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await prepare(page, context);
    if (style === 'single') {
      await page.request.put('/api/settings/roam', { data: { playback_style: 'single' } });
      await page.reload();
    }
    await page.locator('#roam-immersive').click();
    const card = page.locator('#image-card'), stage = card.locator('.image-stage');
    await expect(card).toHaveClass(/immersive/);
    await stage.tap();
    await expect(card).toHaveClass(/immersive-controls-hidden/);
    await expect(card.locator('.image-toolbar')).toHaveAttribute('aria-hidden', 'true');
    await stage.tap();
    await expect(card).not.toHaveClass(/immersive-controls-hidden/);
    await page.locator('#roam-immersive-privacy').tap();
    await expect(card).not.toHaveClass(/immersive-controls-hidden/);
    await stage.tap();
    await expect(card).toHaveClass(/immersive-controls-hidden/);
  });
  for (const immersive of [false, true]) test(`native swipes navigate Scroll smoothly and retain playback intent, immersive=${immersive}`, async ({ page, context, browserName }) => {
    test.skip(browserName !== 'chromium', 'Native touch injection uses the Chromium protocol.');
    await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await page.route(/\/static\/ui\/[^/]+\.css$/, async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: (await response.text()).replaceAll('(display-mode:standalone)', '(min-width:0px)').replaceAll('(display-mode:browser)', '(max-width:0px)') });
    });
    const { scroll, items } = await prepare(page, context);
    if (immersive) await page.locator('#roam-immersive').click();
    const session = await context.newCDPSession(page);
    const offset = () => scroll.evaluate(node => Number(node.dataset.offset));
    const swipe = async dx => {
      const box = await scroll.boundingBox();
      const x = box.x + box.width / 2, y = box.y + box.height / 2;
      // Hit the actual picture content, so its button participates in event targeting.
      expect(await page.evaluate(({ x, y }) => !!document.elementFromPoint(x, y)?.closest('.roam-scroll-picture'), { x, y })).toBe(true);
      await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let step = 1; step <= 5; step++) {
        await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx * step / 5, y }] });
      }
      await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    };

    const start = await offset();
    await swipe(-100);
    await expect(scroll).toHaveAttribute('data-moving', 'true');
    await expect.poll(offset).toBeLessThan(start - 1);
    await expect(scroll).toHaveAttribute('data-focus', items[1].id);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
    await swipe(100);
    await expect(scroll).toHaveAttribute('data-focus', items[0].id);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
    await expect(page.locator('#like')).toHaveAttribute('aria-pressed', 'false');

    // A native swipe must not synthesize a picture click that pauses autoplay.
    // Start through the retained button even when immersive controls are hidden.
    await page.locator('#roam-playback').evaluate(button => button.click());
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
    await swipe(-100);
    await expect(scroll).toHaveAttribute('data-focus', items[1].id);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');

    await page.keyboard.press('ArrowUp');
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('#like')).toBeEnabled();
    const likedId = await scroll.getAttribute('data-focus');
    const paused = await offset();
    await swipe(-100);
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'true');
    await expect(scroll).toHaveAttribute('data-moving', 'false');
    await expect(scroll).toHaveAttribute('data-focus', likedId);
    expect(paused - await offset()).toBeLessThan(25);

    // A short tap still pauses and focuses the picture.
    await scroll.tap();
    await expect(page.locator('#roam-playback')).toHaveAttribute('aria-pressed', 'false');
    await session.detach();
  });
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

test('switching focus does not stall the strip halfway through navigation', async ({ page, context }, testInfo) => {
  const { scroll } = await prepare(page, context, 4);
  const result = await scroll.evaluate(element => new Promise(resolve => {
    const photo = element.querySelector('[data-artifact-id]');
    const track = element.querySelector('.roam-scroll-track');
    const start = photo.getBoundingClientRect().left;
    const samples = [{ time: performance.now(), distance: 0 }];
    document.querySelector('#next').click();
    const animation = track.getAnimations()[0];
    let retainedAnimation = !!animation;
    // Page work must not make the strip depend on JavaScript painting every frame.
    setTimeout(() => { const until = performance.now() + 100; while (performance.now() < until) {} }, 60);
    const sample = time => {
      samples.push({ time, distance: start - photo.getBoundingClientRect().left });
      if (element.dataset.moving === 'true' && time - samples[0].time < 2000) {
        retainedAnimation &&= track.getAnimations()[0] === animation;
        requestAnimationFrame(sample);
      } else resolve({ samples, retainedAnimation });
    };
    requestAnimationFrame(sample);
  }));
  await testInfo.attach('scroll-motion-samples', { body: JSON.stringify(result), contentType: 'application/json' });
  expect(result.retainedAnimation, 'native animation survives focus updates and a busy main thread').toBe(true);
  const { samples } = result;
  const distance = samples.at(-1).distance;
  expect(distance).toBeGreaterThan(100);
  const velocities = samples.slice(1).map((sample, index) => ({
    previousProgress: samples[index].distance / distance,
    progress: sample.distance / distance,
    speed: (sample.distance - samples[index].distance) / (sample.time - samples[index].time),
  // The compositor can cross the midpoint while this deliberately busy main
  // thread cannot sample it. Include intervals spanning the middle region.
  })).filter(sample => sample.progress > .35 && sample.previousProgress < .65).map(sample => sample.speed);
  expect(velocities.length).toBeGreaterThanOrEqual(1);
  expect(Math.min(...velocities)).toBeGreaterThan(Math.max(...velocities) * .35);
});

test('retargeting a long scroll window never cancels the visible transform', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
  await page.route(/\/static\/ui\/[^/]+\.css$/, async route => {
    const response = await route.fetch();
    await route.fulfill({ response, body: (await response.text()).replaceAll('(display-mode:standalone)', '(min-width:0px)').replaceAll('(display-mode:browser)', '(max-width:0px)') });
  });
  const { scroll, items } = await prepare(page, context, 12);
  for (let index = 1; index <= 5; index++) {
    await page.keyboard.press('ArrowRight');
    await expect(scroll).toHaveAttribute('data-focus', items[index].id);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
  }
  await expect(scroll).toHaveAttribute('data-focus', items[5].id);
  await expect.poll(() => scroll.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
  const visibleError = () => scroll.evaluate(element => Math.abs(new DOMMatrix(getComputedStyle(element.querySelector('.roam-scroll-track')).transform).m41 - Number(element.dataset.offset)));
  await expect.poll(visibleError).toBeLessThan(1);
  await scroll.evaluate(element => {
    window.scrollNativeEffect = element.querySelector('.roam-scroll-track').getAnimations()[0];
    const original = Animation.prototype.cancel;
    window.scrollCancellationJumps = [];
    window.scrollCurveWrites = 0;
    const setKeyframes = KeyframeEffect.prototype.setKeyframes;
    KeyframeEffect.prototype.setKeyframes = function (...args) {
      if (this.target?.classList.contains('roam-scroll-track')) window.scrollCurveWrites++;
      return setKeyframes.apply(this, args);
    };
    Animation.prototype.cancel = function (...args) {
      const track = this.effect?.target;
      if (!track?.classList.contains('roam-scroll-track') || !track.isConnected) return original.apply(this, args);
      const before = new DOMMatrix(getComputedStyle(track).transform).m41;
      const result = original.apply(this, args);
      const after = new DOMMatrix(getComputedStyle(track).transform).m41;
      window.scrollCancellationJumps.push(Math.abs(after - before));
      return result;
    };
  });
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-moving', 'true');
  await page.waitForTimeout(120);
  await page.keyboard.press('ArrowRight');
  await expect(scroll).toHaveAttribute('data-focus', items[7].id);
  await expect(scroll).toHaveAttribute('data-moving', 'false');
  await expect.poll(visibleError).toBeLessThan(1);
  expect(await page.evaluate(() => window.scrollCancellationJumps.every(distance => distance < 1)), 'retargeting must not expose the previous inline transform').toBe(true);
  expect(await scroll.evaluate(element => element.querySelector('.roam-scroll-track').getAnimations()[0] === window.scrollNativeEffect), 'retargeting and settling must keep the same native effect').toBe(true);
  expect(await page.evaluate(() => window.scrollCurveWrites), 'only the two navigation commands should replace the curve').toBe(2);
});

test('autoplay crosses picture boundaries without rebasing the visible strip', async ({ page, context }) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 390, height: 520 });
  await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
  await page.route(/\/static\/ui\/[^/]+\.css$/, async route => {
    const response = await route.fetch();
    await route.fulfill({ response, body: (await response.text()).replaceAll('(display-mode:standalone)', '(min-width:0px)').replaceAll('(display-mode:browser)', '(max-width:0px)') });
  });
  await page.route(/\/api\/artifacts\/[^/]+\/image$/, route => route.fulfill({ contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="640" fill="#52796f"/></svg>' }));
  const { scroll, items } = await prepare(page, context, 12);
  for (let index = 1; index <= 5; index++) {
    await page.keyboard.press('ArrowRight');
    await expect(scroll).toHaveAttribute('data-focus', items[index].id);
    await expect(scroll).toHaveAttribute('data-moving', 'false');
  }
  await expect(scroll).toHaveAttribute('data-focus', items[5].id);
  await expect.poll(() => scroll.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth))).toBe(true);
  const samples = await scroll.evaluate((element, target) => new Promise(resolve => {
    const samples = [];
    document.querySelector('#roam-playback').click();
    const start = performance.now();
    const sample = () => {
      samples.push({ offset: Number(element.dataset.offset), origin: parseFloat(element.querySelector('[data-artifact-id]').style.left) || 0 });
      if (element.dataset.focus !== target && performance.now() - start < 15000) requestAnimationFrame(sample);
      else { document.querySelector('#roam-playback').click(); resolve(samples); }
    };
    requestAnimationFrame(sample);
  }), items[8].id);
  await expect(scroll).toHaveAttribute('data-focus', items[8].id);
  expect(samples.at(-1).origin).toBeGreaterThan(samples[0].origin);
  expect(Math.max(...samples.slice(1).map((frame, index) => frame.offset - samples[index].offset))).toBeLessThan(1);
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
  const offsetBeforeCleanup = await scroll.getAttribute('data-offset');
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
  expect(Number(await scroll.getAttribute('data-offset'))).toBeCloseTo(Number(offsetBeforeCleanup), 4);
  await page.locator('.roam-anchor-term').filter({ hasText: 'scroll anchor fixture' }).click({ button: 'right' });
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).excluded_positive).toContain('scroll anchor fixture');
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
  await page.getByRole('button', { name: 'Clear anchors', exact: true }).click();
  await expect.poll(async () => (await (await page.request.get('/api/settings/roam')).json()).excluded_positive).toEqual([]);
  await expect(scroll).toHaveAttribute('data-focus', items[2].id);
});
