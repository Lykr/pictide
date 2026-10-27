import { createRequestId } from '../shared/request-id.mjs';
import { t, tr } from '../i18n/index.mjs';
import { createModel } from '../shared/model.mjs';
import { requestIdentity } from './feed-controls.mjs';
import { ruleVisibility, nextRuleCounters, submissionDecision, afterPromptEdit } from './rule-controls.mjs';
import { generationCount, generationRepetitions, generationSizeFields } from './generation-controls.mjs';
import { backendCapabilities } from './backend-controls.mjs';
import { notify, notifyError, dismissNotification } from '../shared/notifications.mjs';

/** Own the Generate form, prompt counters, and uncertain submissions. */
export function createGenerationController({ state, api, getRoamSettings, renderJobs, refresh }) {
  const uncertainRequests = new Map();
  const model = createModel({ draft: { backendId: '', canvasSize: '', source: 'manual', presetId: '', mode: 'random_each_run', ruleSeed: '0', step: '0', seedControl: 'fixed', stepControl: 'increment', maxSteps: '100', automatic: true, positive: '', negative: '', seed: '-1', count: '1', repetitions: '1' }, presets: [], busy: false, loadingPresets: false, report: null, rendered: null, promptNote: null, feedback: {} });
  const { draft } = model.data;
  const changed = model.changed;
  let composeBusy = false, composeDirty = false, ruleConfigsLoaded = false;
  let backendSignature;
  const feedback = name => ({ show(kind, label, message) {
    model.data.feedback[name] = kind === 'pending' ? { kind, label } : null; changed();
    if (kind !== 'pending') notify(message || label, { id: `generate-${name}`, kind });
  } });
  const generateFeedback = feedback('submit'), cancelPendingFeedback = feedback('cancel'), promptFeedback = feedback('prompts'), configFeedback = feedback('presets');
  function updateGenerationHints() {
    if (!state.backends.some(item => item.id === draft.backendId)) { draft.backendId = state.backends[0]?.id || ''; draft.canvasSize = ''; }
    const signature = JSON.stringify(state.backends.find(item => item.id === draft.backendId));
    if (signature !== backendSignature) model.data.rendered = null;
    backendSignature = signature;
    changed();
  }
  function updateRuleControls() { changed(); }
  async function loadRuleConfigs(feedback = false) {
    if (model.data.loadingPresets) return; model.data.loadingPresets = true; changed();
    if (feedback) configFeedback.show('pending', t("正在刷新…"));
    try {
      const listing = await api('/api/candidate/presets');
      const presets = listing.presets;
      const selected = draft.presetId || getRoamSettings().preset_id;
      model.data.presets = presets;
      draft.presetId = presets.some(item => item.id === selected) ? selected : presets[0]?.id || '';

      dismissNotification('rule-config-error');
      ruleConfigsLoaded = true; updateRuleControls();
      if (feedback) configFeedback.show('success', t("已刷新"));
    } catch (error) {

      if (!feedback) notifyError(() => tr`预设读取失败：${error.message}`, { id: 'rule-config-error' });
      if (feedback) configFeedback.show('error', t("刷新失败"), tr`刷新失败：${error.message}`);
    }
    finally { model.data.loadingPresets = false; changed(); }
  }

  function ruleNumber(raw, label, minimum, maximum) {
    const value = Number(raw);
    if (!raw.trim() || !Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error(tr`${label}须为 ${minimum}–${maximum} 之间的整数。`);
    return value;
  }

  function readRuleGeneration() {
    if (!draft.presetId) throw new Error(t("请先选择生成预设，或在提示词页新建预设。"));
    const mode = draft.mode;
    const current = {
      mode, seed: mode === 'random_each_run' ? Number(draft.ruleSeed) || 0 : ruleNumber(draft.ruleSeed, t("提示词种子"), 0, Number.MAX_SAFE_INTEGER),
      step: mode === 'sequence' ? ruleNumber(draft.step, t("帧序号"), 0, 1000) : Number(draft.step) || 0,
      seedControl: draft.seedControl, stepControl: draft.stepControl,
    };
    const payload = { preset_id: draft.presetId, mode, seed: mode === 'random_each_run' ? 0 : current.seed, max_steps: ruleNumber(draft.maxSteps, t("搜索上限"), 1, 1000000), sequence_step: mode === 'sequence' ? current.step : 0 };
    return { current, payload };
  }

  function presentRulePrompts(result, counters, current) {
    if (typeof result.positive !== 'string' || typeof result.negative !== 'string') throw new Error(t("候选服务没有返回完整的正负提示词。"));
    model.data.rendered = result.rendered || null;
    draft.positive = result.positive; draft.negative = result.negative;
    draft.ruleSeed = String(counters.seed); draft.step = String(counters.step);

    const { positive, negative, ...report } = result;
    model.data.report = report;
    const usedSeed = () => current.mode === 'sequence' ? tr`序列种子 ${result.sequence?.seed ?? current.seed} · 帧 ${result.sequence?.step ?? current.step} · 本帧有效种子 ${result.seed}` : tr`本次提示词种子 ${result.seed}`;
    model.data.promptNote = usedSeed; changed();

  }

  async function generateRulePrompts() {
    const { current, payload } = readRuleGeneration();
    model.data.promptNote = null; changed();
    const result = await api('/api/candidate/generate', { method: 'POST', body: JSON.stringify({ ...payload, backend_id: draft.backendId }) });
    const counters = nextRuleCounters(current, result);
    presentRulePrompts(result, counters, current);
    composeDirty = true;
    return result;
  }

  function setComposeBusy(value) { composeBusy = value; model.data.busy = value; changed(); }
  async function submit() {
    if (composeBusy) return; setComposeBusy(true);
    generateFeedback.show('pending', t("正在提交…"));
    let operation;
    try {
      const backend = state.backends.find((item) => item.id === draft.backendId);
      const capabilities = backendCapabilities(backend);
      const natural = backend?.prompt_type === "natural_language";
      if (natural) generateFeedback.show("pending", t("正在准备提示词…"));
      const seed = capabilities.cloud && !capabilities.seed ? -1 : Number(draft.seed);
      if (!(capabilities.cloud && !capabilities.seed) && (!draft.seed.trim() || !Number.isSafeInteger(seed) || seed < -1)) throw new Error(t("种子须为 -1 或非负安全整数。"));
      const count = generationCount(draft.count);
      const repetitions = generationRepetitions(draft.repetitions);
      const automatic = draft.source === 'rules' && draft.automatic;
      const rule = automatic ? readRuleGeneration() : null;
      const fromRules = draft.source === 'rules';
      const negative = !natural && capabilities.cloud && !capabilities.negative_prompt && !fromRules ? '' : draft.negative;
      if (!natural && !automatic && capabilities.cloud && negative.trim()) throw new Error(t('此生图 API 不支持负向提示词，请在候选预设中移除负向词，或改用手动正向提示词。'));
      const payload = { backend_id: draft.backendId, positive: draft.positive, negative, seed, count, repetitions,
        ...generationSizeFields(draft.canvasSize, backend),
        ...(!automatic && natural && model.data.rendered ? { preparation_id: model.data.rendered.preparation_id } : {}),
        ...(rule ? { candidate: { ...rule.payload, seed_control: rule.current.seedControl, step_control: rule.current.stepControl } } : {}) };
      if (!payload.positive.trim() && !automatic) throw new Error(t("请输入正向提示词，或使用共现候选生成提示词。"));
      const decision = submissionDecision(payload, uncertainRequests, automatic);
      if (!natural && !automatic && payload.negative.trim() && !capabilities.negative_prompt) throw new Error(t("当前生图 API 未绑定负向输入。请清空负向提示词，或在生图 API 设置中指定负向绑定。"));
      operation = decision.retry || requestIdentity(payload, uncertainRequests, createRequestId);
      const hasOtherUncertain = uncertainRequests.size && !uncertainRequests.has(operation.key);
      uncertainRequests.set(operation.key, operation);
      const result = await api('/api/jobs', { method: 'POST', body: JSON.stringify(operation.payload) });
      uncertainRequests.delete(operation.key);
      if (result.candidate_result && result.next_candidate) {
        presentRulePrompts(result.candidate_result, { seed: result.next_candidate.seed, step: result.next_candidate.sequence_step },
          { mode: operation.payload.candidate.mode, seed: operation.payload.candidate.seed, step: operation.payload.candidate.sequence_step });
      }
      model.data.rendered = result.rendered || null;
      if (capabilities.seed && Number.isSafeInteger(result.next_seed)) draft.seed = String(result.next_seed);
      composeDirty = false;
      const submitted = result.jobs || [result.job];
      const submittedIds = new Set(submitted.map(job => job.id));
      state.jobs = [...submitted, ...state.jobs.filter((job) => !submittedIds.has(job.id))]; renderJobs();
      generateFeedback.show(hasOtherUncertain ? 'warning' : 'success', hasOtherUncertain ? t("已提交 · 有待确认任务") : t("已提交"),
        tr`已提交 ${repetitions} 轮，每轮 ${count} 个生成任务；完成后在生成结果中查看。${hasOtherUncertain ? t("此前提交的结果仍待确认，请查看任务。") : ''}`);
      refresh(true);
    } catch (error) {
      const uncertain = operation && !(error.status >= 400 && error.status < 500);
      if (operation && !uncertain) uncertainRequests.delete(operation.key);
      generateFeedback.show(uncertain ? 'warning' : 'error', uncertain ? t("结果待确认 · 重试") : t("提交失败 · 重试"),
        uncertain ? tr`提交结果尚未确认：${error.message}。相同内容再次点击生成会复用请求 ID，避免重复任务；修改内容则提交新任务。` : error.message);
    }
    finally { setComposeBusy(false); }
  }
  async function cancelPending() {
    if (composeBusy) return;
    setComposeBusy(true); cancelPendingFeedback.show('pending', t("正在取消…"));
    try {
      const result = await api('/api/jobs/cancel-pending', { method: 'POST', body: '{}' });
      cancelPendingFeedback.show('success', result.cancelled_count ? tr`已取消 ${result.cancelled_count} 个` : t("暂无待取消任务"),
        tr`已取消 ${result.cancelled_count} 个待执行的生成任务；已开始的任务和漫游预取保持不变。`);
      await refresh(true);
    } catch (error) { cancelPendingFeedback.show('error', t("取消失败 · 重试"), error.message); }
    finally { setComposeBusy(false); }
  }
  async function drawPrompts() {
    if (composeBusy) return; setComposeBusy(true);
    promptFeedback.show('pending', t(state.backends.find(item => item.id === draft.backendId)?.prompt_type === "natural_language" ? "正在准备提示词…" : "正在抽取…"));
    try { await generateRulePrompts(); promptFeedback.show('success', t("已抽取")); }
    catch (error) { model.data.promptNote = null; promptFeedback.show('error', t("抽取失败 · 重试"), tr`抽取失败：${error.message}`); }
    finally { setComposeBusy(false); }
  }
  function edit(key, value) {
    if (key === 'backendId' && value !== draft.backendId) draft.canvasSize = '';
    draft[key] = value; composeDirty = true;
    if (['backendId', 'positive', 'negative', 'presetId', 'source', 'mode'].includes(key)) model.data.rendered = null;
    if (key === 'backendId') updateGenerationHints();
    if (['positive', 'negative'].includes(key)) {
      const wasAutomatic = draft.source === 'rules' && draft.automatic;
      draft.automatic = afterPromptEdit(draft.source, draft.automatic);
      if (wasAutomatic) notify(() => t('自动抽取已关闭，使用当前文本。'), { id: 'prompt-edit', kind: 'info' });
    }
    changed();
    if (key === 'source' && value === 'rules' && !ruleConfigsLoaded) loadRuleConfigs();
  }

  return {
    model, edit, submit, cancelPending, drawPrompts, updateGenerationHints, updateRuleControls, loadRuleConfigs,
    invalidatePrompt() { model.data.rendered = null; changed(); },
    selectPreset(id) { model.data.rendered = null; draft.presetId = id || model.data.presets[0]?.id || ''; changed(); },
    selectBackend(id) { if (id !== draft.backendId) draft.canvasSize = ''; draft.backendId = id; model.data.rendered = null; updateGenerationHints(); },
    observeJobs() {
      for (const [key, request] of uncertainRequests) {
        if (request.payload.repetitions === undefined && state.jobs.some(job => job.request_id === request.payload.request_id)) uncertainRequests.delete(key);
      }
    },
    get dirty() { return composeDirty || uncertainRequests.size > 0; },
  };
}
