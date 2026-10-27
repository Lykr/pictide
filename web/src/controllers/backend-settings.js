import { createRequestId } from '../shared/request-id.mjs';
import { t, tr } from '../i18n/index.mjs';
import { publishUiState } from '../shared/ui-state.mjs';
import { notify, notifyError, dismissNotification } from '../shared/notifications.mjs';
import { createModel } from '../shared/model.mjs';
import { confirmAction } from '../components/confirm-action';
import { configuredWorkflowMode, effectiveWorkflowMode } from './feed-controls.mjs';
import { editableNodeInputs, changeNodeInput, workflowSaveFields } from './workflow-controls.mjs';
import { parseWorkflowDraft, retainedWorkflowBindings } from './workflow-panel.mjs';
import { API_KEY_MASK, apiKeyFields, customWorkflowName } from './settings-controls.mjs';
import { backendDefaults, cloudConfigFields } from './backend-controls.mjs';


/** Own Image API and workflow drafts; the app coordinates other pages. */
export function createBackendSettings({ state, api, checkBackendAvailability, showBackendAvailability,
  generation, renderRoamBackends, renderArtifacts, loadRoamSettings }) {
  const updateGenerationHints = generation.updateGenerationHints;
  const model = createModel({ draft: { selectedId: '__new__', llm_id: '', canvas_pool_id: '', width: '', height: '', prompt_type: 'danbooru', name: '', kind: 'comfyui', url: 'http://127.0.0.1:8188', key: '', model: '', size: '', quality: '', aspect_ratio: '', image_size: '', workflowMode: 'default', workflowName: '', workflowJson: '', checkpoint: '', positive: '', negative: '', seed: '', outputs: [] }, pending: {}, models: [], textInputs: [], seedInputs: [], outputs: [], nodes: [], nodeErrors: {}, nodeDrafts: {}, nodeParametersOpen: false, editorMode: 'parameters', workflowValid: true, workflowMessage: null, hasSavedApiKey: false });
  const { draft } = model.data;
  const changed = model.changed;
  function pending(name, value) { model.data.pending[name] = value; changed(); }
  let workflowInputOptions = {};
  let settingsInitialized = false;
  let settingsDirty = false;
  let workflowLoadRevision = 0;
  let hasSavedApiKey = false;
  let apiDraftRevision = 0;
  function apiDraftChanged() {
    apiDraftRevision++;
    publishUiState({ apiDraftRevision, apiTestedRevision: -1, apiSavedRevision: -1 });
  }
  publishUiState({ ready: false, apiDraftRevision, apiTestedRevision: -1, apiSavedRevision: -1, apiTestPending: false, apiSavePending: false });
  function settingsNotice(message, error = false, kind = 'success') { notify(message, { id: 'settings-operation', kind: error ? 'error' : kind }); }
  function renderBackends() {
    publishUiState({ backendCount: state.backends.length });
    checkBackendAvailability();
    if (!state.backends.some(item => item.id === draft.selectedId)) draft.selectedId = state.backends[0]?.id || '__new__';
    changed();
    updateGenerationHints();
    renderRoamBackends();
  }
  const backendTypeDrafts = new Map();
  let settingsBackendKind = 'comfyui';
  const cloudFields = ['model', 'size', 'quality', 'aspect_ratio', 'image_size'];
  function updateBackendTypeControls() { model.data.hasSavedApiKey = hasSavedApiKey; changed(); }
  function switchBackendType() {
    backendTypeDrafts.set(settingsBackendKind, { name:draft.name, url:draft.url, key:draft.key, hasKey:hasSavedApiKey, fields:Object.fromEntries(cloudFields.map(key => [key,draft[key]])) });
    const kind = draft.kind;
    const previous = backendTypeDrafts.get(kind), defaults = backendDefaults[kind];
    draft.name = previous?.name ?? defaults.name;
    draft.url = previous?.url ?? defaults.base_url;
    draft.key = previous?.key ?? ''; hasSavedApiKey = previous?.hasKey ?? false;

    for (const key of cloudFields) draft[key] = previous?.fields[key] ?? '';
    if (kind === 'gemini') draft.canvas_pool_id = '';
    settingsBackendKind = kind; workflowLoadRevision++; settingsDirty = true;
    dismissNotification('settings-operation');
    updateBackendTypeControls();
  }
  function loadBackend(id, preserveRevision = false) {
    if (!preserveRevision) apiDraftChanged();
    // Discard stale template responses when a different backend is selected.
    workflowLoadRevision++;
    pending('workflow', false); draft.selectedId = id || '__new__';
    const backend = state.backends.find((item) => item.id === id);
    backendTypeDrafts.clear();
    workflowInputOptions = {};
    draft.name = backend?.name || t("本机 ComfyUI"); draft.kind = backend?.kind || 'comfyui';
    draft.prompt_type = backend?.prompt_type || 'danbooru';
    draft.canvas_pool_id = backend?.canvas_pool_id || '';
    draft.llm_id = backend?.llm_id ?? (backend?.prompt_type === 'natural_language' ? 'legacy-prompt-api' : '');
    draft.url = backend?.base_url || 'http://127.0.0.1:8188';
    settingsBackendKind = backend?.kind || 'comfyui';
    for (const key of cloudFields) draft[key] = backend?.[key] || '';
    hasSavedApiKey = !!backend?.has_api_key;
    draft.key = hasSavedApiKey ? API_KEY_MASK : '';


    draft.workflowJson = backend?.workflow ? JSON.stringify(backend.workflow, null, 2) : '';
    draft.workflowMode = backend?.workflow_id && state.workflows.some((item) => item.id === backend.workflow_id) ? `saved:${backend.workflow_id}` : configuredWorkflowMode(backend);
    state.workflowId = backend?.workflow_id || null;
    state.workflowRevision = backend?.workflow_revision || null;
    model.data.models = backend?.default_checkpoint ? [backend.default_checkpoint] : []; draft.checkpoint = backend?.default_checkpoint || '';
    dismissNotification('settings-operation');
    draft.workflowName = backend?.workflow_name || customWorkflowName(state.workflows.map(item => item.name));
    setWorkflowPanelMode('parameters', false);
    setNodeParametersExpanded(false);
    settingsDirty = false;
    settingsInitialized = true;

    updateBindings(backend?.bindings || {}, backend?.output_nodes || []);
    updateBackendTypeControls();
    if (!preserveRevision) publishUiState({ apiSavedRevision: backend ? apiDraftRevision : -1 });
  }
  function updateWorkflowControls() { changed(); }
  function bindingValue(binding) { return binding ? JSON.stringify([String(binding.node_id), binding.input]) : ''; }
  function parseBinding(value) { if (!value) return null; const [node_id, input] = JSON.parse(value); return { node_id, input }; }
  function readWorkflow() {
    return parseWorkflowDraft(draft.workflowJson);
  }
  function setNodeParametersExpanded(expanded) { model.data.nodeParametersOpen = expanded; changed(); }
  function setWorkflowPanelMode(mode, validate = true) {
    if (validate) setNodeParametersExpanded(true);
    if (mode === 'json' && validate && Object.keys(model.data.nodeErrors).length) {
      settingsNotice(() => t('请先修正节点参数中的无效输入，再切换 JSON。'), true); return;
    }
    if (mode === 'parameters' && validate && !updateBindings()) mode = 'json';
    model.data.editorMode = mode; changed();
  }
  function updateBindings(bindings = null, outputNodes = null) {
    const previous = bindings || { positive: parseBinding(draft.positive), negative: parseBinding(draft.negative), seed: parseBinding(draft.seed), width: parseBinding(draft.width), height: parseBinding(draft.height) };
    try {
      const workflow = readWorkflow();
      const retained = retainedWorkflowBindings(workflow, previous, outputNodes || draft.outputs);
      const texts = [], seeds = [], outputs = [];
      for (const [nodeId, node] of Object.entries(workflow)) {
        if (!node?.class_type || !node?.inputs) continue;
        const label = `${nodeId} · ${node._meta?.title || node.class_type}`;
        outputs.push({ value: nodeId, label });
        for (const [input, value] of Object.entries(node.inputs)) {
          const choice = { value: bindingValue({ node_id: nodeId, input }), label: `${label} → ${input}` };
          if (typeof value === 'string') texts.push(choice);
          if (typeof value === 'number' && Number.isInteger(value)) seeds.push(choice);
        }
      }
      Object.assign(model.data, { textInputs: texts, seedInputs: seeds, outputs, workflowValid: true,
        workflowMessage: () => tr`${Object.keys(workflow).length} 个节点 · ${texts.length} 个文本输入`,
        nodes: editableNodeInputs(workflow, workflowInputOptions), nodeErrors: {}, nodeDrafts: {} });
      draft.positive = bindingValue(retained.bindings.positive); draft.negative = bindingValue(retained.bindings.negative); draft.seed = bindingValue(retained.bindings.seed); draft.width = bindingValue(retained.bindings.width); draft.height = bindingValue(retained.bindings.height); draft.outputs = retained.output_nodes;
      dismissNotification('workflow-json'); changed(); return true;
    } catch (error) {
      Object.assign(model.data, { workflowValid: false, workflowMessage: () => t('支持从 ComfyUI 导出的 API 工作流。'), nodes: [] });
      if (draft.workflowJson.trim()) notifyError(error.message, { id: 'workflow-json' });
      if (bindings !== null) { model.data.textInputs = []; model.data.seedInputs = []; model.data.outputs = []; draft.positive = ''; draft.negative = ''; draft.seed = ''; draft.width = ''; draft.height = ''; draft.outputs = []; }
      changed(); return false;
    }
  }
  function editNode(node, input, value) {
    const key = `${node.id}:${input.name}`;
    model.data.nodeDrafts[key] = value;
    try {
      const updated = changeNodeInput(readWorkflow(), node.id, input.name, value, input.kind);
      draft.workflowJson = JSON.stringify(updated, null, 2); delete model.data.nodeErrors[key]; dismissNotification('workflow-json');
    } catch (error) { model.data.nodeErrors[key] = error.message; }
    settingsDirty = true; apiDraftChanged(); changed();
  }

  function applyWorkflowDraft(record, inputOptions = {}) {
    apiDraftChanged();
    workflowInputOptions = inputOptions;
    draft.workflowJson = JSON.stringify(record.workflow, null, 2);
    draft.workflowMode = 'custom';
    state.workflowId = null;
    state.workflowRevision = null;
    if (!record.id) draft.workflowName = customWorkflowName(state.workflows.map(item => item.name));
    settingsDirty = true;
    updateBindings(record.bindings, record.output_nodes || []); updateWorkflowControls();
    setWorkflowPanelMode('parameters', false);
  }

  async function currentDefaultTemplate() {
    const version = workflowLoadRevision;
    const editedId = draft.selectedId;
    const url = draft.url;
    const checkpoint = draft.checkpoint;
    const payload = { ...connectionDraft(), default_checkpoint:checkpoint };
    const id = editedId === '__new__' ? 'new' : editedId;
    const result = await api(`/api/backends/${encodeURIComponent(id)}/template`, { method:'POST', body:JSON.stringify(payload) });
    if (workflowLoadRevision !== version || draft.selectedId !== editedId || draft.url !== url || draft.checkpoint !== checkpoint) throw new Error(t("生图 API、工作流或模型选择已变化，请重新读取默认节点参数。"));
    return result;
  }

  function renderWorkflowLibrary(selected = draft.workflowMode) {
    draft.workflowMode = ['default', 'custom', ...state.workflows.map(record => `saved:${record.id}`)].includes(selected) ? selected : 'custom';
    updateWorkflowControls();
  }
  async function loadWorkflowLibrary(selected = draft.workflowMode) {
    const result = await api('/api/workflows');
    state.workflows = result.workflows || [];
    renderWorkflowLibrary(selected);
  }
  async function selectWorkflow() {
    const selected = draft.workflowMode;
    const revision = ++workflowLoadRevision;
    settingsDirty = true;
    if (!selected.startsWith('saved:')) {
      if (selected === 'custom') draft.workflowName = customWorkflowName(state.workflows.map(item => item.name));
      state.workflowId = null;
      state.workflowRevision = null;
      setWorkflowPanelMode('parameters', false);
      updateWorkflowControls();
      return;
    }
    pending('workflow', true);
    settingsNotice(() => t("正在读取工作流…"), false, 'info');
    try {
      const record = await api(`/api/workflows/${encodeURIComponent(selected.slice(6))}`);
      if (workflowLoadRevision !== revision) return;
      applyWorkflowDraft(record);
      draft.workflowMode = selected;
      state.workflowId = record.id;
      state.workflowRevision = record.revision;
      draft.workflowName = record.name;
      setWorkflowPanelMode('parameters', false);
      updateWorkflowControls();
      dismissNotification('settings-operation');
    } catch (error) { settingsNotice(error.message, true); }
    finally { if (workflowLoadRevision === revision) pending('workflow', false); }
  }
  function connectionDraft() {
    const payload = { name: draft.name.trim(), kind: draft.kind, base_url: draft.url.trim(), prompt_type: draft.prompt_type, llm_id: draft.llm_id || '', canvas_pool_id: draft.kind === 'gemini' ? '' : draft.canvas_pool_id || '' };
    if (!payload.name || !payload.base_url) throw new Error(t('请填写 API 名称和 API 地址。'));
    Object.assign(payload, apiKeyFields(draft.key, hasSavedApiKey)); return payload;
  }
  function draftBackend({ saveWorkflow = false } = {}) {
    const payload = connectionDraft();
    if (payload.kind !== 'comfyui') return { ...payload, ...cloudConfigFields(payload.kind, Object.fromEntries(cloudFields.map(key => [key, draft[key]]))) };
    payload.workflow_mode = draft.workflowMode === 'default' ? 'default' : 'custom';
    if (payload.workflow_mode === 'default') return { ...payload, default_checkpoint: draft.checkpoint };
    if (Object.keys(model.data.nodeErrors).length) { setNodeParametersExpanded(true); setWorkflowPanelMode('parameters', false); throw new Error(t('请先修正节点参数中的无效输入。')); }
    const workflow = readWorkflow();
    const positive = parseBinding(draft.positive), negative = parseBinding(draft.negative), seed = parseBinding(draft.seed);
    if (!positive) throw new Error(t('请选择正向提示词输入。'));
    if (!negative) throw new Error(t('请选择负向提示词输入，以便准确记录本次实际使用的提示词。'));
    if (bindingValue(positive) === bindingValue(negative)) throw new Error(t('正向和负向提示词不能绑定同一个输入。'));
    const width = parseBinding(draft.width), height = parseBinding(draft.height);
    if (!!width !== !!height || payload.canvas_pool_id && !width) throw new Error(t('使用画幅池时，请同时绑定宽度和高度输入。'));
    const custom = { ...payload, workflow, bindings: { positive, negative, seed, ...(width && height ? {width, height} : {}) }, output_nodes: draft.outputs };
    return saveWorkflow ? { ...custom, ...workflowSaveFields(custom, draft.workflowName, state.workflowId ? { id: state.workflowId, revision: state.workflowRevision } : null) } : custom;
  }
  function edit(key, value) {
    draft[key] = value; settingsDirty = true; apiDraftChanged();
    if (key === 'kind') switchBackendType();
    if (key === 'selectedId') loadBackend(value);
    if (key === 'workflowMode') selectWorkflow();
    if (key === 'workflowJson') updateBindings();
    changed();
  }
  async function editDefaultParameters() {
    pending('template', true); settingsNotice(() => t("正在读取默认工作流参数…"), false, 'info');
    try { const template = await currentDefaultTemplate(); applyWorkflowDraft(template, template.input_options || {}); setNodeParametersExpanded(true); settingsNotice(() => t("已展开节点参数，保存后生效。")); }
    catch (error) { settingsNotice(error.message, true); }
    finally { pending('template', false); }
  }
  async function reloadWorkflows() {
    pending('library', true);
    try { await loadWorkflowLibrary(); settingsNotice(() => t("工作流列表已刷新。")); }
    catch (error) { settingsNotice(error.message, true); }
    finally { pending('library', false); }
  }
  async function deleteWorkflow() {
    const id = state.workflowId, revision = state.workflowRevision;
    const workflow = state.workflows.find(item => item.id === id);
    if (state.saving || !workflow || !revision) return;
    if (!await confirmAction(tr`删除工作流「${workflow.name}」？已配置生图 API 保留当前工作流参数，历史任务和图片保留。`)) return;
    state.saving = true; pending('saving', true);
    try {
      await api(`/api/workflows/${encodeURIComponent(id)}`, { method: 'DELETE', body: JSON.stringify({ revision }) });
      state.workflows = state.workflows.filter(item => item.id !== id);
      state.backends = state.backends.map(backend => {
        if (backend.workflow_id !== id) return backend;
        const copy = { ...backend }; for (const key of ['workflow_id', 'workflow_revision', 'workflow_name']) delete copy[key]; return copy;
      });
      state.workflowId = null; state.workflowRevision = null; workflowLoadRevision++;
      renderWorkflowLibrary('custom'); renderBackends(); settingsDirty = true;
      settingsNotice(() => t("工作流已删除，当前参数保留为自定义草稿。"));
    } catch (error) { settingsNotice(error.message, true); }
    finally { state.saving = false; pending('saving', false); }
  }
  async function deleteBackend() {
    const id = draft.selectedId, backend = state.backends.find(item => item.id === id);
    if (state.saving || !backend) return;
    if (!await confirmAction(tr`删除 API 配置「${backend.name}」？${settingsDirty ? t("当前未保存的生图 API 修改将放弃。") : ''}历史任务和图片保留，已有任务继续使用提交时的配置。`)) return;
    state.saving = true; pending('saving', true);
    try {
      await api(`/api/backends/${encodeURIComponent(id)}`, { method: 'DELETE', body: '{}' });
      state.backends = state.backends.filter(item => item.id !== id);
      renderBackends(); loadBackend(draft.selectedId); renderArtifacts();
      settingsNotice(() => t("API 配置已删除。"));
    } catch (error) { settingsNotice(error.message, true); }
    finally { state.saving = false; pending('saving', false); }
  }
  async function importWorkflow(file) {
    if (!file) return;
    const revision = workflowLoadRevision;
    try {
      const source = await file.text();
      if (revision !== workflowLoadRevision) return;
      draft.workflowJson = source;
      settingsDirty = true;
      workflowInputOptions = {};
      const valid = updateBindings();
      updateWorkflowControls();
      setNodeParametersExpanded(true);
      if (!valid) setWorkflowPanelMode('json', false);
    } catch (error) { settingsNotice(error.message, true); }
    finally { apiDraftChanged(); changed(); }
  }
  async function loadModels() {
    if (model.data.pending.models) return; pending('models', true);
    const editedId = draft.selectedId;
    const baseUrl = draft.url;
    try {
      const payload = connectionDraft(); const id = editedId === '__new__' ? 'new' : editedId;
      const result = await api(`/api/backends/${encodeURIComponent(id)}/models`, { method: 'POST', body: JSON.stringify(payload) });
      if (draft.selectedId !== editedId || draft.url !== baseUrl) return;
      const selected = draft.checkpoint;
      const models = (result.models || []).filter((model) => typeof model === 'string');
      model.data.models = models; draft.checkpoint = '';
      if (models.includes(selected)) draft.checkpoint = selected;
        if (!models.length) notify(() => t("生图 API 没有可用模型，请在 ComfyUI 中配置。"), { id: 'model-list', kind: 'warning' });
      else dismissNotification('model-list');

    } catch (error) { notifyError(() => tr`读取失败：${error.message}`, { id: 'model-list' }); }
    finally { pending('models', false); }
  }
  async function testBackend() {
    const revision = apiDraftRevision;
    publishUiState({ apiTestPending: true, apiTestedRevision: -1 });
    pending('test', true); settingsNotice(() => t("正在测试连接…"), false, 'info');
    try {
      const payload = draftBackend();
      const id = draft.selectedId === '__new__' ? 'new' : draft.selectedId;
      const result = await api(`/api/backends/${encodeURIComponent(id)}/check`, { method: 'POST', body: JSON.stringify(payload) });
      if (result.ok && revision === apiDraftRevision) publishUiState({ apiTestedRevision: revision });
      settingsNotice(result.message || (result.ok ? t("连接成功。") : t("连接失败。")), !result.ok);
      if (id !== 'new' && result.ok) showBackendAvailability(true);
    }
    catch (error) { settingsNotice(error.message, true); }
    finally { pending('test', false); publishUiState({ apiTestPending: false }); }
  }
  async function save() {
    if (state.saving) return;
    const revision = apiDraftRevision; publishUiState({ apiSavePending: true });
    state.saving = true;  pending('saving', true);
    try {
      const payload = draftBackend({ saveWorkflow: true });
      const id = draft.selectedId === '__new__' ? createRequestId() : draft.selectedId;
      const result = await api(`/api/backends/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(payload) });
      const backend = result.backend || result;
      const index = state.backends.findIndex((item) => item.id === backend.id);
      if (index >= 0) state.backends[index] = backend; else state.backends.push(backend);
      renderBackends(); draft.selectedId = backend.id; generation.selectBackend(backend.id);
      updateGenerationHints();
      await loadWorkflowLibrary(backend.workflow_id ? `saved:${backend.workflow_id}` : 'default');
      loadBackend(backend.id, true); renderArtifacts();
      if (revision === apiDraftRevision) publishUiState({ apiSavedRevision: revision });
      await loadRoamSettings({ preserveDraft: true });
      settingsNotice(() => backend.workflow_name ? tr`生图 API 与工作流「${backend.workflow_name}」已保存。` : t("生图 API 已保存。"));
    } catch (error) { settingsNotice(error.message, true); }
    finally { state.saving = false;  pending('saving', false); publishUiState({ apiSavePending: false }); }
  }

  return {
    model, edit, editNode, setNodeParametersExpanded, setWorkflowPanelMode, editDefaultParameters, reloadWorkflows, deleteWorkflow, deleteBackend, importWorkflow, loadModels, testBackend, save, renderBackends, loadBackend, loadWorkflowLibrary,
    get initialized() { return settingsInitialized; },
    get dirty() { return settingsDirty; },
  };
}
