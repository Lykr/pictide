import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const directory = path => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  testDir: directory('./tests/browser'),
  outputDir: directory('../dev/verification/browser/artifacts'),
  workers: 1,
  retries: 0,
  timeout: 30000,
  expect: { timeout: 10000 },
  reporter: [['list'], ['json', { outputFile: directory('../dev/verification/browser/results.json') }]],
  use: {
    browserName: 'chromium',
    channel: process.env.PICTIDE_TEST_BROWSER_CHANNEL || undefined,
    locale: 'en-US',
    viewport: { width: 1365, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
