import { t, tr } from '../i18n/index.mjs';
import { publishUiState } from '../shared/ui-state.mjs';
import { notify, notifyError, dismissNotification } from '../shared/notifications.mjs';
import { decorateElement } from '../dom-primitives';
import { confirmAction } from '../components/confirm-action';
import { configuredWorkflowMode, effectiveWorkflowMode } from './feed-controls.mjs';
import { editableNodeInputs, changeNodeInput, workflowSaveFields } from './workflow-controls.mjs';
import { parseWorkflowDraft, retainedWorkflowBindings } from './workflow-panel.mjs';
import { API_KEY_MASK, apiKeyFields, customWorkflowName } from './settings-controls.mjs';
import { backendDefaults, cloudConfigFields } from './backend-controls.mjs';
import { $, option, translatedOption, describeAction, setStatusText } from './dom-utils.mjs';

/** Own Image API and workflow drafts; the app coordinates other pages. */
export function createBackendSettings({ state, api, checkBackendAvailability, showBackendAvailability,
  updateGenerationHints, renderRoamBackends, renderArtifacts, loadRoamSettings }) {
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
    const selected = $('generate-backend').value;
    $('generate-backend').replaceChildren(...(state.backends.length ? state.backends.map((backend) => option(backend.id, backend.name)) : [translatedOption('', "请先配置生图 API")]));
    if (state.backends.some((backend) => backend.id === selected)) $('generate-backend').value = selected;
    $('generate').disabled = !state.backends.length;
    checkBackendAvailability();
    const edited = $('edit-backend').value;
    $('edit-backend').replaceChildren(...state.backends.map((backend) => option(backend.id, backend.name)), translatedOption('__new__', "＋ 添加 API"));
    if (state.backends.some((backend) => backend.id === edited)) $('edit-backend').value = edited;
    updateGenerationHints();
    renderRoamBackends();
  }
  const backendTypeDrafts = new Map();
  let settingsBackendKind = 'comfyui';
  const cloudInputIds = { model:'backend-model', size:'backend-size', quality:'backend-quality', aspect_ratio:'backend-aspect-ratio', image_size:'backend-image-size' };
  function updateBackendTypeControls() {
    const kind = $('backend-kind').value, cloud = kind !== 'comfyui';
    $('cloud-backend').hidden = !cloud; $('cloud-backend').disabled = !cloud;
    $('workflow-picker-field').hidden = cloud;
    $('openai-options').hidden = kind !== 'openai'; $('openai-options').disabled = kind !== 'openai';
    $('gemini-options').hidden = kind !== 'gemini'; $('gemini-options').disabled = kind !== 'gemini';
    describeAction($('key-state'), hasSavedApiKey ? t("已保存密钥。保留遮罩不修改，清空并保存可移除。") : cloud ? t('填写所选生图服务的 API Key。') : t("可选。本机 ComfyUI 通常无需密钥。"));
    updateWorkflowControls();
  }
  function switchBackendType() {
    backendTypeDrafts.set(settingsBackendKind, { name:$('backend-name').value, url:$('backend-url').value, key:$('backend-key').value, hasKey:hasSavedApiKey, fields:Object.fromEntries(Object.entries(cloudInputIds).map(([key,id]) => [key,$(id).value])) });
    const kind = $('backend-kind').value;
    const previous = backendTypeDrafts.get(kind), defaults = backendDefaults[kind];
    $('backend-name').value = previous?.name ?? defaults.name;
    $('backend-url').value = previous?.url ?? defaults.base_url;
    $('backend-key').value = previous?.key ?? ''; hasSavedApiKey = previous?.hasKey ?? false;
    $('backend-key').setCustomValidity('');
    for (const [key,id] of Object.entries(cloudInputIds)) $(id).value = previous?.fields[key] ?? '';
    settingsBackendKind = kind; workflowLoadRevision++; settingsDirty = true;
    dismissNotification('settings-operation');
    updateBackendTypeControls();
  }
  function loadBackend(id, preserveRevision = false) {
    if (!preserveRevision) apiDraftChanged();
    // Discard stale template responses when a different backend is selected.
    workflowLoadRevision++;
    $('workflow-mode').disabled = false;
    const backend = state.backends.find((item) => item.id === id);
    backendTypeDrafts.clear();
    workflowInputOptions = {};
    $('backend-name').value = backend?.name || t("本机 ComfyUI"); $('backend-kind').value = backend?.kind || 'comfyui';
    $('backend-url').value = backend?.base_url || 'http://127.0.0.1:8188';
    settingsBackendKind = backend?.kind || 'comfyui';
    for (const [key, inputId] of Object.entries(cloudInputIds)) $(inputId).value = backend?.[key] || '';
    hasSavedApiKey = !!backend?.has_api_key;
    $('backend-key').value = hasSavedApiKey ? API_KEY_MASK : '';
    $('backend-key').setCustomValidity('');
    describeAction($('key-state'), hasSavedApiKey ? t("已保存密钥。保留遮罩不修改，清空并保存可移除。") : t("可选。本机 ComfyUI 通常无需密钥。"));
    $('workflow-json').value = backend?.workflow ? JSON.stringify(backend.workflow, null, 2) : '';
    $('workflow-mode').value = backend?.workflow_id && state.workflows.some((item) => item.id === backend.workflow_id) ? `saved:${backend.workflow_id}` : configuredWorkflowMode(backend);
    state.workflowId = backend?.workflow_id || null;
    state.workflowRevision = backend?.workflow_revision || null;
    $('default-checkpoint').replaceChildren(translatedOption('', "自动选择第一个可用模型"));
    if (backend?.default_checkpoint) { $('default-checkpoint').append(option(backend.default_checkpoint, backend.default_checkpoint)); $('default-checkpoint').value = backend.default_checkpoint; }
    dismissNotification('settings-operation');
    $('workflow-name').value = backend?.workflow_name || customWorkflowName(state.workflows.map(item => item.name));
    setWorkflowPanelMode('parameters', false);
    setNodeParametersExpanded(false);
    settingsDirty = false;
    settingsInitialized = true;
    $('delete-backend').disabled = !backend;
    updateBindings(backend?.bindings || {}, backend?.output_nodes || []);
    updateBackendTypeControls();
    if (!preserveRevision) publishUiState({ apiSavedRevision: backend ? apiDraftRevision : -1 });
  }
  function updateWorkflowControls() {
    const cloud = $('backend-kind').value !== 'comfyui';
    const custom = $('workflow-mode').value !== 'default';
    $('custom-workflow').hidden = cloud || !custom; $('custom-workflow').disabled = cloud || !custom;
    $('default-workflow').hidden = cloud || custom;
    $('workflow-mode').disabled = cloud;
    const needsBindings = !cloud && effectiveWorkflowMode($('workflow-mode').value === 'default' ? 'default' : 'custom', $('workflow-json').value) === 'custom';
    $('binding-positive').required = needsBindings; $('binding-negative').required = needsBindings;
    $('workflow-name').required = !cloud && custom;
    $('delete-workflow').disabled = !state.workflowId || !state.workflows.some(item => item.id === state.workflowId);
    if (custom && !needsBindings) { setStatusText('workflow-error', () => t("请导入 API 工作流，或从默认文生图读取节点参数。")); $('workflow-error').classList.remove('valid'); }
  }
  function bindingValue(binding) { return binding ? JSON.stringify([String(binding.node_id), binding.input]) : ''; }
  function parseBinding(value) { if (!value) return null; const [node_id, input] = JSON.parse(value); return { node_id, input }; }
  function readWorkflow() {
    return parseWorkflowDraft($('workflow-json').value);
  }
  function setNodeParametersExpanded(expanded) {
    const trigger = $('toggle-node-parameters');
    if (trigger.getAttribute('aria-expanded') !== String(expanded)) trigger.click();
  }
  function setWorkflowPanelMode(mode, validate = true) {
    if (validate) setNodeParametersExpanded(true);
    if (mode === 'json' && validate) {
      const invalidParameter = $('node-parameter-fields').querySelector(':invalid');
      if (invalidParameter) {
        invalidParameter.reportValidity(); invalidParameter.focus();
        settingsNotice(() => t("请先修正节点参数中的无效输入，再切换 JSON。"), true);
        return;
      }
    }
    if (mode === 'parameters' && validate && !updateBindings()) {
      // Keep incomplete JSON visible instead of replacing it with a stale form.
      mode = 'json';
    }
    const json = mode === 'json';
    $('node-parameters').dataset.editorMode = mode;
    $('node-parameter-fields').hidden = json;
    $('workflow-json-editor').hidden = !json;
    $('toggle-workflow-json').setAttribute('aria-pressed', String(json));
    describeAction($('toggle-workflow-json'), json ? t("返回节点参数") : t("编辑 API 工作流 JSON"));
  }
  function updateBindings(bindings = null, outputNodes = null) {
    const previous = bindings || { positive: parseBinding($('binding-positive').value), negative: parseBinding($('binding-negative').value), seed: parseBinding($('binding-seed').value) };
    const previousOutputs = outputNodes || [...$('output-nodes').selectedOptions].map((item) => item.value);
    const positive = $('binding-positive'), negative = $('binding-negative'), seed = $('binding-seed'), outputs = $('output-nodes');
    try {
      const workflow = readWorkflow(); let textCount = 0;
      const retained = retainedWorkflowBindings(workflow, previous, previousOutputs);
      positive.replaceChildren(translatedOption('', "选择正向 text 输入")); negative.replaceChildren(translatedOption('', "选择负向 text 输入")); seed.replaceChildren(translatedOption('', "不绑定")); outputs.replaceChildren();
      for (const [nodeId, node] of Object.entries(workflow)) {
        if (!node?.class_type || !node?.inputs) continue;
        const label = `${nodeId} · ${node._meta?.title || node.class_type}`;
        outputs.append(option(nodeId, label));
        for (const [input, value] of Object.entries(node.inputs)) {
          const key = bindingValue({ node_id: nodeId, input });
          if (typeof value === 'string') { positive.append(option(key, `${label} → ${input}`)); negative.append(option(key, `${label} → ${input}`)); textCount++; }
          if (typeof value === 'number' && Number.isInteger(value)) seed.append(option(key, `${label} → ${input}`));
        }
      }
      positive.value = bindingValue(retained.bindings.positive); negative.value = bindingValue(retained.bindings.negative); seed.value = bindingValue(retained.bindings.seed);
      [...outputs.options].forEach((item) => { item.selected = retained.output_nodes.includes(item.value); });
      setStatusText('workflow-error', () => tr`${Object.keys(workflow).length} 个节点 · ${textCount} 个文本输入`);
      $('workflow-error').classList.add('valid');
      $('workflow-json').setAttribute('aria-invalid', 'false');
      dismissNotification('workflow-json');
    } catch (error) {
      setStatusText('workflow-error', () => t("支持从 ComfyUI 导出的 API 工作流。"));
      $('workflow-error').classList.remove('valid');
      if ($('workflow-json').value.trim()) notifyError(error.message, { id: 'workflow-json' });
      $('workflow-json').setAttribute('aria-invalid', 'true');
      if (bindings !== null) {
        positive.replaceChildren(translatedOption('', "选择正向 text 输入")); negative.replaceChildren(translatedOption('', "选择负向 text 输入")); seed.replaceChildren(translatedOption('', "不绑定")); outputs.replaceChildren();
      }
      $('node-parameter-fields').replaceChildren();
      return false;
    }
    renderNodeParameters();
    return true;
  }

  function renderNodeParameters() {
    const target = $('node-parameter-fields'); target.replaceChildren();
    let workflow;
    try { workflow = readWorkflow(); } catch { return; }
    for (const node of editableNodeInputs(workflow, workflowInputOptions)) {
      const panel = document.createElement('fieldset'); panel.className = 'node-parameter-group';
      const legend = document.createElement('legend'); legend.textContent = `${node.id} · ${node.title}`; panel.append(legend);
      const grid = document.createElement('div'); grid.className = 'node-input-grid'; panel.append(grid);
      for (const input of node.inputs) {
        const label = document.createElement('label'); label.className = 'node-input-field';
        const caption = document.createElement('span'); caption.className = 'node-input-caption'; caption.textContent = input.name; label.append(caption);
        let control;
        if (Array.isArray(input.options) && input.options.length) {
          control = document.createElement('select');
          const values = input.options.includes(input.value) ? input.options : [input.value, ...input.options];
          control.append(...values.map((value) => option(String(value), String(value)))); control.value = String(input.value);
        } else if (input.kind === 'string' && (input.value.length > 100 || input.value.includes('\n'))) {
          control = document.createElement('textarea'); control.rows = 3; control.value = input.value; label.classList.add('wide-node-input');
        } else {
          control = document.createElement('input');
          control.type = input.kind === 'boolean' ? 'checkbox' : ['integer', 'number'].includes(input.kind) ? 'number' : 'text';
          if (input.kind === 'boolean') { control.checked = input.value; label.className = 'checkbox-label'; }
          else { control.value = String(input.value); if (control.type === 'number') { control.step = input.kind === 'integer' ? '1' : 'any'; control.required = true; } }
        }
        control.setAttribute('aria-label', `${node.id} ${node.classType} ${input.name}`);
        control.addEventListener('input', () => {
          try {
            const updated = changeNodeInput(readWorkflow(), node.id, input.name, input.kind === 'boolean' ? control.checked : control.value, input.kind);
            control.setCustomValidity(''); $('workflow-json').value = JSON.stringify(updated, null, 2);
            dismissNotification('workflow-json');
          } catch (error) { control.setCustomValidity(error.message); }
        });
        decorateElement(control, control.tagName.toLowerCase(), { type: control.type }); label.append(control); grid.append(label);
      }
      target.append(panel);
    }
  }

  function applyWorkflowDraft(draft, inputOptions = {}) {
    apiDraftChanged();
    workflowInputOptions = inputOptions;
    $('workflow-json').value = JSON.stringify(draft.workflow, null, 2);
    $('workflow-mode').value = 'custom';
    state.workflowId = null;
    state.workflowRevision = null;
    if (!draft.id) $('workflow-name').value = customWorkflowName(state.workflows.map(item => item.name));
    settingsDirty = true;
    updateBindings(draft.bindings, draft.output_nodes || []); updateWorkflowControls();
    setWorkflowPanelMode('parameters', false);
  }

  async function currentDefaultTemplate() {
    const version = workflowLoadRevision;
    const editedId = $('edit-backend').value;
    const url = $('backend-url').value;
    const checkpoint = $('default-checkpoint').value;
    const draft = { ...connectionDraft(), default_checkpoint:checkpoint };
    const id = editedId === '__new__' ? 'new' : editedId;
    const result = await api(`/api/backends/${encodeURIComponent(id)}/template`, { method:'POST', body:JSON.stringify(draft) });
    if (workflowLoadRevision !== version || $('edit-backend').value !== editedId || $('backend-url').value !== url || $('default-checkpoint').value !== checkpoint) throw new Error(t("生图 API、工作流或模型选择已变化，请重新读取默认节点参数。"));
    return result;
  }

  function renderWorkflowLibrary(selected = $('workflow-mode').value) {
    $('workflow-mode').replaceChildren(translatedOption('default', "默认文生图"), ...state.workflows.map((record) => option(`saved:${record.id}`, record.name)), translatedOption('custom', "自定义 API 工作流"));
    $('workflow-mode').value = [...$('workflow-mode').options].some((item) => item.value === selected) ? selected : 'custom';
    updateWorkflowControls();
  }
  async function loadWorkflowLibrary(selected = $('workflow-mode').value) {
    const result = await api('/api/workflows');
    state.workflows = result.workflows || [];
    renderWorkflowLibrary(selected);
  }
  async function selectWorkflow() {
    const selected = $('workflow-mode').value;
    const revision = ++workflowLoadRevision;
    settingsDirty = true;
    if (!selected.startsWith('saved:')) {
      if (selected === 'custom') $('workflow-name').value = customWorkflowName(state.workflows.map(item => item.name));
      state.workflowId = null;
      state.workflowRevision = null;
      setWorkflowPanelMode('parameters', false);
      updateWorkflowControls();
      return;
    }
    const select = $('workflow-mode'); select.disabled = true;
    settingsNotice(() => t("正在读取工作流…"), false, 'info');
    try {
      const record = await api(`/api/workflows/${encodeURIComponent(selected.slice(6))}`);
      if (workflowLoadRevision !== revision) return;
      applyWorkflowDraft(record);
      $('workflow-mode').value = selected;
      state.workflowId = record.id;
      state.workflowRevision = record.revision;
      $('workflow-name').value = record.name;
      setWorkflowPanelMode('parameters', false);
      updateWorkflowControls();
      dismissNotification('settings-operation');
    } catch (error) { settingsNotice(error.message, true); }
    finally { if (workflowLoadRevision === revision) select.disabled = false; }
  }
  function connectionDraft() {
    const draft = { name: $('backend-name').value.trim(), kind: $('backend-kind').value, base_url: $('backend-url').value.trim() };
    if (!draft.name || !draft.base_url) throw new Error(t("请填写 API 名称和 API 地址。"));
    Object.assign(draft, apiKeyFields($('backend-key').value, hasSavedApiKey));
    return draft;
  }
  function draftBackend({ saveWorkflow = false } = {}) {
    const draft = connectionDraft();
    if (draft.kind !== 'comfyui') return { ...draft, ...cloudConfigFields(draft.kind, Object.fromEntries(Object.entries(cloudInputIds).map(([key,id]) => [key,$(id).value]))) };
    draft.workflow_mode = $('workflow-mode').value === 'default' ? 'default' : 'custom';
    if (draft.workflow_mode === 'default') { draft.default_checkpoint = $('default-checkpoint').value; return draft; }
    const invalidParameter = $('node-parameters').querySelector(':invalid');
    if (invalidParameter) { setNodeParametersExpanded(true); setWorkflowPanelMode('parameters', false); invalidParameter.reportValidity(); invalidParameter.focus(); throw new Error(t("请先修正节点参数中的无效输入。")); }
    const workflow = readWorkflow();
    const positive = parseBinding($('binding-positive').value), negative = parseBinding($('binding-negative').value), seed = parseBinding($('binding-seed').value);
    if (!positive) throw new Error(t("请选择正向提示词输入。"));
    if (!negative) throw new Error(t("请选择负向提示词输入，以便准确记录本次实际使用的提示词。"));
    if (bindingValue(positive) === bindingValue(negative)) throw new Error(t("正向和负向提示词不能绑定同一个输入。"));
    const custom = { ...draft, workflow, bindings: { positive, negative, seed }, output_nodes: [...$('output-nodes').selectedOptions].map((item) => item.value) };
    return saveWorkflow ? { ...custom, ...workflowSaveFields(custom, $('workflow-name').value, state.workflowId ? { id: state.workflowId, revision: state.workflowRevision } : null) } : custom;
  }
  $('edit-backend').addEventListener('change', () => loadBackend($('edit-backend').value));
  $('backend-kind').addEventListener('change', switchBackendType);
  $('backend-key').addEventListener('focus', () => { if (hasSavedApiKey && $('backend-key').value === API_KEY_MASK) $('backend-key').select(); });
  $('backend-key').addEventListener('input', () => {
    try { apiKeyFields($('backend-key').value, hasSavedApiKey); $('backend-key').setCustomValidity(''); }
    catch (error) { $('backend-key').setCustomValidity(error.message); }
  });
  $('workflow-mode').addEventListener('change', selectWorkflow);
  $('toggle-workflow-json').addEventListener('click', () => setWorkflowPanelMode($('node-parameters').dataset.editorMode === 'json' ? 'parameters' : 'json'));
  $('workflow-json').addEventListener('input', () => {
    updateWorkflowControls();
    try {
      readWorkflow();
      $('workflow-json').setAttribute('aria-invalid', 'false');
      dismissNotification('workflow-json');
    } catch (error) {
      $('workflow-json').setAttribute('aria-invalid', 'true');
      notifyError(error.message, { id: 'workflow-json' });
    }
  });
  $('workflow-json').addEventListener('change', () => { updateBindings(); updateWorkflowControls(); });
  $('edit-default-parameters').addEventListener('click', async () => {
    const button = $('edit-default-parameters'); button.disabled = true; settingsNotice(() => t("正在读取默认工作流参数…"), false, 'info');
    try { const template = await currentDefaultTemplate(); applyWorkflowDraft(template, template.input_options || {}); setNodeParametersExpanded(true); settingsNotice(() => t("已展开节点参数，保存后生效。")); }
    catch (error) { settingsNotice(error.message, true); }
    finally { button.disabled = false; }
  });
  $('reload-workflows').addEventListener('click', async () => {
    const button = $('reload-workflows'); button.disabled = true;
    try { await loadWorkflowLibrary(); settingsNotice(() => t("工作流列表已刷新。")); }
    catch (error) { settingsNotice(error.message, true); }
    finally { button.disabled = false; }
  });
  $('delete-workflow').addEventListener('click', async () => {
    const id = state.workflowId, revision = state.workflowRevision;
    const workflow = state.workflows.find(item => item.id === id);
    if (state.saving || !workflow || !revision) return;
    if (!await confirmAction(tr`删除工作流「${workflow.name}」？已配置生图 API 保留当前工作流参数，历史任务和图片保留。`)) return;
    state.saving = true; $('settings-form').inert = true;
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
    finally { state.saving = false; $('settings-form').inert = false; }
  });
  $('delete-backend').addEventListener('click', async () => {
    const id = $('edit-backend').value, backend = state.backends.find(item => item.id === id);
    if (state.saving || !backend) return;
    if (!await confirmAction(tr`删除 API 配置「${backend.name}」？${settingsDirty ? t("当前未保存的生图 API 修改将放弃。") : ''}历史任务和图片保留，已有任务继续使用提交时的配置。`)) return;
    state.saving = true; $('settings-form').inert = true;
    try {
      await api(`/api/backends/${encodeURIComponent(id)}`, { method: 'DELETE', body: '{}' });
      state.backends = state.backends.filter(item => item.id !== id);
      renderBackends(); loadBackend($('edit-backend').value); renderArtifacts();
      settingsNotice(() => t("API 配置已删除。"));
    } catch (error) { settingsNotice(error.message, true); }
    finally { state.saving = false; $('settings-form').inert = false; }
  });
  $('workflow-file').addEventListener('change', async (event) => {
    const file = event.target.files[0]; if (!file) return;
    const revision = workflowLoadRevision;
    try {
      const source = await file.text();
      if (revision !== workflowLoadRevision) return;
      $('workflow-json').value = source;
      settingsDirty = true;
      workflowInputOptions = {};
      const valid = updateBindings();
      updateWorkflowControls();
      setNodeParametersExpanded(true);
      if (!valid) setWorkflowPanelMode('json', false);
    } catch (error) { settingsNotice(error.message, true); }
    finally { event.target.value = ''; }
  });
  $('load-models').addEventListener('click', async () => {
    const button = $('load-models'); button.disabled = true; button.setAttribute('aria-busy', 'true'); button.querySelector('svg')?.classList.add('animate-spin');
    const editedId = $('edit-backend').value;
    const baseUrl = $('backend-url').value;
    try {
      const draft = connectionDraft(); const id = editedId === '__new__' ? 'new' : editedId;
      const result = await api(`/api/backends/${encodeURIComponent(id)}/models`, { method: 'POST', body: JSON.stringify(draft) });
      if ($('edit-backend').value !== editedId || $('backend-url').value !== baseUrl) return;
      const selected = $('default-checkpoint').value;
      const models = (result.models || []).filter((model) => typeof model === 'string');
      $('default-checkpoint').replaceChildren(translatedOption('', "自动选择第一个可用模型"), ...models.map((model) => option(model, model)));
      if (models.includes(selected)) $('default-checkpoint').value = selected;
        if (!models.length) notify(() => t("生图 API 没有可用模型，请在 ComfyUI 中配置。"), { id: 'model-list', kind: 'warning' });
      else dismissNotification('model-list');
      button.dataset.tooltip = tr`刷新模型，当前 ${models.length} 个可用`;
    } catch (error) { notifyError(() => tr`读取失败：${error.message}`, { id: 'model-list' }); }
    finally { button.disabled = false; button.removeAttribute('aria-busy'); button.querySelector('svg')?.classList.remove('animate-spin'); }
  });
  $('test-backend').addEventListener('click', async () => {
    const revision = apiDraftRevision;
    publishUiState({ apiTestPending: true, apiTestedRevision: -1 });
    const button = $('test-backend'); button.disabled = true; settingsNotice(() => t("正在测试连接…"), false, 'info');
    try {
      const draft = draftBackend();
      const id = $('edit-backend').value === '__new__' ? 'new' : $('edit-backend').value;
      const result = await api(`/api/backends/${encodeURIComponent(id)}/check`, { method: 'POST', body: JSON.stringify(draft) });
      if (result.ok && revision === apiDraftRevision) publishUiState({ apiTestedRevision: revision });
      settingsNotice(result.message || (result.ok ? t("连接成功。") : t("连接失败。")), !result.ok);
      if (id !== 'new' && result.ok) showBackendAvailability(true);
    }
    catch (error) { settingsNotice(error.message, true); }
    finally { button.disabled = false; publishUiState({ apiTestPending: false }); }
  });
  $('settings-form').addEventListener('invalid', (event) => {
    if (event.target.closest('#node-parameters')) setNodeParametersExpanded(true);
  }, true);
  $('settings-form').addEventListener('submit', async (event) => {
    event.preventDefault(); if (state.saving) return;
    const revision = apiDraftRevision; publishUiState({ apiSavePending: true });
    state.saving = true; $('save-backend').disabled = true; $('settings-form').inert = true;
    try {
      const draft = draftBackend({ saveWorkflow: true });
      const id = $('edit-backend').value === '__new__' ? crypto.randomUUID() : $('edit-backend').value;
      const result = await api(`/api/backends/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(draft) });
      const backend = result.backend || result;
      const index = state.backends.findIndex((item) => item.id === backend.id);
      if (index >= 0) state.backends[index] = backend; else state.backends.push(backend);
      renderBackends(); $('edit-backend').value = backend.id; $('generate-backend').value = backend.id;
      updateGenerationHints();
      await loadWorkflowLibrary(backend.workflow_id ? `saved:${backend.workflow_id}` : 'default');
      loadBackend(backend.id, true); renderArtifacts();
      if (revision === apiDraftRevision) publishUiState({ apiSavedRevision: revision });
      await loadRoamSettings({ preserveDraft: true });
      settingsNotice(() => backend.workflow_name ? tr`生图 API 与工作流「${backend.workflow_name}」已保存。` : t("生图 API 已保存。"));
    } catch (error) { settingsNotice(error.message, true); }
    finally { state.saving = false; $('save-backend').disabled = false; $('settings-form').inert = false; publishUiState({ apiSavePending: false }); }
  });

  $('settings-form').addEventListener('input', () => { settingsDirty = true; apiDraftChanged(); });
  $('settings-form').addEventListener('change', event => { settingsDirty = true; if (event.target.id !== 'edit-backend') apiDraftChanged(); });

  return {
    renderBackends, loadBackend, loadWorkflowLibrary,
    get initialized() { return settingsInitialized; },
    get dirty() { return settingsDirty; },
  };
}
