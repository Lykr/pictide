import { test, expect } from './fixtures.mjs';

async function prepare(page, context) {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.addInitScript(() => localStorage.setItem(
    'pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN', theme: 'light' } });
}

test('user data owns migration, preferences, cleanup, and data location', async ({ page, context }) => {
  await prepare(page, context);
  await page.goto('/#settings/user-data');
  await expect(page.getByRole('tab', { name: '用户数据', exact: true })).toHaveAttribute('data-state', 'active');
  await expect(page.locator('#settings-user-data')).toBeVisible();
  await expect(page.locator('#data-directory')).toHaveText(/.+/);
  await expect(page.getByRole('button', { name: '导出用户数据', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '导入用户数据', exact: true })).toBeEnabled();
  await expect(page.getByText('用户偏好', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '图片清理', exact: true })).toBeVisible();
  await expect(page.locator('#settings-general')).toBeHidden();
  await expect(page.locator('#settings-history')).toBeHidden();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出用户数据', exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/^pictide-user-data-\d{8}T\d{6}\.zip$/);
});

test('user data import confirms replacement and reports validated counts', async ({ page, context }) => {
  await prepare(page, context);
  await page.route('**/api/user-data/import', route => route.fulfill({
    json: {
      liked_imported: 3, liked_skipped: 1, preference_evidence: 9,
      backup: 'backups/before-user-data-import/test/pictide.sqlite3', artifact_revision: 12,
    },
  }));
  await page.goto('/#settings/user-data');
  const response = page.waitForResponse(item => item.url().endsWith('/api/user-data/import'));
  await page.locator('#user-data-file').setInputFiles({
    name: 'pictide-user-data.zip', mimeType: 'application/zip', buffer: Buffer.from('zip'),
  });
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toContainText('替换当前学习偏好');
  await dialog.getByRole('button', { name: '确认', exact: true }).click();
  expect((await response).status()).toBe(200);
  await expect(page.locator('.notification-card[data-state=open]')).toContainText(
    '已导入 3 张喜欢图片和 9 条偏好证据');
});
