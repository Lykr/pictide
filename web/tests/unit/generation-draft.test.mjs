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

test('natural-language results survive unchanged API refreshes and are invalidated by edits', async () => {
  const state = { backends: [{ id: 'tags' }, { id: 'text', kind: 'comfyui', prompt_type: 'natural_language' }], jobs: [] };
  const requests = [];
  const rendered = { positive: 'A sunlit garden.', negative: '', preparation_id: 'prepared-result' };
  const service = createGenerationController({ state, api: async (_, options) => {
    requests.push(JSON.parse(options.body));
    return { jobs: [{ id: 'image' }], rendered };
  }, getRoamSettings: () => ({}), renderJobs() {}, refresh() {} });
  service.updateGenerationHints();
  service.edit('backendId', 'text');
  service.edit('positive', 'garden');
  await service.submit();
  service.updateGenerationHints();
  assert.equal(service.model.data.rendered, rendered);
  await service.submit();
  assert.equal(requests[1].preparation_id, 'prepared-result');
  state.backends[1] = { ...state.backends[1], model: 'changed' };
  service.updateGenerationHints();
  assert.equal(service.model.data.rendered, null);
  service.model.data.rendered = rendered;
  service.edit('positive', 'forest');
  assert.equal(service.model.data.rendered, null);
});


test('selected pixels survive an uncertain retry and changing size creates a distinct request', async () => {
  const state = {backends: [{id: 'local', kind: 'openai'}], jobs: []}, requests = [];
  const service = createGenerationController({state, api: async (_, options) => {
    requests.push(JSON.parse(options.body));
    if (requests.length === 1) throw new Error('Response lost');
    return {jobs: [{id: 'job-' + requests.length}]};
  }, getRoamSettings: () => ({}), renderJobs() {}, refresh() {}});
  service.updateGenerationHints(); service.edit('positive', 'garden'); service.edit('canvasSize', '768x1024');
  await service.submit(); await service.submit();
  assert.equal(requests[0].width, 768); assert.equal(requests[0].height, 1024);
  assert.equal(requests[0].request_id, requests[1].request_id);
  service.model.data.rendered = {positive: 'A garden.', preparation_id: 'retained-text'};
  service.edit('canvasSize', '1024x768');
  assert.equal(service.model.data.rendered.preparation_id, 'retained-text');
  await service.submit();
  assert.equal(requests[2].width, 1024); assert.equal(requests[2].height, 768);
  assert.notEqual(requests[1].request_id, requests[2].request_id);
});

test('size drafts survive API refresh and same-API saves while an explicit API switch uses its default', async () => {
  const state = {backends: [{id: 'one', kind: 'openai'}, {id: 'two', kind: 'openai'}], jobs: []};
  const requests = [], service = createGenerationController({state, api: async (_, options) => {
    requests.push(JSON.parse(options.body)); return {jobs: [{id: 'job'}]};
  }, getRoamSettings: () => ({}), renderJobs() {}, refresh() {}});
  service.updateGenerationHints(); service.edit('positive', 'retained prompt'); service.edit('canvasSize', '768x1024');
  state.backends[0] = {...state.backends[0], canvas_pool_id: 'changed'};
  service.updateGenerationHints(); service.selectBackend('one');
  assert.equal(service.model.data.draft.canvasSize, '768x1024');
  service.edit('backendId', 'two');
  assert.equal(service.model.data.draft.canvasSize, '');
  assert.equal(service.model.data.draft.positive, 'retained prompt');
  await service.submit();
  assert.equal(Object.hasOwn(requests[0], 'width'), false);
  assert.equal(Object.hasOwn(requests[0], 'height'), false);
});

test('unsupported pixel sizes fail locally before creating a submission', async () => {
  const state = {backends: [{id: 'cloud', kind: 'gemini'}], jobs: []}; let calls = 0;
  const service = createGenerationController({state, api: async () => { calls++; }, getRoamSettings: () => ({}), renderJobs() {}, refresh() {}});
  service.updateGenerationHints(); service.edit('positive', 'garden'); service.edit('canvasSize', '1024x1024');
  await service.submit();
  assert.equal(calls, 0); assert.equal(service.model.data.busy, false);
});
