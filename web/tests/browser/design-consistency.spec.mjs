import { test, expect } from './fixtures.mjs';

async function prepare(page, context, width = 390) {
  await page.setViewportSize({ width, height: 844 });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'en', theme: 'light' } });
}

for (const width of [320, 390]) test(`settings keep the active tab visible and generation actions readable at ${width}px`, async ({ page, context }) => {
  await prepare(page, context, width);
  await page.goto('/#settings/user-data');
  const list = page.getByRole('tablist', { name: 'Settings categories' });
  const active = page.getByRole('tab', { name: 'User data', exact: true });
  await expect(active).toHaveAttribute('data-state', 'active');
  await expect.poll(async () => {
    const frame = await list.boundingBox(), tab = await active.boundingBox();
    return tab.x >= frame.x && tab.x + tab.width <= frame.x + frame.width + 1;
  }).toBe(true);
  await page.setViewportSize({ width: width - 20, height: 844 });
  await expect.poll(async () => {
    const frame = await list.boundingBox(), tab = await active.boundingBox();
    return tab.x + tab.width <= frame.x + frame.width + 1;
  }).toBe(true);
  await active.focus();
  await page.keyboard.press('Home');
  await expect(page.getByRole('tab', { name: 'General', exact: true })).toBeFocused();
  await page.locator('[data-view=generate]').click();
  for (const button of await page.locator('.generation-actions button').all()) {
    const fits = await button.evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const content = range.getBoundingClientRect(), bounds = element.getBoundingClientRect();
      return content.left >= bounds.left && content.right <= bounds.right + 1;
    });
    expect(fits, 'the complete action label fits its button').toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('prompt field labels focus the editable control and preserve drafts across sections', async ({ page, context }) => {
  await prepare(page, context);
  await page.goto('/#prompts');
  await page.getByRole('tab', { name: 'Arrange', exact: true }).click();
  await page.locator('label[for=cooc-min_tags]').click();
  await expect(page.locator('#cooc-min_tags')).toBeFocused();
  await page.locator('#cooc-min_tags').fill('3');
  await page.locator('label[for=cooc-blocked-keywords]').click();
  await expect(page.locator('#cooc-blocked-keywords')).toBeFocused();
  await page.keyboard.type('test term');
  await page.getByRole('tab', { name: 'Preview', exact: true }).click();
  await page.locator('label[for=cooc-preview-mode]').click();
  await expect(page.getByRole('listbox')).toBeVisible();
  await page.getByRole('option', { name: 'Fixed seed', exact: true }).click();
  await page.locator('label[for=cooc-preview-seed]').click();
  await expect(page.locator('#cooc-preview-seed')).toBeFocused();
  await page.locator('[data-view=generate]').click();
  await page.locator('[data-view=prompts]').click();
  await page.getByRole('tab', { name: 'Arrange', exact: true }).click();
  await expect(page.locator('#cooc-min_tags')).toHaveValue('3');
  await expect(page.locator('#cooc-blocked-keywords')).toHaveValue('test term');
});

test('connection progress stays at the action and a stale result asks for a new test', async ({ page, context }) => {
  await prepare(page, context, 1365);
  await page.goto('/#settings/backend');
  await expect(page.locator('#backend-name')).toHaveValue('Browser fixture');
  let finish, held;
  const arrived = new Promise(resolve => { finish = resolve; });
  await page.route('**/api/backends/*/check', route => { held = route; finish(); });
  const testButton = page.getByRole('button', { name: 'Test connection', exact: true });
  await testButton.scrollIntoViewIfNeeded();
  const before = await testButton.boundingBox();
  await testButton.click();
  await arrived;
  await expect(testButton).toHaveAttribute('aria-busy', 'true');
  await expect(testButton).toBeDisabled();
  await expect(page.locator('.notification-card[data-state=open]')).toHaveCount(0);
  expect(await testButton.boundingBox()).toEqual(before);
  await page.locator('#backend-url').fill('http://127.0.0.1:9999');
  await held.fulfill({ json: { ok: true, message: 'Old connection succeeded' } });
  await expect(testButton).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.notification-card[data-state=open]')).toContainText('Test the connection again');
  await expect(page.locator('#backend-url')).toHaveValue('http://127.0.0.1:9999');
  await expect(page.locator('#backend-url')).toBeFocused();
  await expect(page.locator('.notification-card[data-state=open]')).not.toContainText('Old connection succeeded');
});

for (const section of ['llm', 'canvas']) test(`${section} saving indicates the actual pending action and keeps the draft`, async ({ page, context }) => {
  await prepare(page, context);
  await page.goto(`/#settings/${section}`);
  const name = section === 'llm' ? page.locator('#llm-name') : page.locator('#canvas-pool-name');
  await name.fill('Retained configuration');
  if (section === 'llm') {
    await page.locator('#prompt-api-url').fill('https://example.invalid/v1');
    await page.locator('#prompt-api-model').fill('fixture');
  }
  let finish, held;
  const arrived = new Promise(resolve => { finish = resolve; });
  await page.route(section === 'llm' ? /\/api\/llm-apis\/[^/]+$/ : /\/api\/canvas-pools\/[^/]+$/, route => {
    if (route.request().method() !== 'PUT') return route.continue();
    held = route; finish();
  });
  const save = page.getByRole('button', { name: section === 'llm' ? 'Save LLM API' : 'Save canvas pool', exact: true });
  await save.click();
  await arrived;
  await expect(save).toHaveAttribute('aria-busy', 'true');
  await expect(save).toBeDisabled();
  await expect(name).toHaveValue('Retained configuration');
  await held.fulfill({ response: await held.fetch() });
  await expect(save).toHaveAttribute('aria-busy', 'false');
  await expect(name).toHaveValue('Retained configuration');
});

test('prompt preview shows progress without claiming the preset is being saved', async ({ page, context }) => {
  await prepare(page, context, 1365);
  await page.goto('/#prompts');
  await page.getByRole('tab', { name: 'Preview', exact: true }).click();
  const preview = page.getByRole('button', { name: 'Preview', exact: true });
  await expect(preview).toBeEnabled();
  let finish, held;
  const arrived = new Promise(resolve => { finish = resolve; });
  await page.route('**/api/candidate/generate', route => { held = route; finish(); });
  await preview.click(); await arrived;
  await expect(preview).toHaveAttribute('aria-busy', 'true');
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveAttribute('aria-busy', 'false');
  await held.fulfill({ response: await held.fetch() });
  await expect(preview).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.cooc-preview-results')).toBeVisible();
});
