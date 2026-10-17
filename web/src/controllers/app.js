import { loadTheme } from './theme.mjs';
import { createButtonFeedback } from './button-feedback.mjs';
import { decorateElement, createIcon } from "../dom-primitives";
import { confirmAction } from '../components/confirm-action';
import { destinationIndex, keyboardAction, feedbackValue, requestIdentity, configuredWorkflowMode, effectiveWorkflowMode } from './feed-controls.mjs';
import { ruleVisibility, nextRuleCounters, submissionDecision, afterPromptEdit } from './rule-controls.mjs';
import { editableNodeInputs, changeNodeInput, workflowSaveFields } from './workflow-controls.mjs';
import { parseWorkflowDraft, retainedWorkflowBindings } from './workflow-panel.mjs';
import { applyArtifactPage, observeArtifactRevision, retentionDays } from './history-controls.mjs';
import { API_KEY_MASK, apiKeyFields, customWorkflowName } from './settings-controls.mjs';
import { prefetchCount, maxHistoryImages, createRefillCoordinator, isTemporaryRefillError, mergeRoamDraft, likedTagsWait, roamGenerationChanged } from './roam-controls.mjs';
import { generationCount, generationRepetitions, artifactPath } from './generation-controls.mjs';
import { createGalleryCursors, createNextImageWait, roamArtifactPath, roamBoundaryAction, resolveGalleryCursor } from './roam-navigation.mjs';
import { playbackInterval, createRoamPlayback } from './roam-playback.mjs';
import { createImmersiveViewer } from './immersive-controls.mjs';
import { createJobPager } from './job-pages.mjs';

const $ = (id) => document.getElementById(id);
const state = { backends: [], jobs: [], artifacts: [], view: 'feed', activeId: null, databasePath: '', polling: false, saving: false, currentImage: null, feedbackPending: false, feedbackRevision: 0 };
const galleryCursors = createGalleryCursors();
const nextImageWait = createNextImageWait();
Object.defineProperty(state, 'activeId', { get: () => galleryCursors.get(state.view), set: id => selectImage(id) });
let roamWindowLoading = false, roamBlocked = false, viewRevision = 0;
let roamViewPending = Promise.resolve();
function selectImage(id, view = state.view) {
  const record = galleryCursors.select(view, id);
  if (record) roamViewPending = api('/api/roam/view', { method: 'PUT', keepalive: true, body: JSON.stringify(record) }).catch(error => showNotice(`观看位置保存失败：${error.message}`, true));
}
state.likedArtifacts = [];
state.likedError = "";
state.generatedArtifacts = [];
state.generatedLoaded = false;
state.generatedError = '';
state.generatedMutationPending = false;
state.generatedMutationError = '';
state.workflows = [];
state.settingsSection = 'general';
state.pages = { feed: { hasMore: false, cursor: null, total: 0, loadedMore: false }, liked: { hasMore: false, cursor: null, total: 0, loadedMore: false }, generate: { hasMore: false, cursor: null, total: 0, loadedMore: false } };
state.loadingMore = false;
state.artifactRevision = 0;
const uncertainRequests = new Map();
const statusNames = { queued: '等待生成', submitting: '正在提交', running: '正在生成', completed: '已完成', failed: '生成失败', cancelled: '已取消', unknown: '状态待确认' };
const activeStatuses = new Set(['queued', 'submitting', 'running']);
let jobsSignature = '';
let noticeTimer;
const generateFeedback = createButtonFeedback($('generate'), createIcon);
const cancelPendingFeedback = createButtonFeedback($('cancel-pending'), createIcon);
const promptFeedback = createButtonFeedback($('generate-prompts'), createIcon);
const configFeedback = createButtonFeedback($('reload-rule-configs'), createIcon);
let composeBusy = false;
let composeDirty = false;
let ruleConfigsLoaded = false;
let workflowInputOptions = {};
let settingsInitialized = false;
let settingsDirty = false;
let historyLoaded = false;
let historyLoading = false;
let workflowLoadRevision = 0;
const expandedJobs = new Set();
const jobPager = createJobPager({ request: page => api(`/api/jobs?page=${page}`), changed: renderJobPage, active: () => state.view === 'jobs' });
let availabilityRevision = 0;
let availabilitySignature = '';
let hasSavedApiKey = false;
let roamSettingsLoaded = false, roamSettingsLoading = false;
let roamSettings = { prefetch_count: 0, max_history_images: 0, backend_id: '', preset_id: '', liked_tags_only: false, prompt_mode: 'random', playback_interval_seconds: 5 };
let roamError = '';
let roamAnchorRetried = false;
let roamPageActive = true, roamVersion = 0;
let roamSettingsSaving = false, roamSwitch = null;
const roamPlayback = createRoamPlayback({
  advance: current => moveImage('newer', current),
  changed: detail => document.dispatchEvent(new CustomEvent('pictide:roam-playback-state', { detail })),
  cancelWait: () => { nextImageWait.cancel(); renderArtifacts(); },
});
function syncRoamPlayback(artifact = null) {
  const image = $('main-image');
  roamPlayback.update({ imageId: artifact?.id || null,
    ready: !!artifact && state.currentImage === artifact.id && image.complete && image.naturalWidth > 0 && $('image-error').hidden,
    active: state.view === 'feed' && roamPageActive && !document.hidden,
    busy: !!nextImageWait.current || roamWindowLoading || !!roamSwitch || state.feedbackPending,
    // A paused generator must not disable playback of already saved pictures.
    blocked: !!roamSwitch || !$('image-error').hidden,
  });
}
function publishPlaybackInterval(settings) {
  document.dispatchEvent(new CustomEvent('pictide:roam-playback-interval', { detail: settings.playback_interval_seconds ?? 5 }));
  document.dispatchEvent(new CustomEvent('pictide:roam-options-settings', { detail: settings }));
}
const immersive = createImmersiveViewer({
  card: $('image-card'), toolbar: document.querySelector('.image-toolbar'),
  entry: $('roam-immersive'), focusReturn: $('roam-options'),
  eligible: () => state.view === 'feed' && !$('image-card').hidden && !!state.currentImage,
  changed: () => document.dispatchEvent(new Event('pictide:roam-options-close')),
});
const refillRoam = createRefillCoordinator({
  active: () => galleryCursors.ready && roamPageActive && roamSettingsLoaded && !roamSwitch && !roamBlocked && (roamSettings.prefetch_count > 0 || !!nextImageWait.current) && state.view === 'feed' && !document.hidden,
  version: () => `${roamVersion}:${nextImageWait.current?.token || 0}`,
  anchor: () => state.activeId || null,
  request: anchor_id => api('/api/roam/ensure', { method: 'POST', body: JSON.stringify({ anchor_id, demand: !!nextImageWait.current }) }),
  result: result => {
    roamAnchorRetried = false;
    if (Number.isInteger(result.prefetch_count)) roamSettings.prefetch_count = result.prefetch_count;
    if (result.job && !state.jobs.some(job => job.id === result.job.id)) { state.jobs.unshift(result.job); renderJobs(); }
    if (result.paused) {
      roamBlocked = true; roamPlayback.pause(); nextImageWait.cancel(); renderArtifacts();
      if (result.error !== roamError) { roamError = result.error; showNotice(`预取已暂停：${result.error || '请检查任务状态'}。可在漫游设置中保存后重试。`, true); }
    } else {
      if (likedTagsWait(result, !!nextImageWait.current)) {
        roamBlocked = false; nextImageWait.cancel(); roamPlayback.pause(); renderArtifacts();
        showNotice('喜欢图片中暂无可用标签，请先喜欢图片或将偏好范围设为全部');
        return;
      }
      clearRoamError();
      if (nextImageWait.current && result.ready > 0) refresh(true);
    }
  },
  error: error => {
    if (error.status === 404 && !roamAnchorRetried) { roamAnchorRetried = true; refresh(true); return; }
    roamBlocked = !isTemporaryRefillError(error); nextImageWait.cancel(); renderArtifacts();
    if (error.message !== roamError) { roamError = error.message; showNotice(`预取未完成：${error.message}${roamBlocked ? '' : '。后续页面事件会自动重试。'}`, true); }
  },
});

function clearRoamError() {
  if (/^(?:预取(?:已暂停|未完成)：|喜欢图片中暂无可用标签)/.test($('notice').textContent)) $('notice').hidden = true;
  roamError = '';
  roamBlocked = false;
}

