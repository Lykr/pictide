/** Parse the single JSON draft shared by both workflow editing views. */
export function parseWorkflowDraft(source) {
  const text = source.trim();
  if (!text) throw new Error('请导入 API 格式工作流。');
  const workflow = JSON.parse(text);
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow) || workflow.nodes || !Object.values(workflow).some(node => node?.class_type && node?.inputs)) {
    throw new Error('需要 ComfyUI「API 格式」工作流，而非普通画布 JSON。');
  }
  return workflow;
}

/** Retain bindings only while their input still exists with the expected type. */
export function retainedWorkflowBindings(workflow, bindings = {}, outputNodes = []) {
  const retain = (binding, type) => {
    const value = binding && workflow[binding.node_id]?.inputs?.[binding.input];
    return (type === 'integer' ? Number.isInteger(value) : typeof value === type) ? binding : null;
  };
  return {
    bindings: { positive: retain(bindings?.positive, 'string'), negative: retain(bindings?.negative, 'string'), seed: retain(bindings?.seed, 'integer'), ...(bindings?.steps ? { steps: bindings.steps.input === 'steps' ? retain(bindings.steps, 'integer') : null } : {}) },
    output_nodes: outputNodes.filter(id => workflow[id]?.class_type && workflow[id]?.inputs),
  };
}

/** Only scalar integer steps can be adjusted without replacing a connection. */
export function workflowStepInputs(workflow) {
  return Object.entries(workflow).filter(([, node]) => Number.isSafeInteger(node?.inputs?.steps)).map(([node_id]) => ({ node_id, input: 'steps' }));
}

export function selectedStepsBinding(workflow, binding = null) {
  const choices = workflowStepInputs(workflow);
  return choices.find(item => item.node_id === String(binding?.node_id) && item.input === binding?.input) || (choices.length === 1 ? choices[0] : null);
}
