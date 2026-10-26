import { test, expect } from './fixtures.mjs';

const initial = () => ({ can_configure: true,
  config: { enabled: false, backend_id: '', install_dir: '', python: '', entry: '', cwd: '', args: [] },
  choices: [{ id: 'fixture', name: 'Local ComfyUI', base_url: 'http://127.0.0.1:8188' }],
  status: { phase: 'disabled', owned: false, error: '', url: null, log_path: 'C:/Pictide data/logs/comfyui.log' }, restart_required: false });
const candidate = { install_dir: 'C:/Comfy UI 中文', python: 'C:/Comfy UI 中文/.venv/Scripts/python.exe',
  entry: 'C:/Comfy UI 中文/main.py', cwd: 'C:/Comfy UI 中文', args: ['--enable-manager', '--output-directory', 'E:/Images with spaces'] };

for (const width of [1365, 390]) {
  test(`ComfyUI startup settings preserve drafts and only save explicitly at ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
    let settings = initial(), writes = 0, detects = 0;
    await page.route('**/api/settings/local-generation**', route => {
      if (route.request().url().endsWith('/detect')) { detects++; return route.fulfill({ json: { candidates: [candidate] } }); }
      if (route.request().method() === 'PUT') {
        writes++;
        const payload = route.request().postDataJSON();
        expect(payload.args).toEqual(candidate.args);
        settings = { ...settings, config: payload, restart_required: true };
      }
      return route.fulfill({ json: settings });
    });
    await page.goto('/#settings/general');
    const section = page.locator('.local-generation-settings');
    const enabled = section.getByRole('checkbox', { name: 'Start and stop with Pictide', exact: true });
    await expect(enabled).not.toBeChecked();
    await enabled.check();
    await section.getByRole('button', { name: 'Detect installation', exact: true }).click();
    await expect(section.locator('#local-generation-path')).toHaveValue(candidate.install_dir);
    expect(detects).toBe(1); expect(writes).toBe(0);
    await section.getByRole('button', { name: 'Advanced startup settings', exact: true }).click();
    await expect(section.locator('#local-generation-python')).toHaveValue(candidate.python);
    await expect(section.locator('#local-generation-args')).toHaveValue(candidate.args.join('\n'));
    await page.getByRole('tab', { name: 'Image API', exact: true }).click();
    await page.getByRole('tab', { name: 'General', exact: true }).click();
    await expect(section.locator('#local-generation-path')).toHaveValue(candidate.install_dir);
    await expect(section.locator('#local-generation-args')).toHaveValue(candidate.args.join('\n'));
    await section.getByRole('button', { name: 'Save startup settings', exact: true }).click();
    expect(writes).toBe(1);
    await expect(section.getByRole('button', { name: 'Save startup settings', exact: true })).toBeDisabled();
    await expect(section.getByRole('status')).toContainText('Changes apply the next time Pictide starts.');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`local-generation-${width}.png`), fullPage: true });
    await info.attach('local-generation-settings', { path: info.outputPath(`local-generation-${width}.png`), contentType: 'image/png' });
  });
}

test('multiple ComfyUI candidates require selection and failed saves keep the edited path', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  const second = { ...candidate, install_dir: 'D:/' + 'Long folder name '.repeat(16) + '/ComfyUI', python: 'D:/Other/python.exe' };
  await page.route('**/api/settings/local-generation**', route => {
    if (route.request().url().endsWith('/detect')) return route.fulfill({ json: { candidates: [candidate, second] } });
    if (route.request().method() === 'PUT') return route.fulfill({ status: 400, json: { error: 'The Python interpreter is missing' } });
    return route.fulfill({ json: initial() });
  });
  await page.goto('/#settings/general');
  const section = page.locator('.local-generation-settings');
  await section.getByRole('checkbox', { name: 'Start and stop with Pictide', exact: true }).check();
  await section.getByRole('button', { name: 'Detect installation', exact: true }).click();
  await expect(section.locator('#local-generation-path')).toHaveValue('');
  await section.getByRole('combobox', { name: 'Choose a detected installation', exact: true }).click();
  const option = page.getByRole('option', { name: second.install_dir, exact: true });
  await expect(option).toBeVisible();
  const box = await page.getByRole('listbox').boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
  await option.click();
  await expect(section.locator('#local-generation-path')).toHaveValue(second.install_dir);
  await section.getByRole('button', { name: 'Save startup settings', exact: true }).click();
  await expect(page.locator('.notification-card[data-state="open"]')).toContainText('The Python interpreter is missing');
  await expect(section.locator('#local-generation-path')).toHaveValue(second.install_dir);
  await expect(section.getByRole('button', { name: 'Save startup settings', exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('LAN view explains host-only configuration and startup failure exposes its log path', async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  let local = false;
  await page.route('**/api/settings/local-generation', route => route.fulfill({ json: local ? {
    ...initial(), status: { phase: 'failed', owned: false, error: 'ComfyUI could not start; see logs/comfyui.log', log_path: 'C:/Pictide/logs/comfyui.log' },
  } : { can_configure: false } }));
  await page.goto('/#settings/general');
  const section = page.locator('.local-generation-settings');
  await expect(section).toContainText('Configure this using localhost on the computer running Pictide.');
  await expect(section.getByRole('checkbox')).toHaveCount(0);
  local = true;
  await page.reload();
  await expect(section.locator('[data-local-generation-status]')).toContainText('ComfyUI startup failed');
  await expect(section).toContainText('C:/Pictide/logs/comfyui.log');
});


test('Chinese dark startup settings support keyboard and long paths on phones', async ({ page, context }, info) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await context.addInitScript(() => localStorage.setItem('pictide.first-run-guide.v1', JSON.stringify({ version: 1, status: 'dismissed' })));
  await page.request.put('/api/settings/general', { data: { language: 'zh-CN', theme: 'dark' } });
  await page.route('**/api/settings/local-generation**', route => route.fulfill({ json: route.request().url().endsWith('/detect') ? { candidates: [candidate] } : initial() }));
  await page.goto('/#settings/general');
  const section = page.locator('.local-generation-settings');
  const enabled = section.getByRole('checkbox', { name: '跟随 Pictide 启动和退出', exact: true });
  await enabled.focus(); await page.keyboard.press('Space');
  await expect(enabled).toBeChecked();
  expect((await section.locator('label[for=local-generation-enabled]').boundingBox()).height).toBeGreaterThanOrEqual(44);
  await section.getByRole('button', { name: '自动识别', exact: true }).click();
  await expect(section.locator('#local-generation-path')).toHaveValue(candidate.install_dir);
  await section.evaluate(element => element.scrollIntoView({ block: 'start' }));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('html')).toHaveClass(/dark/);
  const path = info.outputPath('local-generation-zh-dark.png');
  await page.screenshot({ path, fullPage: true });
  await info.attach('Chinese dark startup settings', { path, contentType: 'image/png' });
});