function showBackendAvailability(available, pending = false) {
  const element = $('backend-status');
  element.textContent = pending ? '检查中' : available ? '可用' : state.backends.length ? '不可用' : '未配置';
  element.dataset.tooltip = pending ? '正在检查后端连接' : available ? '至少一个后端已通过连接检查' : state.backends.length ? '后端未通过连接检查，可在设置中测试连接' : '在设置中添加生图后端';
  element.classList.toggle('connected', available);
}
async function checkBackendAvailability() {
  const signature = JSON.stringify(state.backends);
  if (signature === availabilitySignature) return;
  availabilitySignature = signature;
  const revision = ++availabilityRevision;
  if (!state.backends.length) { showBackendAvailability(false); return; }
  showBackendAvailability(false, true);
  let available = false;
  await Promise.allSettled(state.backends.map(async backend => {
    const result = await api(`/api/backends/${encodeURIComponent(backend.id)}/check`, { method: 'POST', body: JSON.stringify(backend) });
    if (result.ok && revision === availabilityRevision) { available = true; showBackendAvailability(true); }
  }));
  if (revision === availabilityRevision) showBackendAvailability(available);
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  let data;
  try { data = await response.json(); } catch { throw new Error(`服务返回了无法解析的响应（HTTP ${response.status}）`); }
  if (!response.ok) { const error = new Error(typeof data.error === 'string' ? data.error : data.error?.message || data.detail || `请求失败（HTTP ${response.status}）`); error.status = response.status; throw error; }
  return data;
}
function showNotice(message, error = false) {
  if (state.view === 'generate') {
    $('notice').hidden = true;
    if (error) { state.generatedError = message; renderGeneratedResults(); }
    return;
  }
  if (error) immersive.leave(); // Keep actionable errors visible outside native fullscreen.
  clearTimeout(noticeTimer); $('notice').textContent = message; $('notice').classList.toggle('error', error); $('notice').hidden = false;
  if (!error) noticeTimer = setTimeout(() => { $('notice').hidden = true; }, 5000);
}
function settingsNotice(message, error = false) { $('settings-result').textContent = message; $('settings-result').classList.toggle('error', error); $('settings-result').hidden = false; }
function historyNotice(message, error = false) { $('history-result').textContent = message; $('history-result').classList.toggle('error', error); $('history-result').hidden = !message; }
function describeAction(element, label) { element.setAttribute('aria-label', label); element.dataset.tooltip = label; }
function inlineStatus(id, message, visible = true) { const element = $(id); element.textContent = message; element.hidden = !visible; }
function option(value, label) { const item = document.createElement('option'); item.value = value; item.textContent = label; return item; }
function dateLabel(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
function seedLabel(item) { return item.seed_applied === false ? '使用工作流种子设置' : `seed ${item.seed ?? '—'}`; }
function artifactsForView() { return state.view === 'liked' ? state.likedArtifacts : state.artifacts; }
function pageView() { return ['liked', 'generate'].includes(state.view) ? state.view : 'feed'; }
function applyPage(view, result, append = false) {
  return applyArtifactPage(state, view, result, typeof append === 'object' ? append : { append });
}
const viewTitles = { feed: '漫游', generate: '生成', liked: '喜欢', jobs: '任务', prompts: '提示词', settings: '设置' };
function setView(route, updateUrl = true) {
  const [requested, section] = String(route || 'feed').split('/');
  const view = Object.hasOwn(viewTitles, requested) ? requested : 'feed';
  if (state.feedbackPending) { showNotice('正在保存评价，请稍候。'); return; }
  if (view !== state.view) { if (view !== 'feed') roamPlayback.pause(); immersive.leave(); viewRevision++; nextImageWait.cancel(); roamWindowLoading = false; }
  state.view = view;
  if (view === 'generate') { clearTimeout(noticeTimer); $('notice').hidden = true; }
  document.dispatchEvent(new Event('pictide:close-image-info'));
  if (view === 'settings' && ['general', 'backend', 'roam', 'history', 'data'].includes(section)) state.settingsSection = section;
  const editor = view === 'prompts';
  document.querySelectorAll('[data-view]').forEach((button) => {
    const selected = button.dataset.view === view;
    button.classList.toggle('active', selected);
    if (selected) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('view-title').textContent = viewTitles[view];
  $('roam-loading').hidden = true;
  $('feed-main').hidden = editor;
  $('prompts-view').hidden = !editor;
  $('compose').hidden = view !== 'generate';
  $('settings-view').hidden = view !== 'settings';
  $('app-workspace').classList.add('compose-hidden');
  $('app-workspace').classList.toggle('editor-active', editor);
  $('app-workspace').classList.toggle('roam-active', view === 'feed');
  $('gallery-view').hidden = view !== 'feed';
  $('liked-view').hidden = view !== 'liked';
  $('liked-privacy-controls').hidden = view !== 'liked';
  $('roam-options-controls').hidden = view !== 'feed';
  if (view !== 'feed') document.dispatchEvent(new Event('pictide:roam-options-close'));
  $('jobs-view').hidden = view !== 'jobs';
  if (view === 'settings') setSettingsSection(state.settingsSection, false);
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#${view}${view === 'settings' ? `/${state.settingsSection}` : ''}`);
  // Keep controllers and their inputs mounted: navigation never discards drafts.
  if (!editor) { renderArtifacts(); renderJobs(); if (galleryCursors.ready) refresh(true); }
  refillRoam();
}
function setSettingsSection(section, updateUrl = true) {
  if (!['general', 'backend', 'roam', 'history', 'data'].includes(section)) section = 'general';
  state.settingsSection = section;
  document.querySelectorAll('[data-settings-section]').forEach((button) => {
    const active = button.dataset.settingsSection === section;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  for (const name of ['general', 'backend', 'roam', 'history', 'data']) $(`settings-${name}`).hidden = name !== section;
  if (section === 'roam' && !roamSettingsLoading) { if (!roamSettingsLoaded) loadRoamSettings(); else loadRoamConfigs(); }
  if (section === 'history' && !historyLoaded && !historyLoading) loadHistorySettings();
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#settings/${section}`);
}
function renderBackends() {
  const selected = $('generate-backend').value;
  $('generate-backend').replaceChildren(...(state.backends.length ? state.backends.map((backend) => option(backend.id, backend.name)) : [option('', '请先配置生图后端')]));
  if (state.backends.some((backend) => backend.id === selected)) $('generate-backend').value = selected;
  $('generate').disabled = !state.backends.length;
  checkBackendAvailability();
  const edited = $('edit-backend').value;
  $('edit-backend').replaceChildren(...state.backends.map((backend) => option(backend.id, backend.name)), option('__new__', '＋ 添加后端'));
  if (state.backends.some((backend) => backend.id === edited)) $('edit-backend').value = edited;
  updateGenerationHints();
  renderRoamBackends();
}
function updateGenerationHints() {
  const backend = state.backends.find((item) => item.id === $('generate-backend').value);
  const noSeed = !!backend && !backend.bindings?.seed;
  $('seed').disabled = noSeed;
  describeAction($('seed-note'), noSeed ? '未绑定种子输入，将使用工作流自身的种子设置。' : '-1 为随机，每次使用的实际种子会保留。');
  $('negative-binding-note').hidden = !backend || !!backend.bindings?.negative;
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
  if (feedback) configFeedback.show('pending', '正在刷新…');
  try {
    const selected = $('rule-config').value;
    const listing = await api('/api/candidate/presets');
    const presets = listing.presets;
    $('rule-config').replaceChildren(...(presets.length ? presets.map(item => option(item.id, item.name)) : [option('', '请先新建生成预设')]));
    $('rule-config').value = presets.some(item => item.id === selected) ? selected : presets[0]?.id || '';
    inlineStatus('rule-config-note', '还没有生成预设，请在提示词页新建。', !presets.length);
    ruleConfigsLoaded = true; updateRuleControls();
    if (feedback) configFeedback.show('success', '已刷新');
  } catch (error) {
    inlineStatus('rule-config-note', `预设读取失败：${error.message}`, !feedback);
    if (feedback) configFeedback.show('error', '刷新失败', `刷新失败：${error.message}`);
  }
  finally { button.disabled = false; }
}

function ruleNumber(id, label, minimum, maximum) {
  const raw = $(id).value;
  const value = Number(raw);
  if (!raw.trim() || !Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error(`${label}须为 ${minimum}–${maximum} 之间的整数。`);
  return value;
}

function readRuleGeneration() {
  if (!$('rule-config').value) throw new Error('请先选择生成预设，或在提示词页新建预设。');
  const mode = $('rule-mode').value;
  const current = {
    mode, seed: mode === 'random_each_run' ? Number($('rule-seed').value) || 0 : ruleNumber('rule-seed', '提示词种子', 0, Number.MAX_SAFE_INTEGER),
    step: mode === 'sequence' ? ruleNumber('sequence-step', '帧序号', 0, 1000) : Number($('sequence-step').value) || 0,
    seedControl: $('rule-seed-control').value, stepControl: $('sequence-control').value,
  };
  const payload = { preset_id: $('rule-config').value, mode, seed: mode === 'random_each_run' ? 0 : current.seed, max_steps: ruleNumber('rule-max-steps', '搜索上限', 1, 1000000), sequence_step: mode === 'sequence' ? current.step : 0 };
  return { current, payload };
}

function presentRulePrompts(result, counters, current) {
  if (typeof result.positive !== 'string' || typeof result.negative !== 'string') throw new Error('候选服务没有返回完整的正负提示词。');
  $('positive').value = result.positive; $('negative').value = result.negative;
  $('rule-seed').value = String(counters.seed); $('sequence-step').value = String(counters.step);
  $('rule-report').hidden = false;
  const { positive, negative, ...report } = result;
  $('rule-report-content').textContent = JSON.stringify(report, null, 2);
  const usedSeed = current.mode === 'sequence' ? `序列种子 ${result.sequence?.seed ?? current.seed} · 帧 ${result.sequence?.step ?? current.step} · 本帧有效种子 ${result.seed}` : `本次提示词种子 ${result.seed}`;
  inlineStatus('rule-generation-note', usedSeed);
  $('rule-generation-note').dataset.tooltip = '计数已更新为下次值，当前提示词可直接编辑。';
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
function renderGalleryLoading() {
  syncRoamPlayback();
  $('roam-immersive').disabled = true;
  immersive.leave();
  $('empty-state').hidden = false; $('image-card').hidden = true;
  $('empty-title').hidden = true; $('empty-description').textContent = '正在读取图片…';
  $('empty-settings').hidden = true; $('empty-generate').hidden = true; $('load-more').hidden = true;
  $('roam-loading').hidden = state.view !== 'feed';
  $('roam-loading-label').textContent = '正在读取漫游图片';
}
function renderArtifacts() {
  renderGeneratedResults();
  renderLikedResults();
  if (state.view !== 'feed') return;
  if (!galleryCursors.ready) { renderGalleryLoading(); return; }
  const items = artifactsForView();
  const page = state.pages[pageView()];
  const selection = resolveGalleryCursor(items, state.activeId, page.loaded);
  if (selection.loading) { renderGalleryLoading(); return; }
  const roam = state.view === 'feed';
  const waiting = roam && (!!nextImageWait.current || roamWindowLoading || !!roamSwitch);
  $('load-more').hidden = roam || !page.hasMore;
  $('load-more').disabled = state.loadingMore || state.feedbackPending;
  $('load-more').textContent = state.loadingMore ? '加载中…' : '更早图片';
  $('load-more').dataset.tooltip = `已加载 ${items.length} / ${page.total} 张图片`;
  if (selection.id !== state.activeId) state.activeId = selection.id;
  const index = Math.max(0, items.findIndex((item) => item.id === state.activeId));
  const artifact = items[index];
  $('empty-state').hidden = !!artifact; $('image-card').hidden = !artifact;
  $('empty-title').hidden = false;
  $('empty-description').textContent = state.view === 'liked' ? '喜欢的图片会保存在这里。' : waiting ? '正在准备漫游图片…' : state.backends.length ? '开始漫游，发现下一张图片。' : '连接 ComfyUI，开始生成。';
  $('empty-settings').hidden = state.view === 'liked' || state.backends.length > 0;
  $('empty-generate').hidden = !roam || !state.backends.length || waiting;
  $('empty-generate').textContent = '开始漫游';
  $('empty-settings').textContent = '配置后端';
  $('roam-loading').hidden = !waiting;
  $('roam-loading-label').textContent = artifact ? '正在加载下一张漫游图片' : '正在生成漫游图片';
  $('image-card').setAttribute('aria-busy', String(waiting));
  $('roam-immersive').disabled = !roam || !artifact;
  if (!artifact) { syncRoamPlayback(); immersive.leave(); state.currentImage = null; document.dispatchEvent(new CustomEvent('pictide:image-info', { detail: null })); return; }
  document.dispatchEvent(new CustomEvent('pictide:image-info', { detail: { id: artifact.id, seed: artifact.seed_applied === false ? '使用工作流种子设置' : String(artifact.seed ?? '—'), positive: artifact.positive || '', negative: artifact.negative || '' } }));
  if (state.currentImage !== artifact.id) {
    state.currentImage = artifact.id; $('image-error').hidden = true;
    const imageUrl = `/api/artifacts/${encodeURIComponent(artifact.id)}/image`;
    $('main-image').src = imageUrl;
    $('image-date').textContent = dateLabel(artifact.created_at);
  }
  $('image-index').textContent = `${index + 1} / ${page.total || items.length}`;
  $('like').setAttribute('aria-pressed', String(artifact.feedback === 1));
  describeAction($('like'), artifact.feedback === 1 ? '已喜欢，点击撤回' : '喜欢 · ↑');
  $('dislike').setAttribute('aria-pressed', String(artifact.feedback === -1));
  describeAction($('dislike'), artifact.feedback === -1 ? '已不喜欢，点击撤回' : '不喜欢 · ↓');
  $('like').disabled = state.feedbackPending; $('dislike').disabled = state.feedbackPending;
  $('previous').disabled = (index >= items.length - 1 && !page.hasMore) || state.feedbackPending || roamWindowLoading || !!roamSwitch;
  $('next').disabled = (!roam && index <= 0) || state.feedbackPending || waiting;
  syncRoamPlayback(artifact);
}
function advanceWaitingImage() {
  const next = nextImageWait.consume(state.artifacts, galleryCursors.get('feed'), state.view === 'feed' && roamPageActive && !document.hidden);
  if (next) selectImage(next);
}
function requestNextRoamImage() {
  if (!galleryCursors.ready || roamSwitch || nextImageWait.current || state.view !== 'feed') return;
  if (!state.backends.length) { roamPlayback.pause(); showNotice('请先在设置中配置生图后端。', true); return; }
  clearRoamError();
  nextImageWait.begin(state.activeId); renderArtifacts(); refillRoam();
}
async function moveImage(direction, automatic = null) {
  if (state.feedbackPending || !galleryCursors.ready || roamWindowLoading || roamSwitch) return;
  if (automatic && !automatic()) return;
  if (!automatic && state.view === 'feed') roamPlayback.restart();
  if (!state.pages[pageView()].loaded) { refresh(true); return; }
  if (state.view === 'feed' && direction === 'older') nextImageWait.cancel();
  else if (state.view === 'feed' && nextImageWait.current) return;
  const items = artifactsForView(); const index = items.findIndex((item) => item.id === state.activeId);
  const destination = destinationIndex(index, items.length, direction);
  if (destination === null && state.view === 'feed') {
    const page = state.pages.feed;
    const action = roamBoundaryAction(direction, page);
    if (action === 'load') {
      const anchor = state.activeId, revision = viewRevision;
      roamWindowLoading = true; renderArtifacts();
      try {
        const result = await api(roamArtifactPath(anchor));
        if (state.view !== 'feed' || state.activeId !== anchor || revision !== viewRevision || (automatic && !automatic())) return;
        const applied = applyPage('feed', result, { replace: true });
        if (!applied.accepted) { refresh(true); return; }
        if (result.anchor_id !== undefined && !state.artifacts.some(item => item.id === anchor)) { state.activeId = result.anchor_id; renderArtifacts(); return; }
        const next = destinationIndex(state.artifacts.findIndex(item => item.id === anchor), state.artifacts.length, direction);
        if (next !== null) state.activeId = state.artifacts[next].id;
        else if (direction === 'newer') requestNextRoamImage();
      } catch (error) { if (automatic && !isTemporaryRefillError(error)) roamPlayback.pause(); showNotice(`图片加载失败：${error.message}`, true); }
      finally { if (revision === viewRevision) roamWindowLoading = false; renderArtifacts(); refillRoam(); }
    } else if (action === 'generate') requestNextRoamImage();
    else renderArtifacts();
    return;
  }
  if (destination === null) { showNotice(items.length ? direction === 'newer' ? '已经是最新的一张。' : state.pages[pageView()].hasMore ? '已到已加载图片的末尾，请点击加载更早图片。' : '已经是最早的一张。' : '还没有可以浏览的图片。'); return; }
  state.activeId = items[destination].id; renderArtifacts(); refillRoam();
}
async function feedback(value, toggle = true) {
  if (state.feedbackPending) return;
  const artifact = artifactsForView().find((item) => item.id === state.activeId); if (!artifact) { showNotice('还没有可以评价的图片。'); return; }
  const nextValue = feedbackValue(artifact.feedback, value, toggle);
  if (nextValue === artifact.feedback) return;
  const artifactRevision = state.artifactRevision;
  state.feedbackPending = true;
  renderArtifacts();
  try {
    if (state.view === 'liked' && nextValue === null && !await confirmAction('确定取消喜欢这张图片？取消后将从喜欢页面移除，并受自动清理规则影响。')) return;
    const result = await api(`/api/artifacts/${encodeURIComponent(artifact.id)}/feedback`, { method: 'PUT', body: JSON.stringify({ value: nextValue }) }); state.feedbackRevision++; observeArtifactRevision(state, result.revision ?? result.artifact_revision); if (artifactRevision === state.artifactRevision) { const delta = Number(result.artifact.feedback === 1) - Number(artifact.feedback === 1); state.pages.liked.total += delta; replaceArtifact(result.artifact); } renderArtifacts();
  }
  catch (error) { showNotice(error.status === 404 || error.status === 410 ? '图片已清理或不可用，正在刷新列表。' : error.message, true); }
  finally { state.feedbackPending = false; renderArtifacts(); await refresh(true); }
}
function replaceArtifact(artifact) {
  state.artifacts = state.artifacts.map((item) => item.id === artifact.id ? artifact : item);
  state.generatedArtifacts = state.generatedArtifacts.map((item) => item.id === artifact.id ? artifact : item);
  if (artifact.feedback === 1) {
    const index = state.likedArtifacts.findIndex((item) => item.id === artifact.id);
    if (index >= 0) state.likedArtifacts[index] = artifact;
    else state.likedArtifacts = [artifact, ...state.likedArtifacts].sort((a,b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id.localeCompare(a.id));
  } else state.likedArtifacts = state.likedArtifacts.filter((item) => item.id !== artifact.id);
}
function createJobCard(job) {
  const card = document.createElement('details'); card.className = 'job'; card.dataset.jobId = job.id;
  card.open = expandedJobs.has(job.id);
  card.addEventListener('toggle', () => { if (card.open) expandedJobs.add(job.id); else expandedJobs.delete(job.id); });
  const summary = document.createElement('summary');
  const label = statusNames[job.status] || job.status;
  summary.setAttribute('aria-label', `${label} · ${job.id} · ${dateLabel(job.created_at)} · 任务详情`);
  summary.dataset.tooltip = `${label} · ${job.id} · ${dateLabel(job.created_at)}`;
  const iconName = { queued: 'Clock', submitting: 'LoaderCircle', running: 'LoaderCircle', completed: 'CircleCheck', failed: 'CircleX', cancelled: 'CircleSlash' }[job.status] || 'CircleHelp';
  const status = document.createElement('span'); status.className = `job-status job-status-${job.status}`; status.dataset.tooltip = label;
  status.setAttribute('role', 'img'); status.setAttribute('aria-label', label); status.append(createIcon(iconName));
  const clock = document.createElement('span'); clock.className = 'job-time'; clock.dataset.tooltip = new Date(job.created_at).toLocaleString('zh-CN');
  clock.setAttribute('role', 'img'); clock.setAttribute('aria-label', clock.dataset.tooltip); clock.append(createIcon('Clock'));
  const identifier = document.createElement('span'); identifier.className = 'job-identifier'; identifier.textContent = job.id;
  identifier.dataset.tooltip = `任务 ID：${job.id}`;
  summary.append(status, identifier, clock);
  const body = document.createElement('div'); body.className = 'job-body';
  const meta = document.createElement('dl'); meta.className = 'job-meta';
  for (const [name, value] of [['状态', label], ['时间', new Date(job.created_at).toLocaleString('zh-CN')], ['后端', job.backend_name || job.backend_id], ['种子', seedLabel(job)], ['任务 ID', job.id]]) {
    const term = document.createElement('dt'), detail = document.createElement('dd'); term.textContent = name; detail.textContent = value; meta.append(term, detail);
  }
  body.append(meta);
  for (const [name, value] of [['正向提示词', job.positive], ['负向提示词', job.negative]]) {
    if (!value) continue;
    const heading = document.createElement('h3'); heading.textContent = name;
    const prompt = document.createElement('p'); prompt.className = 'job-prompt'; prompt.textContent = value; body.append(heading, prompt);
  }
  if (job.error) { const error = document.createElement('p'); error.className = 'job-error'; error.textContent = job.error; body.append(error); }
  if (activeStatuses.has(job.status)) { const actions = document.createElement('div'); actions.className = 'job-actions'; const cancel = document.createElement('button'); cancel.textContent = '取消任务'; decorateElement(cancel, 'button', {}); cancel.addEventListener('click', () => cancelJob(job.id, cancel)); actions.append(cancel); body.append(actions); }
  card.append(summary, body);
  return card;
}
function renderJobs() {
  renderGeneratedResults();
}
function renderJobPage(page) {
  const signature = JSON.stringify([page.page, page.items]);
  if (signature !== jobsSignature) { jobsSignature = signature; $('job-list').replaceChildren(...page.items.map(createJobCard)); }
  $('job-list').inert = page.loading;
  $('job-list').setAttribute('aria-busy', String(page.loading));
  $('jobs-empty').hidden = !page.loaded || page.total > 0 || page.loading || !!page.error;
  document.dispatchEvent(new CustomEvent('pictide:jobs-pagination', { detail: {
    page: page.page, totalPages: page.totalPages, loading: page.loading,
    visible: page.loading || !!page.error || page.total > 0,
  } }));
  inlineStatus('jobs-page-message', page.error || (page.loading ? '正在读取任务…' : ''), !!page.error || page.loading);
  $('jobs-page-message').classList.toggle('error', !!page.error);
}
document.addEventListener('pictide:jobs-page', event => {
  if (!jobPager.state.loading) jobPager.load(event.detail.page);
});
function renderGeneratedResults() {
  const manual = state.jobs.filter(job => job.source !== 'roam');
  const pending = manual.filter(job => activeStatuses.has(job.status));
  const latest = manual[0];
  const status = pending.length ? `${pending.length} 个任务生成中` : latest && ['failed', 'unknown', 'cancelled'].includes(latest.status) ? `${statusNames[latest.status]}${latest.error ? `：${latest.error}` : ''}` : '';
  document.dispatchEvent(new CustomEvent('pictide:generated-results', { detail: {
    artifacts: state.generatedArtifacts, total: state.pages.generate.total,
    hasMore: state.pages.generate.hasMore, loading: (!state.generatedLoaded || !state.pages.generate.loaded) && !state.generatedError && !state.generatedMutationError || state.loadingMore,
    error: state.generatedMutationError || state.generatedError, pending: pending.length > 0, status,
    feedbackPending: state.feedbackPending, mutationPending: state.generatedMutationPending, visible: state.view === 'generate', configured: state.backends.length > 0,
  } }));
}
function renderLikedResults() {
  document.dispatchEvent(new CustomEvent('pictide:liked-results', { detail: {
    artifacts: state.likedArtifacts, total: state.pages.liked.total,
    hasMore: state.pages.liked.hasMore, loading: !state.pages.liked.loaded && !state.likedError || state.loadingMore,
    error: state.likedError, feedbackPending: state.feedbackPending,
    mutationPending: state.generatedMutationPending, visible: state.view === 'liked', configured: state.backends.length > 0,
  } }));
}
async function feedbackGenerated(id, toggle = true, view = 'generate') {
  if (state.feedbackPending || state.generatedMutationPending) return;
  const artifact = (view === 'liked' ? state.likedArtifacts : state.generatedArtifacts).find(item => item.id === id);
  if (!artifact) return;
  const value = feedbackValue(artifact.feedback, 1, toggle);
  if (value === artifact.feedback) return;
  const revision = state.artifactRevision;
  if (view === 'liked') state.likedError = ''; else state.generatedMutationError = '';
  state.feedbackPending = true; renderArtifacts();
  try {
    if (view === 'liked' && value === null && !await confirmAction('确定取消喜欢这张图片？取消后将从喜欢页面移除，并受自动清理规则影响。')) return;
    const result = await api(`/api/artifacts/${encodeURIComponent(id)}/feedback`, { method: 'PUT', body: JSON.stringify({ value }) });
    state.feedbackRevision++;
    observeArtifactRevision(state, result.revision ?? result.artifact_revision);
    if (revision === state.artifactRevision) { state.pages.liked.total += Number(result.artifact.feedback === 1) - Number(artifact.feedback === 1); replaceArtifact(result.artifact); }
  } catch (error) { const message = error.status === 404 || error.status === 410 ? '图片已清理或不可用，正在刷新列表。' : error.message; if (view === 'liked') state.likedError = message; else state.generatedMutationError = message; }
  finally { state.feedbackPending = false; renderArtifacts(); await refresh(true); }
}
async function clearGenerated() {
  if (state.feedbackPending || state.generatedMutationPending) return;
  const previousTotal = state.pages.generate.total;
  let committed = false;
  state.generatedMutationPending = true; state.generatedMutationError = ''; renderGeneratedResults();
  try {
    const result = await api('/api/generated', { method: 'DELETE', body: '{}' });
    committed = true;
    state.feedbackRevision++;
    observeArtifactRevision(state, result.revision);
    state.generatedArtifacts = [];
    state.pages.generate.total = Math.max(0, previousTotal - result.removed - result.hidden);
    const page = await api(artifactPath('generate'));
    const applied = applyPage('generate', page, { replace: true });
    state.generatedLoaded = applied.accepted;
    if (!applied.accepted) state.refreshQueued = true;
    state.generatedError = '';
  } catch (error) {
    if (committed) { state.generatedArtifacts = []; state.pages.generate.loaded = false; state.generatedLoaded = false; }
    state.generatedMutationError = `${committed ? '图片已处理，列表刷新失败' : '清理失败'}：${error.message}`;
  } finally {
    state.generatedMutationPending = false; renderGeneratedResults(); await refresh(true);
  }
}
async function cancelJob(id, button) {
  button.disabled = true;
  try { const result = await api(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }); state.jobs = state.jobs.map((job) => job.id === id ? result.job : job); renderJobs(); if (state.view === 'jobs') await jobPager.load(); }
  catch (error) { showNotice(error.message, true); button.disabled = false; }
}
async function refresh(force = false) {
  if (!galleryCursors.ready) return;
  if (document.hidden && !force || state.polling) { if (force) state.refreshQueued = true; return; }
  state.polling = true;
  const feedbackRevision = state.feedbackRevision;
  const windowVersion = roamVersion;
  const view = pageView();
  const anchor = galleryCursors.get('feed');
  try {
    const [jobs, artifacts] = await Promise.all([api('/api/jobs'), api(view === 'feed' ? roamArtifactPath(anchor) : artifactPath(view)), state.view === 'jobs' ? jobPager.load() : Promise.resolve()]);
    state.jobs = jobs.jobs;
    // Multi-round counters must come from the idempotent response, even if jobs
    // already appear in events. Retain the original request for a safe retry.
    for (const [key, request] of uncertainRequests) if (request.payload.repetitions === undefined && state.jobs.some((job) => job.request_id === request.payload.request_id)) uncertainRequests.delete(key);
    if (!state.feedbackPending && !state.generatedMutationPending && feedbackRevision === state.feedbackRevision) {
      if (view !== 'feed') applyPage(view, artifacts, { replace: !state.pages[view].loaded });
      else if (!roamSwitch && windowVersion === roamVersion && anchor === galleryCursors.get('feed')) {
        const applied = applyPage(view, artifacts, { replace: true });
        if (applied.accepted) {
          if (anchor && !state.artifacts.some(item => item.id === anchor) && artifacts.anchor_id !== undefined) {
            nextImageWait.cancel();
            selectImage(artifacts.anchor_id, 'feed');
          }
          advanceWaitingImage();
        } else {
          state.refreshQueued = true;
        }
      } else if (!roamSwitch) state.refreshQueued = true;
    }
    if (view === 'generate' && !state.generatedMutationPending) { state.generatedLoaded = true; state.generatedError = ''; }
    if (view === 'liked') state.likedError = '';
    renderJobs(); renderArtifacts();
    if (state.view === 'feed') roamPlayback.retry();
  }
  catch (error) {
    if (view === 'generate') { state.generatedError = `同步失败：${error.message}`; renderGeneratedResults(); }
    if (view === 'liked') { state.likedError = `同步失败：${error.message}`; renderLikedResults(); }
    if (nextImageWait.current) { nextImageWait.cancel(); roamBlocked = !isTemporaryRefillError(error); renderArtifacts(); }
    showNotice(`同步失败：${error.message}`, true);
  }
  finally { state.polling = false; if (state.refreshQueued) { state.refreshQueued = false; await refresh(true); } else refillRoam(); }
}
async function loadMore() {
  if (state.loadingMore || state.feedbackPending || state.generatedMutationPending) return;
  const view = pageView(); const page = state.pages[view]; if (!page.hasMore || !page.cursor) return;
  state.loadingMore = true; const revision = state.feedbackRevision; renderArtifacts();
  const artifactRevision = state.artifactRevision;
  try { const result = await api(artifactPath(view, page.cursor)); if (!state.feedbackPending && !state.generatedMutationPending && revision === state.feedbackRevision) { const applied = applyPage(view, result, { append: true, requestRevision: artifactRevision }); if (applied.refresh) await refresh(true); } }
  catch (error) { if (view === 'generate') state.generatedError = `加载失败：${error.message}`; if (view === 'liked') state.likedError = `加载失败：${error.message}`; showNotice(`加载失败：${error.message}`, true); }
  finally { state.loadingMore = false; renderArtifacts(); }
}
function loadBackend(id) {
  // Discard stale template responses when a different backend is selected.
  workflowLoadRevision++;
  $('workflow-mode').disabled = false;
  const backend = state.backends.find((item) => item.id === id);
  workflowInputOptions = {};
  $('backend-name').value = backend?.name || '本机 ComfyUI'; $('backend-kind').value = backend?.kind || 'comfyui';
  $('backend-url').value = backend?.base_url || 'http://127.0.0.1:8188';
  hasSavedApiKey = !!backend?.has_api_key;
  $('backend-key').value = hasSavedApiKey ? API_KEY_MASK : '';
  $('backend-key').setCustomValidity('');
  describeAction($('key-state'), hasSavedApiKey ? '已保存密钥。保留遮罩不修改，清空并保存可移除。' : '可选。本机 ComfyUI 通常无需密钥。');
  $('workflow-json').value = backend?.workflow ? JSON.stringify(backend.workflow, null, 2) : '';
  $('workflow-mode').value = backend?.workflow_id && state.workflows.some((item) => item.id === backend.workflow_id) ? `saved:${backend.workflow_id}` : configuredWorkflowMode(backend);
  state.workflowId = backend?.workflow_id || null;
  state.workflowRevision = backend?.workflow_revision || null;
  $('default-checkpoint').replaceChildren(option('', '自动选择第一个可用模型'));
  if (backend?.default_checkpoint) { $('default-checkpoint').append(option(backend.default_checkpoint, backend.default_checkpoint)); $('default-checkpoint').value = backend.default_checkpoint; }
  inlineStatus('model-note', '', false);
  $('settings-result').hidden = true;
  $('workflow-name').value = backend?.workflow_name || customWorkflowName(state.workflows.map(item => item.name));
  setWorkflowPanelMode('parameters', false);
  setNodeParametersExpanded(false);
  settingsDirty = false;
  settingsInitialized = true;
  $('delete-backend').disabled = !backend;
  updateBindings(backend?.bindings || {}, backend?.output_nodes || []);
  updateWorkflowControls();
}
function updateWorkflowControls() {
  const custom = $('workflow-mode').value !== 'default';
  $('custom-workflow').hidden = !custom; $('custom-workflow').disabled = !custom;
  $('default-workflow').hidden = custom;
  const needsBindings = effectiveWorkflowMode($('workflow-mode').value === 'default' ? 'default' : 'custom', $('workflow-json').value) === 'custom';
  $('binding-positive').required = needsBindings; $('binding-negative').required = needsBindings;
  $('workflow-name').required = custom;
  $('delete-workflow').disabled = !state.workflowId || !state.workflows.some(item => item.id === state.workflowId);
  if (custom && !needsBindings) { $('workflow-error').textContent = '请导入 API 工作流，或从默认文生图读取节点参数。'; $('workflow-error').classList.remove('valid'); }
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
      settingsNotice('请先修正节点参数中的无效输入，再切换 JSON。', true);
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
  describeAction($('toggle-workflow-json'), json ? '返回节点参数' : '编辑 API 工作流 JSON');
}
function updateBindings(bindings = null, outputNodes = null) {
  const previous = bindings || { positive: parseBinding($('binding-positive').value), negative: parseBinding($('binding-negative').value), seed: parseBinding($('binding-seed').value) };
  const previousOutputs = outputNodes || [...$('output-nodes').selectedOptions].map((item) => item.value);
  const positive = $('binding-positive'), negative = $('binding-negative'), seed = $('binding-seed'), outputs = $('output-nodes');
  try {
    const workflow = readWorkflow(); let textCount = 0;
    const retained = retainedWorkflowBindings(workflow, previous, previousOutputs);
    positive.replaceChildren(option('', '选择正向 text 输入')); negative.replaceChildren(option('', '选择负向 text 输入')); seed.replaceChildren(option('', '不绑定')); outputs.replaceChildren();
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
    $('workflow-error').textContent = `${Object.keys(workflow).length} 个节点 · ${textCount} 个文本输入`;
    $('workflow-error').classList.add('valid');
    $('workflow-json').setAttribute('aria-invalid', 'false');
  } catch (error) {
    $('workflow-error').textContent = $('workflow-json').value.trim() ? error.message : '支持从 ComfyUI 导出的 API 工作流。';
    $('workflow-error').classList.remove('valid');
    $('workflow-json').setAttribute('aria-invalid', 'true');
    if (bindings !== null) {
      positive.replaceChildren(option('', '选择正向 text 输入')); negative.replaceChildren(option('', '选择负向 text 输入')); seed.replaceChildren(option('', '不绑定')); outputs.replaceChildren();
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
          $('workflow-error').textContent = '草稿已更新，保存后生效。'; $('workflow-error').classList.add('valid');
        } catch (error) { control.setCustomValidity(error.message); }
      });
      decorateElement(control, control.tagName.toLowerCase(), { type: control.type }); label.append(control); grid.append(label);
    }
    target.append(panel);
  }
}

function applyWorkflowDraft(draft, inputOptions = {}) {
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
  if (workflowLoadRevision !== version || $('edit-backend').value !== editedId || $('backend-url').value !== url || $('default-checkpoint').value !== checkpoint) throw new Error('后端、工作流或模型选择已变化，请重新读取默认节点参数。');
  return result;
}

function renderWorkflowLibrary(selected = $('workflow-mode').value) {
  $('workflow-mode').replaceChildren(option('default', '默认文生图'), ...state.workflows.map((record) => option(`saved:${record.id}`, record.name)), option('custom', '自定义 API 工作流'));
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
  settingsNotice('正在读取工作流…');
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
    $('settings-result').hidden = true;
  } catch (error) { settingsNotice(error.message, true); }
  finally { if (workflowLoadRevision === revision) select.disabled = false; }
}
function connectionDraft() {
  const draft = { name: $('backend-name').value.trim(), kind: $('backend-kind').value, base_url: $('backend-url').value.trim() };
  if (!draft.name || !draft.base_url) throw new Error('请填写后端名称和 API 地址。');
  Object.assign(draft, apiKeyFields($('backend-key').value, hasSavedApiKey));
  return draft;
}
function draftBackend({ saveWorkflow = false } = {}) {
  const draft = connectionDraft();
  draft.workflow_mode = $('workflow-mode').value === 'default' ? 'default' : 'custom';
  if (draft.workflow_mode === 'default') { draft.default_checkpoint = $('default-checkpoint').value; return draft; }
  const invalidParameter = $('node-parameters').querySelector(':invalid');
  if (invalidParameter) { setNodeParametersExpanded(true); setWorkflowPanelMode('parameters', false); invalidParameter.reportValidity(); invalidParameter.focus(); throw new Error('请先修正节点参数中的无效输入。'); }
  const workflow = readWorkflow();
  const positive = parseBinding($('binding-positive').value), negative = parseBinding($('binding-negative').value), seed = parseBinding($('binding-seed').value);
  if (!positive) throw new Error('请选择正向提示词输入。');
  if (!negative) throw new Error('请选择负向提示词输入，以便准确记录本次实际使用的提示词。');
  if (bindingValue(positive) === bindingValue(negative)) throw new Error('正向和负向提示词不能绑定同一个输入。');
  const custom = { ...draft, workflow, bindings: { positive, negative, seed }, output_nodes: [...$('output-nodes').selectedOptions].map((item) => item.value) };
  return saveWorkflow ? { ...custom, ...workflowSaveFields(custom, $('workflow-name').value, state.workflowId ? { id: state.workflowId, revision: state.workflowRevision } : null) } : custom;
}
function openSettings() {
  if (!settingsInitialized) loadBackend($('edit-backend').value);
  setView('settings/backend');
}
function renderRoamBackends() {
  const selected = $('roam-backend').value;
  $('roam-backend').replaceChildren(option('', '自动选择后端'), ...state.backends.map(item => option(item.id, item.name)));
  if (selected && !state.backends.some(item => item.id === selected)) $('roam-backend').append(option(selected, '已移除的后端，请重新选择'));
  $('roam-backend').value = selected;
}
async function loadRoamConfigs() {
  try {
    const selected = $('roam-config').value;
    const listing = await api('/api/candidate/presets');
    const presets = listing.presets;
    $('roam-config').replaceChildren(option('', '自动选择预设'), ...presets.map(item => option(item.id, item.name)));
    if (selected && !presets.some(item => item.id === selected)) $('roam-config').append(option(selected, '已移除的预设，请重新选择'));
    $('roam-config').value = selected;
  } catch (error) { inlineStatus('roam-result', `预设读取失败：${error.message}`); }
}
const roamFields = {
  prefetch_count: 'roam-prefetch-count', max_history_images: 'roam-max-history-images',
  backend_id: 'roam-backend', preset_id: 'roam-config',
  playback_interval_seconds: 'roam-playback-interval', liked_tags_only: 'roam-liked-tags-only', prompt_mode: 'roam-prompt-mode',
};
function roamDraftDirty() {
  return Object.entries(roamFields).some(([key, id]) => String(key === 'liked_tags_only' ? $(id).checked : $(id).value) !== String(roamSettings[key]));
}
function beginRoamSwitch() {
  if (roamSwitch) return;
  roamSwitch = { resume: roamPlayback.playing, view: viewRevision };
  roamVersion++; viewRevision++;
  roamSwitch.view = viewRevision;
  roamPlayback.pause(); nextImageWait.cancel(); roamWindowLoading = false;
  renderArtifacts();
}
function finishRoamSwitch() {
  const transition = roamSwitch; roamSwitch = null;
  renderArtifacts();
  if (transition?.resume && transition.view === viewRevision && state.view === 'feed' && !document.hidden && !roamBlocked && !roamPlayback.playing) roamPlayback.toggle();
  refillRoam();
}
async function applyRoamSettings(settings, savedFields = []) {
  const next = { ...settings, prefetch_count: prefetchCount(settings.prefetch_count), max_history_images: maxHistoryImages(settings.max_history_images ?? 0), liked_tags_only: !!settings.liked_tags_only, prompt_mode: settings.prompt_mode ?? 'random', playback_interval_seconds: settings.playback_interval_seconds ?? 5 };
  const switched = roamSettingsLoaded && roamGenerationChanged(roamSettings, next);
  if (switched) beginRoamSwitch();
  const draft = Object.fromEntries(Object.entries(roamFields).map(([key, id]) => [key, key === 'liked_tags_only' ? $(id).checked : $(id).value]));
  const merged = mergeRoamDraft(roamSettings, next, draft, savedFields);
  for (const key of ['backend_id', 'preset_id']) {
    const control = $(roamFields[key]);
    if (merged[key] && ![...control.options].some(item => item.value === merged[key])) control.append(option(merged[key], merged[key]));
  }
  for (const [key, id] of Object.entries(roamFields)) {
    if (key === 'liked_tags_only') $(id).checked = merged[key];
    else $(id).value = String(merged[key] ?? '');
  }
  document.dispatchEvent(new CustomEvent('pictide:roam-settings-draft', { detail: merged }));
  roamSettings = next; roamSettingsLoaded = true; roamVersion++;
  publishPlaybackInterval(next);
  if (settings.paused) { roamBlocked = true; roamPlayback.pause(); } else clearRoamError();
  roamAnchorRetried = false;
  const current = state.artifacts.find(item => item.id === galleryCursors.get('feed'));
  const reset = observeArtifactRevision(state, settings.artifact_revision);
  if (roamSwitch) {
    // Keep the current picture visible while reading the new window. No old
    // request may merge its future images after this settings transition.
    if (reset) { state.artifacts = current ? [current] : []; state.pages.feed.loaded = true; state.currentImage = current?.id || null; }
    const version = roamVersion, anchor = galleryCursors.get('feed');
    try {
      const window = await api(roamArtifactPath(anchor));
      if (version === roamVersion) {
        const applied = applyPage('feed', window, { replace: true });
        if (applied.accepted && anchor && !state.artifacts.some(item => item.id === anchor) && window.anchor_id !== undefined) selectImage(window.anchor_id, 'feed');
      }
    } finally { finishRoamSwitch(); }
  } else {
    if (reset || state.view === 'feed') renderArtifacts();
    if (reset) await refresh(true);
    refillRoam();
  }
}
async function loadRoamSettings({ preserveDraft = false } = {}) {
  if (roamSettingsLoading || roamSettingsSaving) return;
  roamSettingsLoading = true;
  const version = roamVersion;
  try {
    const settings = await api('/api/settings/roam');
    if (roamSettingsSaving || version !== roamVersion) return;
    await applyRoamSettings(settings, preserveDraft ? [] : Object.keys(roamFields));
    renderRoamBackends(); await loadRoamConfigs();
  } catch (error) { inlineStatus('roam-result', `设置读取失败：${error.message}`); }
  finally { roamSettingsLoading = false; }
}
async function saveRoamSettings(patch) {
  if (roamSettingsSaving) throw new Error('正在保存漫游设置，请稍候。');
  roamSettingsSaving = true;
  const switched = roamGenerationChanged(roamSettings, { ...roamSettings, ...patch });
  if (switched) beginRoamSwitch();
  try {
    if (switched) await roamViewPending; // Store clears the window after the persisted current picture.
    const result = await api('/api/settings/roam', { method: 'PUT', body: JSON.stringify(patch) });
    await applyRoamSettings(result, Object.keys(patch));
    return result;
  } catch (error) { if (roamSwitch) finishRoamSwitch(); throw error; }
  finally { roamSettingsSaving = false; }
}
document.addEventListener('pictide:roam-settings-save', event => {
  const { patch, resolve, reject } = event.detail;
  saveRoamSettings(patch).then(resolve, reject);
});
$('roam-form').addEventListener('submit', async event => {
  event.preventDefault(); if ($('roam-save').disabled) return;
  $('roam-save').disabled = true; $('roam-fields').disabled = true;
  try {
    const payload = { prefetch_count: prefetchCount($('roam-prefetch-count').value), max_history_images: maxHistoryImages($('roam-max-history-images').value), backend_id: $('roam-backend').value, preset_id: $('roam-config').value, playback_interval_seconds: playbackInterval($('roam-playback-interval').value), liked_tags_only: $('roam-liked-tags-only').checked, prompt_mode: $('roam-prompt-mode').value };
    await saveRoamSettings(payload);
    inlineStatus('roam-result', '已保存漫游设置。');
    await refresh(true);
  } catch (error) { inlineStatus('roam-result', error.message); }
  finally { $('roam-save').disabled = false; $('roam-fields').disabled = false; }
});
async function bootstrap() {
  try {
    const data = await api('/api/bootstrap'); state.backends = data.backends || []; state.jobs = data.jobs || []; state.artifacts = data.artifacts || []; state.artifactRevision = data.artifact_revision ?? 0; state.databasePath = data.database_path || ''; state.dataDirectory = data.data_directory || '';
    galleryCursors.restore(data.roam_view || {});
    if (data.artifact_page?.anchor_id !== undefined && galleryCursors.get('feed') && !state.artifacts.some(item => item.id === galleryCursors.get('feed'))) selectImage(data.artifact_page.anchor_id, 'feed');
    state.pages.feed.loaded = true; state.pages.feed.total = data.counts?.roam ?? state.artifacts.length; state.pages.feed.hasMore = data.artifact_page?.has_more ?? state.pages.feed.total > state.artifacts.length; state.pages.feed.hasNewer = !!data.artifact_page?.has_newer; state.pages.feed.cursor = data.artifact_page?.next_cursor ?? state.artifacts.at(-1)?.id ?? null; state.pages.liked.total = data.counts?.liked ?? 0; state.pages.generate.total = data.counts?.generate ?? 0;
    if (data.backend_types?.length) $('backend-kind').replaceChildren(...data.backend_types.map((type) => option(type.kind, type.label)));
    renderBackends(); renderJobs(); renderArtifacts();
    if (data.roam_settings) await applyRoamSettings(data.roam_settings, Object.keys(roamFields));
    if (state.view === 'jobs') jobPager.load();
    $('data-directory').textContent = state.dataDirectory || '服务尚未返回数据目录';
    $('database-path').textContent = state.databasePath || '服务尚未返回数据库路径';
    await loadWorkflowLibrary();
    loadBackend($('edit-backend').value);
    if (!roamSettingsLoaded) await loadRoamSettings();
  } catch (error) { showNotice(`无法读取平台数据：${error.message}`, true); }
}

$('empty-settings').addEventListener('click', () => { if (state.view === 'feed' && state.backends.length) setView('settings/roam'); else openSettings(); });
$('empty-generate').addEventListener('click', requestNextRoamImage);
async function loadHistorySettings() {
  historyLoading = true;
  $('history-fields').disabled = true; $('history-save').disabled = true; $('history-save').textContent = '保存设置';
  historyNotice('正在读取清理设置…');
  try {
    const result = await api('/api/settings/history');
    $('history-retention-days').value = String(retentionDays(result.unliked_retention_days));
    if (observeArtifactRevision(state, result.artifact_revision)) { renderArtifacts(); await refresh(true); }
    historyLoaded = true; historyNotice('');
  } catch (error) {
    try { retentionDays($('history-retention-days').value); } catch { $('history-retention-days').value = '1'; }
    $('history-save').textContent = '重新保存';
    historyNotice(`读取失败：${error.message}。配置损坏时过期清理会暂停；可修改天数并重新保存以修复设置。`, true);
  } finally { historyLoading = false; $('history-fields').disabled = false; $('history-save').disabled = false; }
}
$('history-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if ($('history-save').disabled) return;
  try {
    const days = retentionDays($('history-retention-days').value);
    $('history-save').disabled = true; $('history-fields').disabled = true;
    const result = await api('/api/settings/history', { method: 'PUT', body: JSON.stringify({ unliked_retention_days: days }) });
    $('history-retention-days').value = String(retentionDays(result.unliked_retention_days));
    $('history-save').textContent = '保存设置'; historyLoaded = true;
    if (observeArtifactRevision(state, result.artifact_revision)) renderArtifacts();
    historyNotice(days ? `已保存：未标记喜欢的图片保留 ${days} 天。` : '已关闭自动清理。');
    await refresh(true);
  } catch (error) { historyNotice(error.message, true); }
  finally { $('history-save').disabled = false; $('history-fields').disabled = false; }
});
$('edit-backend').addEventListener('change', () => loadBackend($('edit-backend').value));
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
    $('workflow-error').textContent = 'JSON 草稿已更新，保存后生效。';
    $('workflow-error').classList.add('valid');
  } catch (error) {
    $('workflow-json').setAttribute('aria-invalid', 'true');
    $('workflow-error').textContent = error.message;
    $('workflow-error').classList.remove('valid');
  }
});
$('workflow-json').addEventListener('change', () => { updateBindings(); updateWorkflowControls(); });
$('edit-default-parameters').addEventListener('click', async () => {
  const button = $('edit-default-parameters'); button.disabled = true; settingsNotice('正在读取默认工作流参数…');
  try { const template = await currentDefaultTemplate(); applyWorkflowDraft(template, template.input_options || {}); setNodeParametersExpanded(true); settingsNotice('已展开节点参数，保存后生效。'); }
  catch (error) { settingsNotice(error.message, true); }
  finally { button.disabled = false; }
});
$('reload-workflows').addEventListener('click', async () => {
  const button = $('reload-workflows'); button.disabled = true;
  try { await loadWorkflowLibrary(); settingsNotice('工作流列表已刷新。'); }
  catch (error) { settingsNotice(error.message, true); }
  finally { button.disabled = false; }
});
$('delete-workflow').addEventListener('click', async () => {
  const id = state.workflowId, revision = state.workflowRevision;
  const workflow = state.workflows.find(item => item.id === id);
  if (state.saving || !workflow || !revision) return;
  if (!await confirmAction(`删除工作流「${workflow.name}」？已配置后端保留当前工作流参数，历史任务和图片保留。`)) return;
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
    settingsNotice('工作流已删除，当前参数保留为自定义草稿。');
  } catch (error) { settingsNotice(error.message, true); }
  finally { state.saving = false; $('settings-form').inert = false; }
});
$('delete-backend').addEventListener('click', async () => {
  const id = $('edit-backend').value, backend = state.backends.find(item => item.id === id);
  if (state.saving || !backend) return;
  if (!await confirmAction(`删除后端配置「${backend.name}」？${settingsDirty ? '当前未保存的后端修改将放弃。' : ''}历史任务和图片保留，已有任务继续使用提交时的配置。`)) return;
  state.saving = true; $('settings-form').inert = true;
  try {
    await api(`/api/backends/${encodeURIComponent(id)}`, { method: 'DELETE', body: '{}' });
    state.backends = state.backends.filter(item => item.id !== id);
    renderBackends(); loadBackend($('edit-backend').value); renderArtifacts();
    settingsNotice('后端配置已删除。');
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
  const button = $('load-models'); button.disabled = true; inlineStatus('model-note', '正在读取模型…');
  const editedId = $('edit-backend').value;
  const baseUrl = $('backend-url').value;
  try {
    const draft = connectionDraft(); const id = editedId === '__new__' ? 'new' : editedId;
    const result = await api(`/api/backends/${encodeURIComponent(id)}/models`, { method: 'POST', body: JSON.stringify(draft) });
    if ($('edit-backend').value !== editedId || $('backend-url').value !== baseUrl) return;
    const selected = $('default-checkpoint').value;
    const models = (result.models || []).filter((model) => typeof model === 'string');
    $('default-checkpoint').replaceChildren(option('', '自动选择第一个可用模型'), ...models.map((model) => option(model, model)));
    if (models.includes(selected)) $('default-checkpoint').value = selected;
    inlineStatus('model-note', '后端没有可用模型，请在 ComfyUI 中配置。', !models.length);
    button.dataset.tooltip = `刷新模型，当前 ${models.length} 个可用`;
  } catch (error) { inlineStatus('model-note', `读取失败：${error.message}`); }
  finally { button.disabled = false; }
});
$('test-backend').addEventListener('click', async () => {
  const button = $('test-backend'); button.disabled = true; settingsNotice('正在测试连接…');
  try { const draft = draftBackend(); const id = $('edit-backend').value === '__new__' ? 'new' : $('edit-backend').value; const result = await api(`/api/backends/${encodeURIComponent(id)}/check`, { method: 'POST', body: JSON.stringify(draft) }); settingsNotice(result.message || (result.ok ? '连接成功。' : '连接失败。'), !result.ok); if (id !== 'new' && result.ok) showBackendAvailability(true); }
  catch (error) { settingsNotice(error.message, true); }
  finally { button.disabled = false; }
});
$('settings-form').addEventListener('invalid', (event) => {
  if (event.target.closest('#node-parameters')) setNodeParametersExpanded(true);
}, true);
$('settings-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (state.saving) return;
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
    loadBackend(backend.id); renderArtifacts();
    settingsNotice(backend.workflow_name ? `后端与工作流「${backend.workflow_name}」已保存。` : '后端已保存。');
  } catch (error) { settingsNotice(error.message, true); }
  finally { state.saving = false; $('save-backend').disabled = false; $('settings-form').inert = false; }
});

