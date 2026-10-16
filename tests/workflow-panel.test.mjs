import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWorkflowDraft, retainedWorkflowBindings } from '../web/src/controllers/workflow-panel.mjs';

const graph = () => ({
  '2': { class_type: 'CLIPTextEncode', inputs: { text: 'positive', clip: ['1', 1] } },
  '3': { class_type: 'CLIPTextEncode', inputs: { text: 'negative', clip: ['1', 1] } },
  '5': { class_type: 'KSampler', inputs: { seed: 42, cfg: 5.5, positive: ['2', 0] } },
  '7': { class_type: 'SaveImage', inputs: { images: ['6', 0] } },
});

test('workflow panel accepts API graphs and rejects incomplete edits and canvas exports', () => {
  const source = JSON.stringify(graph(), null, 2);
  assert.deepEqual(parseWorkflowDraft(source), graph());
  for (const value of ['', '   ', '{', '{"2":', '[]', '{}', 'null', JSON.stringify({ nodes: [] })]) assert.throws(() => parseWorkflowDraft(value));
});

test('JSON edits keep valid bindings and outputs while removing stale or differently typed inputs', () => {
  const bindings = { positive: { node_id: '2', input: 'text' }, negative: { node_id: '3', input: 'text' }, seed: { node_id: '5', input: 'seed' } };
  const workflow = graph();
  assert.deepEqual(retainedWorkflowBindings(workflow, bindings, ['7']), { bindings, output_nodes: ['7'] });
  delete workflow['3'];
  workflow['5'].inputs.seed = ['9', 0];
  assert.deepEqual(retainedWorkflowBindings(workflow, bindings, ['7', '8']), { bindings: { positive: bindings.positive, negative: null, seed: null }, output_nodes: ['7'] });
  assert.equal(bindings.negative.node_id, '3');
  assert.equal(bindings.seed.input, 'seed');
});
