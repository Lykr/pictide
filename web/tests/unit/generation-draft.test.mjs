import test from 'node:test';
import assert from 'node:assert/strict';
import { createGenerationController } from '../../src/controllers/generation-controller.js';

function controller(api) {
  const state = { backends: [{ id: 'local', kind: 'comfyui', workflow_mode: 'default' }], jobs: [] };
  const service = createGenerationController({ state, api, getRoamSettings: () => ({ preset_id: 'preset' }), renderJobs() {}, refresh() {} });
  service.updateGenerationHints();
  return service;
}

test('an uncertain submission retries its request ID while a changed draft gets another ID', async () => {
  const requests = [];
  const service = controller(async (path, options) => {
    requests.push(JSON.parse(options.body));
    if (requests.length === 1) throw new Error('Connection lost after submission');
    return { jobs: [{ id: `job-${requests.length}` }] };
  });
  service.edit('positive', 'garden');
  await service.submit();
  assert.equal(service.dirty, true);
  assert.equal(service.model.data.busy, false);
  await service.submit();
  assert.equal(requests[0].request_id, requests[1].request_id);
  assert.equal(service.dirty, false);
  service.edit('positive', 'forest');
  await service.submit();
  assert.notEqual(requests[1].request_id, requests[2].request_id);
});

test('refreshing presets retains edited prompts and counters, and editing a prompt disables automatic drawing', async () => {
  const service = controller(async () => ({ presets: [{ id: 'preset', name: 'Preset' }] }));
  service.edit('positive', 'my draft');
  service.edit('ruleSeed', '123');
  service.edit('step', '7');
  await service.loadRuleConfigs();
  assert.equal(service.model.data.draft.positive, 'my draft');
  assert.equal(service.model.data.draft.ruleSeed, '123');
  assert.equal(service.model.data.draft.step, '7');
  service.edit('source', 'rules');
  service.edit('positive', 'edited prompt');
  assert.equal(service.model.data.draft.automatic, false);
});

test('duplicate clicks during submission do not start a second request', async () => {
  let finish, count = 0;
  const service = controller(() => { count++; return new Promise(resolve => { finish = resolve; }); });
  service.edit('positive', 'garden');
  const submitted = service.submit();
  await service.submit();
  assert.equal(count, 1);
  assert.equal(service.model.data.busy, true);
  finish({ jobs: [{ id: 'job' }] });
  await submitted;
  assert.equal(service.model.data.busy, false);
});