$('generate-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (composeBusy) return; setComposeBusy(true);
  generateFeedback.show('pending', '正在提交…');
  let operation;
  try {
    const seed = Number($('seed').value); if (!$('seed').value.trim() || !Number.isSafeInteger(seed) || seed < -1) throw new Error('种子须为 -1 或非负安全整数。');
    const count = generationCount($('generation-count').value);
    const repetitions = generationRepetitions($('generation-repetitions').value);
    const automatic = $('prompt-source').value === 'rules' && $('auto-prompts').checked;
    const rule = automatic ? readRuleGeneration() : null;
    const payload = { backend_id: $('generate-backend').value, positive: $('positive').value, negative: $('negative').value, seed, count, repetitions,
      ...(rule ? { candidate: { ...rule.payload, seed_control: rule.current.seedControl, step_control: rule.current.stepControl } } : {}) };
    if (!payload.positive.trim() && !automatic) throw new Error('请输入正向提示词，或使用共现候选生成提示词。');
    const decision = submissionDecision(payload, uncertainRequests, automatic);
    const backend = state.backends.find((item) => item.id === $('generate-backend').value);
    if (!automatic && payload.negative.trim() && !backend?.bindings?.negative) throw new Error('当前后端未绑定负向输入。请清空负向提示词，或在后端设置中指定负向绑定。');
    operation = decision.retry || requestIdentity(payload, uncertainRequests, () => crypto.randomUUID());
    const hasOtherUncertain = uncertainRequests.size && !uncertainRequests.has(operation.key);
    uncertainRequests.set(operation.key, operation);
    const result = await api('/api/jobs', { method: 'POST', body: JSON.stringify(operation.payload) });
    uncertainRequests.delete(operation.key);
    if (result.candidate_result && result.next_candidate) {
      presentRulePrompts(result.candidate_result, { seed: result.next_candidate.seed, step: result.next_candidate.sequence_step },
        { mode: operation.payload.candidate.mode, seed: operation.payload.candidate.seed, step: operation.payload.candidate.sequence_step });
    }
    if (Number.isSafeInteger(result.next_seed)) $('seed').value = String(result.next_seed);
    composeDirty = false;
    const submitted = result.jobs || [result.job];
    const submittedIds = new Set(submitted.map(job => job.id));
    state.jobs = [...submitted, ...state.jobs.filter((job) => !submittedIds.has(job.id))]; renderJobs();
    generateFeedback.show(hasOtherUncertain ? 'warning' : 'success', hasOtherUncertain ? '已提交 · 有待确认任务' : '已提交',
      `已提交 ${repetitions} 轮，每轮 ${count} 个生成任务；完成后在生成结果中查看。${hasOtherUncertain ? '此前提交的结果仍待确认，请查看任务。' : ''}`);
    refresh(true);
  } catch (error) {
    const uncertain = operation && !(error.status >= 400 && error.status < 500);
    if (operation && !uncertain) uncertainRequests.delete(operation.key);
    generateFeedback.show(uncertain ? 'warning' : 'error', uncertain ? '结果待确认 · 重试' : '提交失败 · 重试',
      uncertain ? `提交结果尚未确认：${error.message}。相同内容再次点击生成会复用请求 ID，避免重复任务；修改内容则提交新任务。` : error.message);
  }
  finally { setComposeBusy(false); }
});
$('cancel-pending').addEventListener('click', async () => {
  if (composeBusy) return;
  setComposeBusy(true); cancelPendingFeedback.show('pending', '正在取消…');
  try {
    const result = await api('/api/jobs/cancel-pending', { method: 'POST', body: '{}' });
    cancelPendingFeedback.show('success', result.cancelled_count ? `已取消 ${result.cancelled_count} 个` : '暂无待取消任务',
      `已取消 ${result.cancelled_count} 个待执行的生成任务；已开始的任务和漫游预取保持不变。`);
    await refresh(true);
  } catch (error) { cancelPendingFeedback.show('error', '取消失败 · 重试', error.message); }
  finally { setComposeBusy(false); }
});
$('prompt-source').addEventListener('change', async () => { updateRuleControls(); if ($('prompt-source').value === 'rules' && !ruleConfigsLoaded) await loadRuleConfigs(); });
$('rule-mode').addEventListener('change', updateRuleControls);
$('auto-prompts').addEventListener('change', updateRuleControls);
$('reload-rule-configs').addEventListener('click', () => loadRuleConfigs(true));
$('generate-prompts').addEventListener('click', async () => {
  if (composeBusy) return; setComposeBusy(true);
  promptFeedback.show('pending', '正在抽取…');
  try { await generateRulePrompts(); promptFeedback.show('success', '已抽取'); }
  catch (error) { inlineStatus('rule-generation-note', '', false); promptFeedback.show('error', '抽取失败 · 重试', `抽取失败：${error.message}`); }
  finally { setComposeBusy(false); }
});
for (const id of ['positive', 'negative']) $(id).addEventListener('input', () => {
  const wasAutomatic = $('prompt-source').value === 'rules' && $('auto-prompts').checked;
  $('auto-prompts').checked = afterPromptEdit($('prompt-source').value, $('auto-prompts').checked);
  if ($('prompt-source').value === 'rules') {
    inlineStatus('rule-generation-note', wasAutomatic ? '自动抽取已关闭，使用当前文本。' : '使用当前文本。');
    $('rule-generation-note').dataset.tooltip = '抽取报告对应编辑前的结果，重新勾选自动抽取可恢复共现生成。';
  }
  updateRuleControls();
});
$('generate-form').addEventListener('input', () => { composeDirty = true; });
$('generate-form').addEventListener('change', () => { composeDirty = true; });
window.addEventListener('beforeunload', (event) => { if (composeDirty || settingsDirty || roamDraftDirty() || uncertainRequests.size) { event.preventDefault(); event.returnValue = ''; } });
$('like').addEventListener('click', () => feedback(1));
$('dislike').addEventListener('click', () => feedback(-1));
$('generate-backend').addEventListener('change', updateGenerationHints);
$('previous').addEventListener('click', () => moveImage('older')); $('next').addEventListener('click', () => moveImage('newer'));
$('load-more').addEventListener('click', loadMore);
document.addEventListener('pictide:generated-more', loadMore);
document.addEventListener('pictide:generated-refresh', () => { state.generatedMutationError = ''; refresh(true); });
document.addEventListener('pictide:generated-configure', openSettings);
document.addEventListener('pictide:generated-feedback', event => feedbackGenerated(event.detail.id, event.detail.toggle !== false));
document.addEventListener('pictide:generated-clear', clearGenerated);
document.addEventListener('pictide:liked-more', () => { if (state.view === 'liked') loadMore(); });
document.addEventListener('pictide:liked-refresh', () => { state.likedError = ''; refresh(true); });
document.addEventListener('pictide:liked-feedback', event => feedbackGenerated(event.detail.id, event.detail.toggle !== false, 'liked'));
$('main-image').addEventListener('load', () => syncRoamPlayback(state.artifacts.find(item => item.id === state.activeId)));
$('main-image').addEventListener('error', () => { $('image-error').hidden = false; roamPlayback.pause(); });
document.addEventListener('pictide:roam-playback-toggle', () => roamPlayback.toggle());
document.addEventListener('pictide:roam-playback-interval', event => {
  roamSettings.playback_interval_seconds = event.detail;
  roamPlayback.setInterval(event.detail);
});
$('settings-form').addEventListener('input', () => { settingsDirty = true; });
$('settings-form').addEventListener('change', () => { settingsDirty = true; });
document.querySelectorAll('[data-settings-section]').forEach((button) => button.addEventListener('click', () => setSettingsSection(button.dataset.settingsSection)));
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
document.addEventListener('keydown', (event) => {
  const action = keyboardAction(event, { editing: !!event.target.closest('input,textarea,select,[data-help],[role=combobox],[role=listbox],[role=option],[role=checkbox],[role=radio],[role=tab],[role=dialog],[data-slot=select-content],[data-slot=popover-content],[contenteditable]:not([contenteditable="false"])'), dialogOpen: !!document.querySelector('dialog[open],[role=dialog][data-state=open],[role=alertdialog]'), view: state.view, immersive: immersive.active, feedbackPending: state.feedbackPending });
  if (!action) return;
  event.preventDefault();
  if (action === 'like') feedback(1, false);
  else if (action === 'dislike') feedback(-1, false);
  else if (action === 'privacy') {
    const control = ['generate', 'liked'].includes(state.view) ? document.querySelector(`.generated-privacy-toggle[data-collection="${state.view}"]`) : $(immersive.active ? 'roam-immersive-privacy' : 'roam-privacy');
    control?.click();
  }
  else moveImage(action);
});
window.addEventListener('hashchange', () => setView(location.hash.slice(1) || 'feed', false));
setView(location.hash.slice(1) || 'feed', false);
document.addEventListener('visibilitychange', () => { if (document.hidden) roamPlayback.pause(); else { loadRoamSettings({ preserveDraft: true }); refresh(true); } });
await bootstrap();
updateRuleControls();
let realtimeConnected = false;
let eventSource;
function syncTheme() {
  return loadTheme().catch(error => document.dispatchEvent(new CustomEvent('pictide:theme-error', { detail: `主题读取失败：${error.message}` })));
}
function connectEvents() {
  if (!window.EventSource || eventSource) return;
  eventSource = new EventSource('/api/events');
  eventSource.addEventListener('open', () => { realtimeConnected = true; syncTheme(); loadRoamSettings({ preserveDraft: true }); refresh(true); });
  // Queue another refresh if a change arrives while the current read is in flight.
  eventSource.addEventListener('change', event => {
    try {
      const topic = JSON.parse(event.data).topic;
      if (topic === 'roam_settings') loadRoamSettings({ preserveDraft: true });
      if (topic === 'general_settings') syncTheme();
    } catch {}
    refresh(true);
  });
  eventSource.addEventListener('error', () => { realtimeConnected = false; });
}
connectEvents();
window.addEventListener('pagehide', () => {
  roamPlayback.pause(); roamPageActive = false; viewRevision++; nextImageWait.cancel(); roamWindowLoading = false;
  eventSource?.close(); eventSource = undefined; realtimeConnected = false;
});
window.addEventListener('pageshow', (event) => { roamPageActive = true; if (event.persisted) { renderArtifacts(); connectEvents(); refillRoam(); } });
// Existing polling remains the fallback while SSE is unsupported or reconnecting.
setInterval(() => { if (!realtimeConnected) refresh(); }, 2000);

// Preset changes refresh selectors without resetting generator counters or manual drafts.
document.addEventListener('pictide:candidate-presets-changed', () => { loadRuleConfigs(); if (roamSettingsLoaded) loadRoamConfigs(); });
