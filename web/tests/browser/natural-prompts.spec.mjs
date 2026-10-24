import { test, expect } from './fixtures.mjs';

for (const width of [1365, 390]) {
  test(`natural-language API configuration and read-only preview at ${width}px`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
    await page.goto('/#settings/backend');
    await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
    await page.locator('#backend-prompt-type').click();
    await page.getByRole('option', { name: 'Natural language', exact: true }).click();
    await page.locator('#save-backend').click();
    await expect(page.locator('#save-backend')).toBeEnabled();
    await page.getByRole('button', { name: 'Prompt LLM API', exact: true }).click();
    await page.locator('#prompt-api-url').fill('http://127.0.0.1:1/v1');
    await page.locator('#prompt-api-model').fill('fixture-text');
    await page.locator('#prompt-api-key').fill('test-text-secret');
    await page.getByRole('button', { name: 'Save prompt service', exact: true }).click();
    await expect(page.locator('#prompt-api-key')).toHaveValue('••••••••');
    await page.goto('/#prompts');
    await page.getByRole('tab', { name: 'Preview', exact: true }).click();
    await page.getByRole('combobox', { name: 'Preview image API' }).click();
    await page.getByRole('option', { name: 'Browser fixture', exact: true }).click();
    await page.getByRole('button', { name: 'Preview', exact: true }).click();
    await expect(page.locator('.cooc-preview-results')).toContainText('A quiet garden under a blue sky.');
    expect(await page.locator('.cooc-preview-results textarea').count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('heading', { name: 'Natural-language prompt', exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `dev/verification/browser/natural-preview-${width}.png`, fullPage: true });
    await page.goto('/#generate');
    await page.locator('#positive').fill('garden, blue sky');
    const submitted = page.waitForResponse(response => response.url().endsWith('/api/jobs') && response.request().method() === 'POST');
    await page.locator('#generate').click();
    const response = await submitted;
    expect(response.status()).toBe(202);
    const result = await response.json();
    expect(result.job.positive).toBe('A quiet garden under a blue sky.');
    expect(result.job.source_prompts.positive).toBe('garden, blue sky');
    await expect(page.locator('#generate-form')).toContainText('A quiet garden under a blue sky.');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
