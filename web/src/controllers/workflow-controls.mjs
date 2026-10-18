import { t, tr, locale } from '../i18n/index.mjs';
const decimalInputs = new Set(['cfg', 'denoise', 'strength', 'start_percent', 'end_percent']);

export function editableNodeInputs(workflow, inputOptions = {}) {
  return Object.entries(workflow).filter(([, node]) => node?.class_type && node.inputs).map(([id, node]) => ({
    id, title: node._meta?.title || node.class_type, classType: node.class_type,
    inputs: Object.entries(node.inputs).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).map(([name, value]) => ({
      name, value,
      kind: typeof value === 'number' ? Number.isInteger(value) && !decimalInputs.has(name) ? 'integer' : 'number' : typeof value,
      options: inputOptions[node.class_type]?.[name] || null,
    })),
  })).filter((node) => node.inputs.length);
}

export function changeNodeInput(workflow, nodeId, name, rawValue, kind) {
  const node = workflow[nodeId];
  if (!node || !Object.hasOwn(node.inputs, name) || Array.isArray(node.inputs[name])) throw new Error(t("该输入不是可编辑参数。"));
  let value = rawValue;
  if (kind === 'number' || kind === 'integer') {
    value = Number(rawValue);
    if (!String(rawValue).trim() || !Number.isFinite(value) || (kind === 'integer' && !Number.isSafeInteger(value))) throw new Error(kind === 'integer' ? t("请输入有效整数。") : t("请输入有效数值。"));
  } else if (kind === 'boolean') value = !!rawValue;
  node.inputs[name] = value;
  return workflow;
}

export function workflowRecord(draft, name) {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > 120 || /[\\/\u0000-\u001f]/.test(trimmed)) throw new Error(t("请输入 1–120 字的工作流名称，不含路径或控制字符。"));
  return { name:trimmed, workflow:draft.workflow, bindings:draft.bindings, output_nodes:draft.output_nodes || [] };
}

// Save templates through the backend transaction; the selected ID and revision
// update that template, while custom drafts without an ID create a new one.
export function workflowSaveFields(draft, name, template = null) {
  if (draft.workflow_mode === 'default') return {};
  const { name: workflow_name } = workflowRecord(draft, name);
  return { workflow_name, ...(template?.id ? { workflow_id: template.id, workflow_revision: template.revision } : {}) };
}
