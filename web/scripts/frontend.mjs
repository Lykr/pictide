import { existsSync, mkdirSync, symlinkSync, copyFileSync, lstatSync, readdirSync, rmdirSync, renameSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

const root = fileURLToPath(new URL('../', import.meta.url));
const devRoot = resolve(root, '../dev');
const modules = resolve(devRoot, 'runtime/frontend/node_modules');
if (!existsSync(modules)) throw new Error('请先执行 pnpm install --frozen-lockfile。');
// Module resolvers use this link; the dependency files stay under dev/.
const link = resolve(root, 'node_modules');
if (existsSync(link) && !lstatSync(link).isSymbolicLink()) {
  const metadata = resolve(link, '.pnpm-workspace-state-v1.json');
  if (existsSync(metadata)) {
    mkdirSync(resolve(devRoot, 'cache/pnpm'), { recursive: true });
    renameSync(metadata, resolve(devRoot, 'cache/pnpm/root-workspace-state.json'));
  }
  if (readdirSync(link).length) throw new Error('根 node_modules 不是 dev 目录链接，请先移走旧前端依赖。');
  rmdirSync(link);
}
if (!existsSync(link)) symlinkSync(modules, link, 'junction');
const require = createRequire(resolve(root, 'package.json'));
const command = process.argv[2];
if (command === 'build') {
  const { build } = await import(pathToFileURL(require.resolve('vite')).href);
  await build({ root, configFile: resolve(root, 'vite.config.ts') });
  copyFileSync(resolve(root, 'src/THIRD_PARTY_NOTICES.md'), resolve(root, 'dist/THIRD_PARTY_NOTICES.md'));
} else if (command === 'typecheck') {
  mkdirSync(resolve(devRoot, 'cache/typescript'), { recursive: true });
  const result = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), '--noEmit', '-p', resolve(root, 'tsconfig.json')], { cwd: root, stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
} else throw new Error('Usage: node scripts/frontend.mjs build|typecheck');
