import { t, tr } from '../i18n/index.mjs';
import { createIcon } from '../dom-primitives';
import { createButtonFeedback } from './button-feedback.mjs';
import { requestIdentity } from './feed-controls.mjs';
import { ruleVisibility, nextRuleCounters, submissionDecision, afterPromptEdit } from './rule-controls.mjs';
import { generationCount, generationRepetitions } from './generation-controls.mjs';
import { backendCapabilities } from './backend-controls.mjs';
import { notify, notifyError, dismissNotification } from '../shared/notifications.mjs';
import { $, option, translatedOption, describeAction, inlineStatus } from './dom-utils.mjs';

/** Own the Generate form, prompt counters, and uncertain submissions. */
export function createGenerationController({ state, api, getRoamSettings, renderJobs, refresh }) {
  const uncertainRequests = new Map();
  const generateFeedback = createButtonFeedback($('generate'), createIcon);
  const cancelPendingFeedback = createButtonFeedback($('cancel-pending'), createIcon);
  const promptFeedback = createButtonFeedback($('generate-prompts'), createIcon);
  const configFeedback = createButtonFeedback($('reload-rule-configs'), createIcon);
  let composeBusy = false;
  let composeDirty = false;
  let ruleConfigsLoaded = false;
  function updateGenerationHints() {
    const backend = state.backends.find((item) => item.id === $('generate-backend').value);
    const capabilities = backendCapabilities(backend);
    const noSeed = !!backend && !capabilities.seed;
    const noNegative = !!backend && !capabilities.negative_prompt;
    $('seed').disabled = noSeed;
    $('seed-field').hidden = capabilities.cloud && noSeed;
    $('negative-field').hidden = capabilities.cloud && noNegative;
    $('negative').disabled = capabilities.cloud && noNegative;
    $('generation-cloud-note').hidden = !capabilities.cloud;
    inlineStatus('generation-capability-note', () => t('此生图 API 不支持负向提示词和图像种子；本次仅发送正向提示词，原输入保留。候选预设中的负向词仍需移除。'), capabilities.cloud);
    describeAction($('seed-note'), noSeed ? t("未绑定种子输入，将使用工作流自身的种子设置。") : t("-1 每个任务随机；非负值按任务递增，跨轮延续。实际种子随图片保存。"));
    $('negative-binding-note').hidden = !backend || !noNegative || capabilities.cloud;
  }

  function updateRuleControls() {
    const visibility = ruleVisibility($('prompt-source').value, $('rule-mode').value, $('auto-prompts').checked);
    $('rule-section').hidden = !visibility.rules;
    $('rule-section').disabled = !visibility.rules;
    $('rule-seed-fields').hidden = !visibility.seed;
    $('rule-seed-fields').disabled = !visibility.seed;
    $('rule-sequence-fields').hidden = !visibility.sequence;
    $('rule-sequence-fields').disabled = !visibility.sequence;
    $('positive').required = visibility.positiveRequired;
  }

  async function loadRuleConfigs(feedback = false) {
    const button = $('reload-rule-configs'); if (button.disabled) return; button.disabled = true;
    if (feedback) configFeedback.show('pending', t("正在刷新…"));
    try {
      const listing = await api('/api/candidate/presets');
      const presets = listing.presets;
      const selected = $('rule-config').value || getRoamSettings().preset_id;
      $('rule-config').replaceChildren(...(presets.length ? presets.map(item => option(item.id, item.name)) : [translatedOption('', "请先新建生成预设")]));
      $('rule-config').value = presets.some(item => item.id === selected) ? selected : presets[0]?.id || '';
      inlineStatus('rule-config-note', () => t("还没有生成预设，请在提示词页新建。"), !presets.length);
      dismissNotification('rule-config-error');
      ruleConfigsLoaded = true; updateRuleControls();
      if (feedback) configFeedback.show('success', t("已刷新"));
    } catch (error) {
      inlineStatus('rule-config-note', '', false);
      if (!feedback) notifyError(() => tr`预设读取失败：${error.message}`, { id: 'rule-config-error' });
      if (feedback) configFeedback.show('error', t("刷新失败"), tr`刷新失败：${error.message}`);
    }
    finally { button.disabled = false; }
  }

  function ruleNumber(id, label, minimum, maximum) {
    const raw = $(id).value;
    const value = Number(raw);
    if (!raw.trim() || !Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error(tr`${label}须为 ${minimum}–${maximum} 之间的整数。`);
    return value;
  }

  function readRuleGeneration() {
    if (!$('rule-config').value) throw new Error(t("请先选择生成预设，或在提示词页新建预设。"));
    const mode = $('rule-mode').value;
    const current = {
      mode, seed: mode === 'random_each_run' ? Number($('rule-seed').value) || 0 : ruleNumber('rule-seed', t("提示词种子"), 0, Number.MAX_SAFE_INTEGER),
      step: mode === 'sequence' ? ruleNumber('sequence-step', t("帧序号"), 0, 1000) : Number($('sequence-step').value) || 0,
      seedControl: $('rule-seed-control').value, stepControl: $('sequence-control').value,
    };
    const payload = { preset_id: $('rule-config').value, mode, seed: mode === 'random_each_run' ? 0 : current.seed, max_steps: ruleNumber('rule-max-steps', t("搜索上限"), 1, 1000000), sequence_step: mode === 'sequence' ? current.step : 0 };
    return { current, payload };
  }

  function presentRulePrompts(result, counters, current) {
    if (typeof result.positive !== 'string' || typeof result.negative !== 'string') throw new Error(t("候选服务没有返回完整的正负提示词。"));
    $('positive').value = result.positive; $('negative').value = result.negative;
    $('rule-seed').value = String(counters.seed); $('sequence-step').value = String(counters.step);
    $('rule-report').hidden = false;
    const { positive, negative, ...report } = result;
    $('rule-report-content').textContent = JSON.stringify(report, null, 2);
    const usedSeed = () => current.mode === 'sequence' ? tr`序列种子 ${result.sequence?.seed ?? current.seed} · 帧 ${result.sequence?.step ?? current.step} · 本帧有效种子 ${result.seed}` : tr`本次提示词种子 ${result.seed}`;
    inlineStatus('rule-generation-note', usedSeed);
    $('rule-generation-note').dataset.tooltip = t("计数已更新为下次值，当前提示词可直接编辑。");
  }

  async function generateRulePrompts() {
    const { current, payload } = readRuleGeneration();
    inlineStatus('rule-generation-note', '', false);
    const result = await api('/api/candidate/generate', { method: 'POST', body: JSON.stringify(payload) });
    const counters = nextRuleCounters(current, result);
    presentRulePrompts(result, counters, current);
    composeDirty = true;
    return result;
  }

  function setComposeBusy(value) {
    composeBusy = value; $('generate-form').inert = value;
    $('generate').disabled = value || !state.backends.length;
    $('generate-prompts').disabled = value;
    $('cancel-pending').disabled = value;
  }
  $('generate-form').addEventListener('submit', async (event) => {
    event.preventDefault(); if (composeBusy) return; setComposeBusy(true);
    generateFeedback.show('pending', t("正在提交…"));
    let operation;
    try {
      const backend = state.backends.find((item) => item.id === $('generate-backend').value);
      const capabilities = backendCapabilities(backend);
      const seed = capabilities.cloud && !capabilities.seed ? -1 : Number($('seed').value);
      if (!(capabilities.cloud && !capabilities.seed) && (!$('seed').value.trim() || !Number.isSafeInteger(seed) || seed < -1)) throw new Error(t("种子须为 -1 或非负安全整数。"));
      const count = generationCount($('generation-count').value);
      const repetitions = generationRepetitions($('generation-repetitions').value);
      const automatic = $('prompt-source').value === 'rules' && $('auto-prompts').checked;
      const rule = automatic ? readRuleGeneration() : null;
      const fromRules = $('prompt-source').value === 'rules';
      const negative = capabilities.cloud && !capabilities.negative_prompt && !fromRules ? '' : $('negative').value;
      if (!automatic && capabilities.cloud && negative.trim()) throw new Error(t('此生图 API 不支持负向提示词，请在候选预设中移除负向词，或改用手动正向提示词。'));
      const payload = { backend_id: $('generate-backend').value, positive: $('positive').value, negative, seed, count, repetitions,
        ...(rule ? { candidate: { ...rule.payload, seed_control: rule.current.seedControl, step_control: rule.current.stepControl } } : {}) };
      if (!payload.positive.trim() && !automatic) throw new Error(t("请输入正向提示词，或使用共现候选生成提示词。"));
      const decision = submissionDecision(payload, uncertainRequests, automatic);
      if (!automatic && payload.negative.trim() && !capabilities.negative_prompt) throw new Error(t("当前生图 API 未绑定负向输入。请清空负向提示词，或在生图 API 设置中指定负向绑定。"));
      operation = decision.retry || requestIdentity(payload, uncertainRequests, () => crypto.randomUUID());
      const hasOtherUncertain = uncertainRequests.size && !uncertainRequests.has(operation.key);
      uncertainRequests.set(operation.key, operation);
      const result = await api('/api/jobs', { method: 'POST', body: JSON.stringify(operation.payload) });
      uncertainRequests.delete(operation.key);
      if (result.candidate_result && result.next_candidate) {
        presentRulePrompts(result.candidate_result, { seed: result.next_candidate.seed, step: result.next_candidate.sequence_step },
          { mode: operation.payload.candidate.mode, seed: operation.payload.candidate.seed, step: operation.payload.candidate.sequence_step });
      }
      if (capabilities.seed && Number.isSafeInteger(result.next_seed)) $('seed').value = String(result.next_seed);
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
  });
  $('cancel-pending').addEventListener('click', async () => {
    if (composeBusy) return;
    setComposeBusy(true); cancelPendingFeedback.show('pending', t("正在取消…"));
    try {
      const result = await api('/api/jobs/cancel-pending', { method: 'POST', body: '{}' });
      cancelPendingFeedback.show('success', result.cancelled_count ? tr`已取消 ${result.cancelled_count} 个` : t("暂无待取消任务"),
        tr`已取消 ${result.cancelled_count} 个待执行的生成任务；已开始的任务和漫游预取保持不变。`);
      await refresh(true);
    } catch (error) { cancelPendingFeedback.show('error', t("取消失败 · 重试"), error.message); }
    finally { setComposeBusy(false); }
  });
  $('prompt-source').addEventListener('change', async () => { updateRuleControls(); if ($('prompt-source').value === 'rules' && !ruleConfigsLoaded) await loadRuleConfigs(); });
  $('rule-mode').addEventListener('change', updateRuleControls);
  $('auto-prompts').addEventListener('change', updateRuleControls);
  $('reload-rule-configs').addEventListener('click', () => loadRuleConfigs(true));
  $('generate-prompts').addEventListener('click', async () => {
    if (composeBusy) return; setComposeBusy(true);
    promptFeedback.show('pending', t("正在抽取…"));
    try { await generateRulePrompts(); promptFeedback.show('success', t("已抽取")); }
    catch (error) { inlineStatus('rule-generation-note', '', false); promptFeedback.show('error', t("抽取失败 · 重试"), tr`抽取失败：${error.message}`); }
    finally { setComposeBusy(false); }
  });
  for (const id of ['positive', 'negative']) $(id).addEventListener('input', () => {
    const wasAutomatic = $('prompt-source').value === 'rules' && $('auto-prompts').checked;
    $('auto-prompts').checked = afterPromptEdit($('prompt-source').value, $('auto-prompts').checked);
    if ($('prompt-source').value === 'rules') {
      if (wasAutomatic) notify(() => t("自动抽取已关闭，使用当前文本。"), { id: 'prompt-edit', kind: 'info' });
      $('rule-generation-note').dataset.tooltip = t("抽取报告对应编辑前的结果，重新勾选自动抽取可恢复共现生成。");
    }
    updateRuleControls();
  });
  $('generate-form').addEventListener('input', () => { composeDirty = true; });
  $('generate-form').addEventListener('change', () => { composeDirty = true; });

  $('generate-backend').addEventListener('change', updateGenerationHints);

  return {
    updateGenerationHints, updateRuleControls, loadRuleConfigs,
    observeJobs() {
      for (const [key, request] of uncertainRequests) {
        if (request.payload.repetitions === undefined && state.jobs.some(job => job.request_id === request.payload.request_id)) uncertainRequests.delete(key);
      }
    },
    get dirty() { return composeDirty || uncertainRequests.size > 0; },
  };
}
