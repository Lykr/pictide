import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../', import.meta.url));
const [group = 'ui', ...options] = process.argv.slice(2);
if (!['ui', 'browser'].includes(group) || options.some(option => option !== '--list')) {
  throw new Error('Usage: node web/scripts/test.mjs [ui|browser] [--list]');
}
const files = ['onboarding', 'onboarding-placement', 'button-feedback', 'notifications', 'theme', 'settings-controls', 'request-id']
  .map(name => resolve(root, `web/tests/unit/${name}.test.mjs`));
let command;
if (group === 'ui') {
  if (options.includes('--list')) { console.log(files.join('\n')); process.exit(0); }
  command = ['--test', ...files];
} else {
  const require = createRequire(resolve(root, 'dev/runtime/frontend/package.json'));
  command = [require.resolve('@playwright/test/cli'), 'test', '--config', resolve(root, 'web/playwright.config.mjs'), ...options];
}
const result = spawnSync(process.execPath, command, { cwd: root, stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
