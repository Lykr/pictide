import { test as base, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
export const test = base.extend({
  server: [async ({}, use) => {
    const child = spawn(process.env.PICTIDE_TEST_PYTHON || 'python', ['tests/browser_server.py'], {
      cwd: root, stdio: ['pipe', 'pipe', 'pipe'],
    });
    let diagnostics = '';
    child.stderr.on('data', chunk => { diagnostics = (diagnostics + chunk).slice(-12000); });
    const exited = new Promise(resolve => child.once('close', code => resolve(code)));
    try {
      const server = await new Promise((resolve, reject) => {
        const lines = createInterface({ input: child.stdout });
        const timeout = setTimeout(() => reject(new Error('Browser fixture startup timed out\n' + diagnostics)), 20000);
        lines.once('line', line => {
          clearTimeout(timeout);
          try { resolve(JSON.parse(line)); } catch { reject(new Error('Invalid fixture output: ' + line)); }
        });
        child.once('error', error => { diagnostics += error.message; clearTimeout(timeout); reject(error); });
        child.once('exit', code => { clearTimeout(timeout); reject(new Error(`Fixture exited (${code})\n${diagnostics}`)); });
      });
      await use(server);
    } finally {
      child.stdin?.end();
      const timeout = setTimeout(() => child.kill(), 10000);
      const code = await exited;
      clearTimeout(timeout);
      if (code !== 0) throw new Error(`Browser fixture failed (${code})\n${diagnostics}`);
    }
  }, { scope: 'test' }],
  baseURL: async ({ server }, use) => use(server.url),
  page: async ({ page }, use) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await use(page);
    expect(errors, 'browser JavaScript errors').toEqual([]);
  },
});
export { expect };
