import { test, expect } from './fixtures.mjs';

for (const scenario of [{width: 1365, language: 'en'}, {width: 390, language: 'zh-CN'}]) {
  test(`pixel pool editing, API reuse and Roam selection at ${scenario.width}px`, async ({page, context}, testInfo) => {
    await page.setViewportSize({width: scenario.width, height: 900});
    await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({version: 1, status: 'dismissed'})));
    await page.request.put('/api/settings/general', {data: {theme: 'dark', language: scenario.language}});
    await page.goto('/#settings/canvas');
    await expect(page.locator('#canvas-pool-name')).toBeVisible();
    await page.locator('#canvas-pool-name').fill('Common');
    await expect(page.locator('#canvas-pool-sizes button').last()).toBeDisabled();
    const add = page.locator('#canvas-pool-form button').filter({hasText: scenario.language === 'en' ? 'Add size' : '添加尺寸'});
    await add.click();
    await page.locator('[data-canvas-size]').nth(1).getByRole('spinbutton').nth(0).fill('768');
    await page.locator('[data-canvas-size]').nth(1).getByRole('spinbutton').nth(1).fill('1024');
    const saved = page.waitForResponse(response => /\/api\/canvas-pools\/[^/]+$/.test(response.url()) && response.request().method() === 'PUT');
    await page.locator('#save-canvas-pool').click();
    const response = await saved;
    expect(response.ok()).toBe(true);
    const pool = (await response.json())[0];
    expect(pool.sizes).toEqual([{width: 1024, height: 1024}, {width: 768, height: 1024}]);
    await expect(page.locator('#save-canvas-pool')).toBeDisabled();
    const widthInput = page.locator('[data-canvas-size]').first().getByRole('spinbutton').first();
    await widthInput.focus();
    const catalogRefresh = page.waitForResponse(response => response.url().endsWith('/api/canvas-pools') && response.request().method() === 'GET');
    expect((await page.request.put('/api/canvas-pools/unused', {data: {name: 'Unused', sizes: [{width: 1024, height: 1024}]}})).ok()).toBe(true);
    await catalogRefresh;
    await expect(widthInput).toBeFocused();
    await page.locator('#canvas-pool-name').fill('Unsaved draft');
    await page.locator('[data-settings-section=backend]').click();
    await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
    await page.locator('#backend-canvas-pool').click();
    await page.getByRole('option', {name: 'Common', exact: true}).click();
    await page.locator('#toggle-node-parameters').click();
    await page.locator('#toggle-workflow-json').click();
    const workflow = JSON.parse(await page.locator('#workflow-json').inputValue());
    workflow['4'] = {class_type: 'EmptyLatentImage', inputs: {width: 832, height: 1216, batch_size: 1}};
    await page.locator('#workflow-json').fill(JSON.stringify(workflow));
    await page.locator('#toggle-workflow-json').click();
    for (const dimension of ['width', 'height']) {
      await page.locator('#binding-' + dimension).click();
      await page.getByRole('option', {name: `4 · EmptyLatentImage → ${dimension}`, exact: true}).click();
    }
    const apiSaved = page.waitForResponse(response => response.url().endsWith('/api/backends/fixture') && response.request().method() === 'PUT');
    await page.locator('#save-backend').click();
    expect((await apiSaved).ok()).toBe(true);
    await expect(page.locator('#save-backend')).toBeEnabled();
    for (const section of ['backend', 'roam']) {
      await page.locator(`[data-settings-section=${section}]`).click();
      await page.locator(section === 'backend' ? '#backend-canvas-pool' : '#roam-canvas-mode').scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const screenshot = testInfo.outputPath(section + '.png');
      await page.screenshot({path: screenshot, fullPage: true});
      await testInfo.attach(section, {path: screenshot, contentType: 'image/png'});
    }
    await page.locator('[data-settings-section=canvas]').click();
    await expect(page.locator('#canvas-pool-name')).toHaveValue('Unsaved draft');
    await page.locator('[data-settings-section=roam]').click();
    await page.locator('#roam-canvas-mode').click();
    await page.getByRole('option', {name: scenario.language === 'en' ? 'Fixed API size' : 'API 固定尺寸', exact: true}).click();
    const roamSaved = page.waitForResponse(response => response.url().endsWith('/api/settings/roam') && response.request().method() === 'PUT');
    await page.locator('#roam-save').click();
    expect((await (await roamSaved).json()).use_canvas_pool).toBe(false);
    await page.reload();
    await expect(page.locator('#roam-canvas-mode')).toContainText(scenario.language === 'en' ? 'Fixed API size' : 'API 固定尺寸');
    await page.locator('[data-settings-section=canvas]').click();
    await expect(page.locator('#canvas-pool-name')).toHaveValue('Common');
    await expect(page.locator('[data-canvas-size]')).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const image = testInfo.outputPath('canvas-pools.png');
    await page.screenshot({path: image, fullPage: true});
    await testInfo.attach('canvas-pools', {path: image, contentType: 'image/png'});
    const deleteButton = page.locator('#canvas-pool-form .settings-field-heading button');
    await deleteButton.click();
    await page.getByRole('button', {name: scenario.language === 'en' ? 'Confirm' : '确认', exact: true}).click();
    await expect(page.locator('.notification-card[data-state=open]')).toContainText(scenario.language === 'en' ? 'used by an image API' : '此画幅池正被生图 API 使用');
    await expect(page.locator('#canvas-pool-name')).toHaveValue('Common');
  });
}
