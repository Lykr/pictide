import test from 'node:test';
import assert from 'node:assert/strict';
import { editableNodeInputs, changeNodeInput, workflowRecord, workflowSaveFields } from '../web/src/controllers/workflow-controls.mjs';

const graph = () => ({
  '1': {class_type:'CheckpointLoaderSimple', inputs:{ckpt_name:'test.safetensors'}},
  '4': {class_type:'EmptyLatentImage', inputs:{width:1024, height:1024, batch_size:1}},
  '5': {class_type:'KSampler', inputs:{seed:0, steps:28, cfg:5.5, denoise:1, sampler_name:'dpmpp_2m', scheduler:'karras', model:['1',0], positive:['2',0], negative:['3',0], latent_image:['4',0]}},
  '6': {class_type:'Custom', inputs:{enabled:true, mode:'auto', dynamic:{skip:'object'}}},
});

test('node editor exposes scalar values and preserves connections as graph-only fields', () => {
  const nodes = editableNodeInputs(graph(), {KSampler:{sampler_name:['euler', 'dpmpp_2m']}});
  assert.deepEqual(nodes.find((node) => node.id === '5').inputs.map((input) => input.name), ['seed','steps','cfg','denoise','sampler_name','scheduler']);
  const sampler = nodes.find((node) => node.id === '5');
  assert.equal(sampler.inputs.find((input) => input.name === 'steps').kind, 'integer');
  assert.equal(sampler.inputs.find((input) => input.name === 'cfg').kind, 'number');
  assert.equal(sampler.inputs.find((input) => input.name === 'denoise').kind, 'number');
  assert.deepEqual(sampler.inputs.find((input) => input.name === 'sampler_name').options, ['euler', 'dpmpp_2m']);
  assert.equal(nodes.find((node) => node.id === '6').inputs.find((input) => input.name === 'enabled').kind, 'boolean');
});

test('node edits retain typed parameters and do not disturb graph links', () => {
  const workflow = graph();
  changeNodeInput(workflow, '4', 'width', '768', 'integer');
  changeNodeInput(workflow, '5', 'denoise', '0.7', 'number');
  changeNodeInput(workflow, '5', 'scheduler', 'normal', 'string');
  changeNodeInput(workflow, '6', 'enabled', false, 'boolean');
  assert.equal(workflow['4'].inputs.width, 768);
  assert.equal(workflow['5'].inputs.denoise, .7);
  assert.equal(workflow['5'].inputs.scheduler, 'normal');
  assert.equal(workflow['6'].inputs.enabled, false);
  assert.deepEqual(workflow['5'].inputs.model, ['1',0]);
  for (const value of ['', '1.5', 'NaN', '9007199254740992']) assert.throws(() => changeNodeInput(workflow, '4', 'width', value, 'integer'));
  assert.throws(() => changeNodeInput(workflow, '5', 'model', 'bad', 'string'));
});

test('workflow save records contain only graph configuration and a validated new name', () => {
  const draft = {workflow:graph(), bindings:{positive:{node_id:'2',input:'text'}}, output_nodes:['7'], api_key:'secret', base_url:'http://private'};
  const record = workflowRecord(draft, '  My workflow  ');
  assert.equal(record.name, 'My workflow');
  assert.deepEqual(Object.keys(record), ['name','workflow','bindings','output_nodes']);
  assert.equal(record.workflow, draft.workflow);
  for (const name of ['', ' ', '../bad', 'bad\\path', 'a\nb', 'a'.repeat(121)]) assert.throws(() => workflowRecord(draft, name));
});

test('backend save attaches a template name and preserves selected revision without leaking credentials', () => {
  const draft = { workflow_mode: 'custom', workflow: graph(), bindings: {}, api_key: 'secret' };
  assert.deepEqual(workflowSaveFields(draft, '  New template  '), { workflow_name: 'New template' });
  assert.deepEqual(workflowSaveFields(draft, 'Existing', { id: 'wf-1', revision: 'revision-1' }), { workflow_name: 'Existing', workflow_id: 'wf-1', workflow_revision: 'revision-1' });
  assert.deepEqual(workflowSaveFields(draft, 'Renamed', { id: 'wf-1', revision: 'revision-1' }), { workflow_name: 'Renamed', workflow_id: 'wf-1', workflow_revision: 'revision-1' });
  assert.throws(() => workflowSaveFields(draft, ' '));
  assert.deepEqual(workflowSaveFields({ workflow_mode: 'default' }, ''), {});
});
