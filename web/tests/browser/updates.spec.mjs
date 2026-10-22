import { test, expect } from './fixtures.mjs';

test('update-check notices preserve layout and only appear after explicit checks', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await context.addInitScript(() => {
    const NativeEvents = window.EventSource;
    window.EventSource = class extends NativeEvents { constructor(...args) { super(...args); window.testEvents = this; } };
  });
  let checks = 0, reads = 0;
  let status = { current_version: '0.5.0', latest_version: '0.5.0', phase: 'current', reason: 'already_current',
    can_download: false, can_install: false, release_url: 'https://github.com/Lykr/pictide/releases', error: null };
  await page.route('**/api/updates**', route => {
    if (route.request().method() === 'POST') {
      checks++;
      if (checks === 3) return route.fulfill({ status: 503, json: { error: 'Update check failed' } });
      status = { ...status, latest_version: checks === 2 ? '0.4.9' : '0.5.0' };
    } else reads++;
    return route.fulfill({ json: status });
  });
  await page.goto('/#settings/general');
  const check = page.getByRole('button', { name: 'Check for updates', exact: true });
  const notice = page.locator('.notification-card[data-state="open"]');
  await expect(check).toBeEnabled();
  await page.evaluate(() => document.fonts.ready);
  const settings = page.locator('.general-settings');
  const before = await settings.boundingBox();
  const scroll = await page.evaluate(() => scrollY);
  await expect(notice).toHaveCount(0);
  expect(checks).toBe(0);
  for (let index = 0; index < 2; index++) {
    await check.click();
    await expect(notice).toContainText("You're up to date.");
    await expect(notice).toHaveAttribute('data-kind', 'success');
    await expect.poll(() => settings.boundingBox()).toEqual(before);
    expect(await page.evaluate(() => scrollY)).toBe(scroll);
    await expect(page.locator('.notification-layer :focus')).toHaveCount(0);
    const position = await notice.boundingBox();
    expect(position.y).toBeLessThanOrEqual(32);
    expect(position.x).toBeGreaterThan(900);
    await notice.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
    await expect(notice).toHaveCount(0);
    const previousReads = reads;
    await page.evaluate(() => window.testEvents.dispatchEvent(new MessageEvent('change', { data: JSON.stringify({ topic: 'updates' }) })));
    await expect.poll(() => reads).toBeGreaterThan(previousReads);
    await expect(notice).toHaveCount(0);
  }
  await check.click();
  await expect(notice).toContainText('Update check failed');
  await expect.poll(() => settings.boundingBox()).toEqual(before);
  expect(checks).toBe(3);
});

test('updates require explicit actions and protect unsaved drafts before installation', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  let status = { current_version: '0.5.0', latest_version: null, phase: 'idle', reason: '', can_download: false,
    can_install: false, release_url: 'https://github.com/Lykr/pictide/releases/tag/v0.5.1', downloaded_bytes: 0, total_bytes: 100, error: null };
  const actions = [];
  await page.route('**/api/updates**', route => {
    const action = new URL(route.request().url()).pathname.split('/')[3];
    if (route.request().method() === 'POST') {
      actions.push(action);
      if (action === 'check') status = { ...status, latest_version: '0.5.1', phase: 'checked', can_download: true };
      if (action === 'download') status = { ...status, phase: 'ready', can_install: true };
      if (action === 'install') status = { ...status, phase: 'installing', can_install: false };
    } else if (status.phase === 'installing') status = { ...status, current_version: '0.5.1', phase: 'installed' };
    return route.fulfill({ json: status });
  });
  await page.goto('/#settings/general');
  await expect(page.getByRole('button', { name: 'Check for updates', exact: true })).toBeEnabled();
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).not.toHaveValue('');
  const savedName = await page.locator('#backend-name').inputValue();
  await page.locator('#backend-name').fill('Unsaved API draft');
  await page.goto('/#settings/general');
  expect(actions).toEqual([]);
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toContainText('Version v0.5.1 is available');
  expect(actions).toEqual(['check']);
  await page.getByRole('button', { name: 'Download update', exact: true }).click();
  await page.getByRole('button', { name: 'Install and restart', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toContainText('Save your changes before installing the update.');
  expect(actions).toEqual(['check', 'download']);
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).toHaveValue('Unsaved API draft');
  await page.locator('#backend-name').fill(savedName);
  await page.locator('#save-backend').click();
  await expect(page.locator('#save-backend')).toBeEnabled();
  await page.goto('/#settings/general');
  await page.getByRole('button', { name: 'Install and restart', exact: true }).click();
  await expect(page.getByRole('alertdialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(actions).toEqual(['check', 'download']);
  await page.getByRole('button', { name: 'Install and restart', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByText('Pictide v0.5.1', { exact: true })).toBeVisible();
  expect(actions).toEqual(['check', 'download', 'install']);
});

test('mobile manual-update result fits and failures remain floating notifications', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  let checked = 0;
  let status = { current_version: '0.5.0', latest_version: null, phase: 'idle', reason: 'source_installation',
    can_download: false, can_install: false, release_url: 'https://github.com/Lykr/pictide/releases', error: null };
  await page.route('**/api/updates**', route => {
    if (route.request().method() === 'POST') {
      checked++;
      if (checked === 2) return route.fulfill({ status: 503, json: { error: 'Update source is unavailable' } });
      status = { ...status, latest_version: '0.5.1', phase: 'checked' };
    }
    return route.fulfill({ json: status });
  });
  await page.goto('/#settings/general');
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toContainText('Update source deployments manually.');
  await expect(page.getByRole('link', { name: 'Release notes', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download update', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toContainText('Update source is unavailable');
  expect(checked).toBe(2);
});

test('failed restart stops polling and shows a log hint without resubmitting actions', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.clock.install();
  let phase = 'idle';
  let reads = 0;
  const actions = [];
  await page.route('**/api/updates**', route => {
    const action = new URL(route.request().url()).pathname.split('/')[3];
    if (route.request().method() === 'POST') {
      actions.push(action);
      phase = action === 'check' ? 'checked' : action === 'download' ? 'ready' : 'installing';
    } else {
      reads++;
      if (phase === 'installing') return route.fulfill({ status: 503, json: { error: 'Service unavailable' } });
    }
    return route.fulfill({ json: { current_version: '0.5.0', latest_version: phase === 'idle' ? null : '0.5.1',
      phase, reason: '', can_download: phase === 'checked', can_install: phase === 'ready',
      downloaded_bytes: 100, total_bytes: 100, error: null } });
  });
  await page.goto('/#settings/general');
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await page.getByRole('button', { name: 'Download update', exact: true }).click();
  await page.getByRole('button', { name: 'Install and restart', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByText('Installing. Pictide will restart…', { exact: true })).toBeVisible();
  await page.clock.fastForward(125000);
  await expect(page.locator('.notification-card')).toContainText('Could not reconnect to Pictide.');
  await expect(page.getByText('Installing. Pictide will restart…', { exact: true })).toHaveCount(0);
  const finishedReads = reads;
  await page.clock.fastForward(30000);
  expect(reads).toBe(finishedReads);
  expect(actions).toEqual(['check', 'download', 'install']);
});
