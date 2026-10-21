import { test, expect } from './fixtures.mjs';

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
  await expect(page.getByText('Version v0.5.1 is available', { exact: true })).toBeVisible();
  expect(actions).toEqual(['check']);
  await page.getByRole('button', { name: 'Download update', exact: true }).click();
  await page.getByRole('button', { name: 'Install and restart', exact: true }).click();
  await expect(page.locator('.notification-card')).toContainText('Save your changes before installing the update.');
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
  await expect(page.getByText('Update source deployments manually.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Release notes', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download update', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await expect(page.locator('.notification-card')).toContainText('Update source is unavailable');
  expect(checked).toBe(2);
});
