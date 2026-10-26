import test from 'node:test';
import assert from 'node:assert/strict';
import { createLocalGeneration } from '../../src/controllers/local-generation.js';

const config = { enabled: false, backend_id: '', install_dir: '', python: '', entry: '', cwd: '', args: [] };
const response = () => ({ can_configure: true, config: { ...config }, choices: [{ id: 'local', name: 'Local' }],
  status: { phase: 'disabled', error: '' }, restart_required: false });
const candidate = { install_dir: 'C:/Comfy UI', python: 'C:/Comfy UI/python.exe', entry: 'C:/Comfy UI/main.py',
  cwd: 'C:/Comfy UI', args: ['--cpu', '--output-directory', 'C:/Images with spaces'], source: 'desktop' };

test('discovery only fills an editable draft and saving sends arguments as distinct values', async () => {
  const writes = [];
  const service = createLocalGeneration(async (path, options) => {
    if (path.endsWith('/detect')) return { candidates: [candidate] };
    if (options?.method === 'PUT') { const data = JSON.parse(options.body); writes.push(data); return { ...response(), config: data, restart_required: true }; }
    return response();
  });
  await service.load();
  service.edit('enabled', true);
  assert.equal(service.model.data.draft.backend_id, 'local');
  await service.detect();
  assert.equal(writes.length, 0);
  assert.equal(service.model.data.draft.python, candidate.python);
  assert.equal(service.model.data.dirty, true);
  assert.equal(await service.save(), true);
  assert.deepEqual(writes[0].args, candidate.args);
  assert.equal(service.model.data.dirty, false);
  assert.equal(service.model.data.restartRequired, true);
});

test('settings refresh and late discovery cannot overwrite a newer local draft', async () => {
  let finish;
  const service = createLocalGeneration(async path => path.endsWith('/detect') ? new Promise(resolve => { finish = resolve; }) : response());
  await service.load();
  service.edit('enabled', true);
  service.edit('install_dir', 'C:/My draft');
  await service.load();
  assert.equal(service.model.data.draft.install_dir, 'C:/My draft');
  const pending = service.detect();
  service.edit('install_dir', 'C:/Newer draft');
  finish({ candidates: [candidate] });
  await pending;
  assert.equal(service.model.data.draft.install_dir, 'C:/Newer draft');
  assert.equal(service.model.data.busy, '');
  assert.equal(service.model.data.dirty, true);
});

test('multiple installations require selection, failed saves retain drafts and LAN exposes no configuration', async () => {
  const service = createLocalGeneration(async (path, options) => {
    if (path.endsWith('/detect')) return { candidates: [candidate, { ...candidate, install_dir: 'C:/Other' }] };
    if (options) throw new Error('Cannot save');
    return response();
  });
  await service.load(); service.edit('enabled', true);
  await service.detect();
  assert.equal(service.model.data.draft.install_dir, '');
  service.choose(1);
  assert.equal(service.model.data.draft.install_dir, 'C:/Other');
  assert.equal(await service.save(), false);
  assert.equal(service.model.data.draft.install_dir, 'C:/Other');
  assert.equal(service.model.data.dirty, true);
  const lan = createLocalGeneration(async () => ({ can_configure: false }));
  await lan.load();
  assert.equal(lan.model.data.canConfigure, false);
  assert.equal(lan.model.data.saved, null);
});
