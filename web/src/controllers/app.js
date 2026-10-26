import { createLocalGeneration } from './local-generation.js';
import { createBackendSettings } from './backend-settings.js';
import { createPromptSettings } from './prompt-settings.js';
import { createGenerationController } from './generation-controller.js';
import { createModel } from '../shared/model.mjs';
import { onSignal, emitSignal } from '../shared/signals.mjs';
import { publishUiState, subscribeUiActions, bindUiCommands, getUiState } from '../shared/ui-state.mjs';
import { t, tr } from '../i18n/index.mjs';
import { loadTheme } from './theme.mjs';
import { notify, notifyError, notifySuccess, dismissNotification } from '../shared/notifications.mjs';
import { confirmAction } from '../components/confirm-action';
import { destinationIndex, keyboardAction, feedbackValue, steppedFeedbackValue } from './feed-controls.mjs';
import { applyArtifactPage, observeArtifactRevision, retentionDays } from './history-controls.mjs';
import { candidateCount, strongCandidateMultiplier, prefetchCount, maxHistoryImages, createRefillCoordinator, isTemporaryRefillError, mergeRoamDraft, likedTagsWait, roamGenerationChanged } from './roam-controls.mjs';
import { artifactPath, matchesLikedTags } from './generation-controls.mjs';
import { imageSeedLabel } from './backend-controls.mjs';
import { createGalleryCursors, createNextImageWait, roamArtifactPath, roamBoundaryAction, resolveGalleryCursor } from './roam-navigation.mjs';
import { playbackInterval, createRoamPlayback } from './roam-playback.mjs';
import { createImmersiveViewer } from './immersive-controls.mjs';
import { bindTouchNavigation } from './touch-navigation.mjs';
import { createJobPager } from './job-pages.mjs';
import { createPageScroll } from './page-scroll.mjs';
import { createLikedRanking } from './liked-ranking.mjs';

import { playImageTransition, cancelImageTransition } from './image-transitions.mjs';

export function createApplication() {
const disposers = [];
let disposed = false;
const abort = new AbortController();
const listen = (target, type, callback) => target.addEventListener(type, callback, { signal: abort.signal });
let elements = {}, immersive = { active: false, leave() {} };
let roamImageSwitchPending = false;
let applicationUpdating = false;
const state = { backends: [], jobs: [], artifacts: [], view: 'feed', activeId: null, polling: false, saving: false, currentImage: null, feedbackPending: false, feedbackRevision: 0 };
const model = createModel(state);
const changed = model.changed;
Object.assign(state, { privacy: { feed: true, generate: true, liked: true }, availability: 'pending', gallery: { loading: true }, imageReady: false, imageFailed: false, feedbackNotice: null, historyDraft: '1', historyBusy: false, cancellingJobs: [], roamSaving: false });
const galleryCursors = createGalleryCursors();
const pageScroll = createPageScroll();
const nextImageWait = createNextImageWait();
Object.defineProperty(state, 'activeId', { get: () => galleryCursors.get(state.view), set: id => selectImage(id) });
let roamWindowLoading = false, roamBlocked = false, viewRevision = 0;
let roamViewPending = Promise.resolve();
function selectImage(id, view = state.view) {
  const record = galleryCursors.select(view, id);
  if (record) roamViewPending = api('/api/roam/view', { method: 'PUT', keepalive: true, body: JSON.stringify(record) }).catch(error => showNotice(tr`观看位置保存失败：${error.message}`, true));
}
state.likedArtifacts = [];
state.likedError = "";
state.likedTags = [];
state.likedSort = 'latest';
const likedRanking = createLikedRanking({ request: api, changed: ranked => {
  if (state.likedSort !== 'score') return;
  state.likedArtifacts = ranked.artifacts;
  state.likedError = ranked.error;
  state.pages.liked = { total: ranked.total, hasMore: ranked.hasMore, loaded: !ranked.loading, loadedMore: false, cursor: null };
  renderLikedResults();
} });
let likedFilterVersion = 0;
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
const statusNames = { queued: "等待生成", submitting: "正在提交", running: "正在生成", completed: "已完成", failed: "生成失败", cancelled: "已取消", unknown: "状态待确认" };
const activeStatuses = new Set(['queued', 'submitting', 'running']);
let generationFailureSignature = '';
let historyLoaded = false;
let historyLoading = false;
const viewingHistory = () => state.view === 'settings' && state.settingsSection === 'history';
const jobPager = createJobPager({ request: page => api(`/api/jobs?page=${page}`), changed: renderJobPage, active: viewingHistory });
let availabilityRevision = 0;
let availabilitySignature = '';
let roamSettingsLoaded = false, roamSettingsLoading = false;
let roamSettings = { prefetch_count: 2, max_history_images: 20, backend_id: '', preset_id: '', liked_tags_only: false, prompt_mode: 'random', playback_interval_seconds: 8, candidate_count: 10, recommendation_strength: 'standard', strong_candidate_multiplier: 2 };
let roamError = '';
let roamAnchorRetried = false;
let roamPageActive = true, roamVersion = 0;
let roamSettingsSaving = false, roamSwitch = null;
let anchorPrefetchDeferred = false;
const roamPlayback = createRoamPlayback({
  advance: current => moveImage('newer', current),
  changed: detail => publishUiState({ playback: detail }),
  cancelWait: () => { nextImageWait.cancel(); renderArtifacts(); },
});
function syncRoamPlayback(artifact = state.artifacts.find(item => item.id === state.activeId)) {
  publishUiState({ imageId: artifact?.id || null, imageLoading: !!artifact && !state.imageReady && !state.imageFailed, imageReady: !!artifact && state.imageReady, imageFeedback: artifact?.feedback ?? null });
  roamPlayback.update({ imageId: artifact?.id || null, ready: !!artifact && state.imageReady,
    active: state.view === 'feed' && roamPageActive && !document.hidden,
    busy: !!nextImageWait.current || roamWindowLoading || !!roamSwitch || state.feedbackPending, blocked: !!roamSwitch || state.imageFailed });
}
function publishPlaybackInterval(settings) {
  roamPlayback.setInterval(settings.playback_interval_seconds ?? 8);
  publishUiState({ roamOptions: { ...settings } });
}
const refillRoam = createRefillCoordinator({
  active: () => !applicationUpdating && galleryCursors.ready && roamPageActive && roamSettingsLoaded && !roamSwitch && !anchorPrefetchDeferred && !roamBlocked && (!!state.activeId || !!nextImageWait.current) && (roamSettings.prefetch_count > 0 || !!nextImageWait.current) && state.view === 'feed' && !document.hidden,
  version: () => `${roamVersion}:${nextImageWait.current?.token || 0}`,
  anchor: () => state.activeId || null,
  request: anchor_id => api('/api/roam/ensure', { method: 'POST', body: JSON.stringify({ anchor_id, demand: !!nextImageWait.current }) }),
  result: result => {
    state.preparingPrompt = !!result.preparing_prompt; changed();
    roamAnchorRetried = false;
    if (Number.isInteger(result.prefetch_count)) roamSettings.prefetch_count = result.prefetch_count;
    if (result.job && !state.jobs.some(job => job.id === result.job.id)) { state.jobs.unshift(result.job); renderJobs(); }
    if (result.paused) {
      roamBlocked = true; roamPlayback.pause(); nextImageWait.cancel(); renderArtifacts();
      if (result.error !== roamError) { roamError = result.error; showRoamNotice(tr`预取已暂停：${result.error || t("请检查任务状态")}。可在漫游设置中保存后重试。`, true); }
    } else {
      if (likedTagsWait(result, !!nextImageWait.current)) {
        roamBlocked = false; nextImageWait.cancel(); roamPlayback.pause(); renderArtifacts();
        showRoamNotice(t("喜欢图片中暂无可用标签，请先喜欢图片或将偏好范围设为全部"));
        return;
      }
      clearRoamError();
      if (nextImageWait.current && result.ready > 0) refresh(true);
    }
  },
  error: error => {
    if (error.status === 404 && !roamAnchorRetried) { roamAnchorRetried = true; refresh(true); return; }
    roamBlocked = !isTemporaryRefillError(error); nextImageWait.cancel(); renderArtifacts();
    if (error.message !== roamError) { roamError = error.message; showRoamNotice(tr`预取未完成：${error.message}${roamBlocked ? '' : t("。后续页面事件会自动重试。")}`, true); }
  },
});

function clearRoamError() {
  dismissNotification('roam-status');
  roamError = '';
  roamBlocked = false;
}

function showBackendAvailability(available, pending = false) {
  state.availability = pending ? 'pending' : available ? 'available' : 'unavailable'; changed();
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
  if (disposed) throw new Error('Application session closed');
  const response = await fetch(path, { signal: abort.signal, ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  let data;
  try { data = await response.json(); } catch { throw new Error(tr`服务返回了无法解析的响应（HTTP ${response.status}）`); }
  if (!response.ok) { const error = new Error(typeof data.error === 'string' ? data.error : data.error?.message || data.detail || tr`请求失败（HTTP ${response.status}）`); error.status = response.status; throw error; }
  return data;
}
function showRoamNotice(message, error = false) { notify(message, { id: 'roam-status', kind: error ? 'error' : 'info' }); }
function showNotice(message, error = false) { notify(message, { kind: error ? 'error' : 'info' }); }
function historyNotice(message, error = false, kind = 'success') {
  if (!message) { dismissNotification('history-operation'); return; }
  notify(message, { id: 'history-operation', kind: error ? 'error' : kind });
}
const generation = createGenerationController({ state, api, getRoamSettings: () => roamSettings, renderJobs, refresh });
const { updateGenerationHints, updateRuleControls, loadRuleConfigs } = generation;
const backendSettings = createBackendSettings({ state, api, generation, checkBackendAvailability, showBackendAvailability, renderRoamBackends, renderArtifacts, loadRoamSettings });
const promptSettings = createPromptSettings(api);
const localGeneration = createLocalGeneration(api);
const { renderBackends, loadBackend, loadWorkflowLibrary } = backendSettings;

function artifactsForView() { return state.view === 'liked' ? state.likedArtifacts : state.artifacts; }
function pageView() { return ['liked', 'generate'].includes(state.view) ? state.view : 'feed'; }
function applyPage(view, result, append = false) {
  if (view === 'liked' && state.likedSort === 'score') return { accepted: false, reset: false, refresh: false };
  return applyArtifactPage(state, view, result, typeof append === 'object' ? append : { append });
}
const viewTitles = { feed: "漫游", generate: "生成", liked: "喜欢", prompts: "提示词", settings: "设置" };
function setView(route, updateUrl = true) {
  const [requested, section] = String(route || 'feed').split('/');
  const view = Object.hasOwn(viewTitles, requested) ? requested : 'feed';
  if (state.feedbackPending) { showNotice(t("正在保存评价，请稍候。")); return; }
  const enteringLiked = view === 'liked' && state.view !== 'liked';
  if (view !== 'liked') likedRanking.cancel();
  pageScroll.save();
  if (view !== state.view) { if (view !== 'feed') roamPlayback.pause(); immersive.leave(); viewRevision++; nextImageWait.cancel(); roamWindowLoading = false; }
  state.view = view;
  publishUiState({ route: view === 'settings' ? `settings/${section || state.settingsSection}` : view, ...(view !== 'feed' ? { waiting: false } : {}) });
  emitSignal('close-image-info');
  if (view === 'settings' && ['general', 'backend', 'llm', 'roam', 'history'].includes(section)) state.settingsSection = section;
  const editor = view === 'prompts';
  changed();
  if (view !== 'feed') emitSignal('roam-options-close');
  if (view === 'settings') setSettingsSection(state.settingsSection, false);
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#${view}${view === 'settings' ? `/${state.settingsSection}` : ''}`);
  // Keep controllers and their inputs mounted: navigation never discards drafts.
  if (!editor) { renderArtifacts(); renderJobs(); if (galleryCursors.ready) refresh(true); }
  if (enteringLiked && state.likedSort === 'score') likedRanking.load(state.likedTags);
  refillRoam();
  pageScroll.restore(view);
}
function setSettingsSection(section, updateUrl = true) {
  if (!['general', 'backend', 'llm', 'roam', 'history'].includes(section)) section = 'general';
  state.settingsSection = section;
  if (state.view === 'settings') publishUiState({ route: `settings/${section}` });
  changed();
  if (section === 'roam' && !roamSettingsLoading && !roamSettingsLoaded) loadRoamSettings();
  if (section === 'history') {
    if (!historyLoaded && !historyLoading) loadHistorySettings();
    jobPager.load();
  }
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#settings/${section}`);
}
function renderGalleryLoading() {
  state.gallery = { loading: true, waiting: true, artifact: null };
  state.imageReady = false; syncRoamPlayback(); immersive.leave(); changed();
}
function renderArtifacts() {
  renderGeneratedResults(); renderLikedResults();
  if (state.view !== 'feed') { changed(); return; }
  if (!galleryCursors.ready) { renderGalleryLoading(); return; }
  const items = state.artifacts, page = state.pages.feed;
  const selection = resolveGalleryCursor(items, state.activeId, page.loaded);
  if (selection.loading) { renderGalleryLoading(); return; }
  const waiting = !!nextImageWait.current || roamWindowLoading || !!roamSwitch;
  publishUiState({ waiting });
  if (selection.id !== state.activeId) state.activeId = selection.id;
  const index = Math.max(0, items.findIndex(item => item.id === state.activeId));
  const artifact = items[index];
  state.gallery = { artifact, waiting, loading: false,
    previousDisabled: (index >= items.length - 1 && !page.hasMore) || state.feedbackPending || roamWindowLoading || !!roamSwitch,
    nextDisabled: state.feedbackPending || waiting };
  if (!artifact) {
    cancelImageTransition(elements.image); roamImageSwitchPending = false; immersive.leave(); state.currentImage = null; state.imageReady = false;
    publishUiState({ imageInfo: null }); syncRoamPlayback(); changed(); return;
  }
  publishUiState({ imageInfo: { id: artifact.id, seed: artifact.seed_applied === false ? imageSeedLabel(artifact) : String(artifact.seed ?? '—'), sourcePositive: artifact.source_prompts?.positive ?? artifact.positive ?? '', positive: artifact.positive || '', negative: artifact.negative || '' } });
  if (state.currentImage !== artifact.id) {
    clearFeedbackNotice(); cancelImageTransition(elements.image); roamImageSwitchPending = state.currentImage !== null;
    state.currentImage = artifact.id; state.imageFailed = false; state.imageReady = false; dismissNotification('roam-image-error');
  }
  syncRoamPlayback(artifact); changed();
}
function advanceWaitingImage() {
  const next = nextImageWait.consume(state.artifacts, galleryCursors.get('feed'), state.view === 'feed' && roamPageActive && !document.hidden);
  if (next) selectImage(next);
}
function requestNextRoamImage() {
  if (!galleryCursors.ready || roamSwitch || nextImageWait.current || state.view !== 'feed') return;
  if (!state.backends.length) { roamPlayback.pause(); showNotice(t("请先在设置中配置生图 API。"), true); return; }
  clearRoamError();
  nextImageWait.begin(state.activeId); renderArtifacts(); refillRoam();
}
async function moveImage(direction, automatic = null) {
  if (state.feedbackPending || !galleryCursors.ready || roamWindowLoading || roamSwitch) return;
  if (automatic && !automatic()) return;
  if (!automatic && state.view === 'feed') {
    roamPlayback.prepareNavigation(direction);
    roamPlayback.restart();
  }
  if (!state.pages[pageView()].loaded) { refresh(true); return; }
  if (state.view === 'feed' && direction === 'newer') anchorPrefetchDeferred = false;
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
      } catch (error) { if (automatic && !isTemporaryRefillError(error)) roamPlayback.pause(); showNotice(tr`图片加载失败：${error.message}`, true); }
      finally { if (revision === viewRevision) roamWindowLoading = false; renderArtifacts(); refillRoam(); }
    } else if (action === 'generate') requestNextRoamImage();
    else renderArtifacts();
    return;
  }
  if (destination === null) { showNotice(items.length ? direction === 'newer' ? t("已经是最新的一张。") : state.pages[pageView()].hasMore ? t("已到已加载图片的末尾，请点击加载更早图片。") : t("已经是最早的一张。") : t("还没有可以浏览的图片。")); return; }
  state.activeId = items[destination].id; renderArtifacts(); refillRoam();
}
let feedbackMotionTimer;
function clearFeedbackNotice() { clearTimeout(feedbackMotionTimer); state.feedbackNotice = null; changed(); }
function showFeedbackNotice(value, previous) {
  clearFeedbackNotice(); state.feedbackNotice = { value, previous }; changed();
  feedbackMotionTimer = setTimeout(clearFeedbackNotice, 900);
}
function stepFeedback(direction) {
  if (state.feedbackPending) return;
  const artifact = artifactsForView().find(item => item.id === state.activeId);
  if (artifact) {
    clearFeedbackNotice();
    return feedback(steppedFeedbackValue(artifact.feedback, direction), false, true);
  }
}
async function feedback(value, toggle = true, animate = false) {
  if (value === 1 && state.view === 'feed') roamPlayback.pauseForLike();
  if (state.feedbackPending) return;
  const artifact = artifactsForView().find((item) => item.id === state.activeId); if (!artifact) { showNotice(t("还没有可以评价的图片。")); return; }
  const nextValue = toggle ? feedbackValue(artifact.feedback, value) : value;
  if (nextValue === artifact.feedback) {
    if (animate) showFeedbackNotice(nextValue, artifact.feedback);
    return;
  }
  const artifactRevision = state.artifactRevision;
  state.feedbackPending = true;
  renderArtifacts();
  try {
    if (state.view === 'liked' && nextValue === null && !await confirmAction(t("确定取消喜欢这张图片？取消后将从喜欢页面移除，并受自动清理规则影响。"))) return;
    const result = await api(`/api/artifacts/${encodeURIComponent(artifact.id)}/feedback`, { method: 'PUT', body: JSON.stringify({ value: nextValue }) }); state.feedbackRevision++; observeArtifactRevision(state, result.revision ?? result.artifact_revision); if (artifactRevision === state.artifactRevision) { const delta = Number(result.artifact.feedback === 1) - Number(artifact.feedback === 1); if (state.likedSort !== 'score' && matchesLikedTags(result.artifact, state.likedTags)) state.pages.liked.total += delta; replaceArtifact(result.artifact); } renderArtifacts();
    if (animate && state.view === 'feed' && state.currentImage === artifact.id) showFeedbackNotice(result.artifact.feedback, artifact.feedback);
  }
  catch (error) { showNotice(error.status === 404 || error.status === 410 ? t("图片已清理或不可用，正在刷新列表。") : error.message, true); }
  finally { state.feedbackPending = false; renderArtifacts(); await refresh(true); }
}
function replaceArtifact(artifact) {
  state.artifacts = state.artifacts.map((item) => item.id === artifact.id ? artifact : item);
  state.generatedArtifacts = state.generatedArtifacts.map((item) => item.id === artifact.id ? artifact : item);
  if (state.likedSort === 'score') { if (state.view === 'liked') likedRanking.update(artifact); return; }
  if (artifact.feedback === 1 && matchesLikedTags(artifact, state.likedTags)) {
    const index = state.likedArtifacts.findIndex((item) => item.id === artifact.id);
    if (index >= 0) state.likedArtifacts[index] = artifact;
    else state.likedArtifacts = [artifact, ...state.likedArtifacts].sort((a,b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id.localeCompare(a.id));
  } else state.likedArtifacts = state.likedArtifacts.filter((item) => item.id !== artifact.id);
}
function renderJobs() { renderGeneratedResults(); }
function renderJobPage(page) {
  state.jobPage = { ...page }; changed();
  if (page.error) notifyError(page.error, { id: 'jobs-page-error', action: { label: () => t('重试'), onClick: () => jobPager.load() } });
  else dismissNotification('jobs-page-error');
}
function renderGeneratedResults() {
  const manual = state.jobs.filter(job => job.source !== 'roam');
  const pending = manual.filter(job => activeStatuses.has(job.status));
  const latest = manual[0];
  const failureSignature = latest && ['failed', 'unknown'].includes(latest.status) && latest.error ? JSON.stringify([latest.id, latest.status, latest.error]) : '';
  if (state.view === 'generate' && failureSignature !== generationFailureSignature) {
    generationFailureSignature = failureSignature;
    if (failureSignature) notify(latest.error, { id: 'generation-task-error', kind: latest.status === 'unknown' ? 'warning' : 'error' });
    else dismissNotification('generation-task-error');
  }
  const status = pending.length ? tr`${pending.length} 个任务生成中` : latest && ['failed', 'unknown', 'cancelled'].includes(latest.status) ? t(statusNames[latest.status]) : '';
  publishUiState({ generatedResults: {
    artifacts: state.generatedArtifacts, total: state.pages.generate.total,
    hasMore: state.pages.generate.hasMore, loading: (!state.generatedLoaded || !state.pages.generate.loaded) && !state.generatedError && !state.generatedMutationError || state.loadingMore,
    error: state.generatedMutationError || state.generatedError, pending: pending.length > 0, status,
    feedbackPending: state.feedbackPending, mutationPending: state.generatedMutationPending, visible: state.view === 'generate', configured: state.backends.length > 0,
  } });
}
function renderLikedResults() {
  publishUiState({ likedResults: {
    artifacts: state.likedArtifacts, total: state.pages.liked.total,
    sort: state.likedSort, tags: state.likedTags, refreshedAt: likedRanking.snapshot().refreshedAt, filterVersion: likedFilterVersion, revision: state.feedbackRevision + state.artifactRevision,
    hasMore: state.pages.liked.hasMore, loading: state.likedSort === 'score' ? likedRanking.snapshot().loading : !state.pages.liked.loaded && !state.likedError || state.loadingMore,
    error: state.likedError, feedbackPending: state.feedbackPending,
    mutationPending: state.generatedMutationPending, visible: state.view === 'liked', configured: state.backends.length > 0,
  } });
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
    if (view === 'liked' && value === null && !await confirmAction(t("确定取消喜欢这张图片？取消后将从喜欢页面移除，并受自动清理规则影响。"))) return;
    const result = await api(`/api/artifacts/${encodeURIComponent(id)}/feedback`, { method: 'PUT', body: JSON.stringify({ value }) });
    state.feedbackRevision++;
    observeArtifactRevision(state, result.revision ?? result.artifact_revision);
    if (view === 'liked' && state.likedSort === 'score') { replaceArtifact(result.artifact); }
    else if (revision === state.artifactRevision) { if (state.likedSort !== 'score' && matchesLikedTags(result.artifact, state.likedTags)) state.pages.liked.total += Number(result.artifact.feedback === 1) - Number(artifact.feedback === 1); replaceArtifact(result.artifact); }
  } catch (error) { const message = error.status === 404 || error.status === 410 ? t("图片已清理或不可用，正在刷新列表。") : error.message; if (view === 'liked') state.likedError = message; else state.generatedMutationError = message; }
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
    state.generatedMutationError = `${committed ? t("图片已处理，列表刷新失败") : t("清理失败")}：${error.message}`;
  } finally {
    state.generatedMutationPending = false; renderGeneratedResults(); await refresh(true);
  }
}
async function cancelJob(id) {
  if (state.cancellingJobs.includes(id)) return;
  state.cancellingJobs.push(id); changed();
  try { const result = await api(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }); state.jobs = state.jobs.map((job) => job.id === id ? result.job : job); renderJobs(); if (viewingHistory()) await jobPager.load(); }
  catch (error) { showNotice(error.message, true); }
  finally { state.cancellingJobs = state.cancellingJobs.filter(item => item !== id); changed(); }
}
async function refresh(force = false) {
  if (applicationUpdating) return;
  if (!galleryCursors.ready) return;
  if (document.hidden && !force || state.polling) { if (force) state.refreshQueued = true; return; }
  state.polling = true;
  const feedbackRevision = state.feedbackRevision;
  const windowVersion = roamVersion;
  const view = pageView();
  const filterVersion = likedFilterVersion;
  const rankedLiked = view === 'liked' && state.likedSort === 'score';
  const anchor = galleryCursors.get('feed');
  try {
    const [jobs, artifacts] = await Promise.all([api('/api/jobs'), rankedLiked ? Promise.resolve(null) : api(view === 'feed' ? roamArtifactPath(anchor) : artifactPath(view, null, state.likedTags)), viewingHistory() ? jobPager.load() : Promise.resolve()]);
    state.jobs = jobs.jobs;
    // Multi-round counters must come from the idempotent response, even if jobs
    // already appear in events. Retain the original request for a safe retry.
    generation.observeJobs();
    if (!state.feedbackPending && !state.generatedMutationPending && feedbackRevision === state.feedbackRevision) {
      if (view !== 'feed') {
        if (artifacts && (view !== 'liked' || filterVersion === likedFilterVersion)) applyPage(view, artifacts, { replace: !state.pages[view].loaded });
      }
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
    if (view === 'liked' && state.likedSort !== 'score' && filterVersion === likedFilterVersion) state.likedError = '';
    renderJobs(); renderArtifacts();
    if (state.view === 'feed') roamPlayback.retry();
  }
  catch (error) {
    if (view === 'liked' && filterVersion !== likedFilterVersion) return;
    if (view === 'generate') { state.generatedError = tr`同步失败：${error.message}`; renderGeneratedResults(); }
    if (view === 'liked' && state.likedSort !== 'score') { state.likedError = tr`同步失败：${error.message}`; renderLikedResults(); }
    if (nextImageWait.current) { nextImageWait.cancel(); roamBlocked = !isTemporaryRefillError(error); renderArtifacts(); }
    if (view === 'feed' || rankedLiked) showNotice(tr`同步失败：${error.message}`, true);
  }
  finally { state.polling = false; if (state.refreshQueued) { state.refreshQueued = false; await refresh(true); } else refillRoam(); }
}
async function loadMore() {
  if (state.loadingMore || state.feedbackPending || state.generatedMutationPending) return;
  const view = pageView();
  if (view === 'liked' && state.likedSort === 'score') { likedRanking.more(); return; }
  const page = state.pages[view]; if (!page.hasMore || !page.cursor) return;
  state.loadingMore = true; const revision = state.feedbackRevision; renderArtifacts();
  const artifactRevision = state.artifactRevision;
  const filterVersion = likedFilterVersion;
  try { const result = await api(artifactPath(view, page.cursor, state.likedTags)); if (!state.feedbackPending && !state.generatedMutationPending && revision === state.feedbackRevision && (view !== 'liked' || filterVersion === likedFilterVersion)) { const applied = applyPage(view, result, { append: true, requestRevision: artifactRevision }); if (applied.refresh) await refresh(true); } }
  catch (error) { if (view === 'liked' && filterVersion !== likedFilterVersion) return; if (view === 'generate') state.generatedError = tr`加载失败：${error.message}`; if (view === 'liked') state.likedError = tr`加载失败：${error.message}`; if (view === 'feed') showNotice(tr`加载失败：${error.message}`, true); }
  finally { state.loadingMore = false; renderArtifacts(); }
}
function openSettings() {
  if (!backendSettings.initialized) loadBackend(backendSettings.model.data.draft.selectedId);
  setView('settings/backend');
}
function renderRoamBackends() { changed(); }
const roamFields = ['recommendation_strength', 'strong_candidate_multiplier', 'candidate_count', 'prefetch_count', 'max_history_images', 'backend_id', 'playback_interval_seconds', 'liked_tags_only', 'prompt_mode'];
state.roamDraft = Object.fromEntries(roamFields.map(key => [key, roamSettings[key]]));
function roamDraftDirty() { return roamFields.some(key => String(state.roamDraft[key]) !== String(roamSettings[key])); }
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
  if (transition?.resume && !anchorPrefetchDeferred && transition.view === viewRevision && state.view === 'feed' && !document.hidden && !roamBlocked && !roamPlayback.playing) roamPlayback.toggle();
  refillRoam();
}
async function applyRoamSettings(settings, savedFields = []) {
  const next = { ...settings, recommendation_strength: settings.recommendation_strength ?? 'standard', strong_candidate_multiplier: strongCandidateMultiplier(settings.strong_candidate_multiplier ?? 2), candidate_count: candidateCount(settings.candidate_count ?? 10), prefetch_count: prefetchCount(settings.prefetch_count ?? 2), max_history_images: maxHistoryImages(settings.max_history_images ?? 20), liked_tags_only: !!settings.liked_tags_only, prompt_mode: settings.prompt_mode ?? 'random', playback_interval_seconds: settings.playback_interval_seconds ?? 8 };
  if (!roamSettingsLoaded || next.preset_id !== roamSettings.preset_id) {
    generation.selectPreset(next.preset_id);
  }
  const switched = roamSettingsLoaded && roamGenerationChanged(roamSettings, next);
  if (roamSettingsLoaded && JSON.stringify(roamSettings.pinned_positive ?? []) !== JSON.stringify(next.pinned_positive ?? [])) {
    // Saving anchors still discards the old window, but editing must not launch
    // replacements through settings/SSE/page refresh events. Next navigation resumes it.
    anchorPrefetchDeferred = true;
  }
  if (switched) beginRoamSwitch();
  const merged = mergeRoamDraft(roamSettings, next, state.roamDraft, savedFields);
  state.roamDraft = merged; changed();
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
    await applyRoamSettings(settings, preserveDraft ? [] : roamFields);
    renderRoamBackends();
  } catch (error) { notifyError(() => tr`设置读取失败：${error.message}`, { id: 'roam-settings' }); }
  finally { roamSettingsLoading = false; }
}
async function saveRoamSettings(patch) {
  if (roamSettingsSaving) throw new Error(t("正在保存漫游设置，请稍候。"));
  // The existing full-settings API requires a prefetch count when changing presets.
  if (Object.hasOwn(patch, 'preset_id') && !Object.hasOwn(patch, 'prefetch_count')) patch = { ...patch, prefetch_count: roamSettings.prefetch_count };
  roamSettingsSaving = true;
  const switched = roamGenerationChanged(roamSettings, { ...roamSettings, ...patch });
  if (switched) beginRoamSwitch();
  try {
    if (switched) await roamViewPending; // Store clears the window after the persisted current picture.
    const result = await api('/api/settings/roam', { method: 'PUT', body: JSON.stringify(patch) });
    await applyRoamSettings(result, Object.keys(patch));
    if (Object.hasOwn(patch, 'preset_id')) generation.selectPreset(result.preset_id);
    return result;
  } catch (error) { if (roamSwitch) finishRoamSwitch(); throw error; }
  finally { roamSettingsSaving = false; }
}
async function submitRoamSettings() {
  if (state.roamSaving) return;
  state.roamSaving = true; changed();
  try {
    const draft = state.roamDraft;
    const payload = { recommendation_strength: draft.recommendation_strength, strong_candidate_multiplier: strongCandidateMultiplier(draft.strong_candidate_multiplier), candidate_count: candidateCount(draft.candidate_count), prefetch_count: prefetchCount(draft.prefetch_count), max_history_images: maxHistoryImages(draft.max_history_images), backend_id: draft.backend_id, playback_interval_seconds: playbackInterval(draft.playback_interval_seconds), liked_tags_only: draft.liked_tags_only, prompt_mode: draft.prompt_mode };
    await saveRoamSettings(payload); notifySuccess(() => t('已保存漫游设置。'), { id: 'roam-settings' }); await refresh(true);
  } catch (error) { notifyError(error.message, { id: 'roam-settings' }); }
  finally { state.roamSaving = false; changed(); }
}
async function bootstrap() {
  try {
    const data = await api('/api/bootstrap'); state.backends = data.backends || []; state.jobs = data.jobs || []; state.artifacts = data.artifacts || []; state.artifactRevision = data.artifact_revision ?? 0; state.dataDirectory = data.data_directory || '';
    galleryCursors.restore(data.roam_view || {});
    if (data.artifact_page?.anchor_id !== undefined && galleryCursors.get('feed') && !state.artifacts.some(item => item.id === galleryCursors.get('feed'))) selectImage(data.artifact_page.anchor_id, 'feed');
    state.pages.feed.loaded = true; state.pages.feed.total = data.counts?.roam ?? state.artifacts.length; state.pages.feed.hasMore = data.artifact_page?.has_more ?? state.pages.feed.total > state.artifacts.length; state.pages.feed.hasNewer = !!data.artifact_page?.has_newer; state.pages.feed.cursor = data.artifact_page?.next_cursor ?? state.artifacts.at(-1)?.id ?? null; state.pages.liked.total = data.counts?.liked ?? 0; state.pages.generate.total = data.counts?.generate ?? 0;
    state.backendTypes = data.backend_types;
    renderBackends(); renderJobs(); renderArtifacts();
    if (data.roam_settings) await applyRoamSettings(data.roam_settings, roamFields);
    if (viewingHistory()) jobPager.load();
    changed();
    await loadWorkflowLibrary();
    loadBackend(backendSettings.model.data.draft.selectedId);
    if (!roamSettingsLoaded) await loadRoamSettings();
    publishUiState({ ready: true });
  } catch (error) { showNotice(tr`无法读取平台数据：${error.message}`, true); }
}

async function loadHistorySettings() {
  historyLoading = true;
  state.historyBusy = true; changed();
  historyNotice(() => t("正在读取清理设置…"), false, 'info');
  try {
    const result = await api('/api/settings/history');
    state.historyDraft = String(retentionDays(result.unliked_retention_days));
    if (observeArtifactRevision(state, result.artifact_revision)) { renderArtifacts(); await refresh(true); }
    historyLoaded = true; historyNotice('');
  } catch (error) {
    try { retentionDays(state.historyDraft); } catch { state.historyDraft = '1'; }

    historyNotice(() => tr`读取失败：${error.message}。配置损坏时过期清理会暂停；可修改天数并重新保存以修复设置。`, true);
  } finally { historyLoading = false; state.historyBusy = false; changed(); }
}
async function saveHistory() {
  if (state.historyBusy) return;
  try {
    const days = retentionDays(state.historyDraft);
    state.historyBusy = true; changed();
    const result = await api('/api/settings/history', { method: 'PUT', body: JSON.stringify({ unliked_retention_days: days }) });
    state.historyDraft = String(retentionDays(result.unliked_retention_days));
    historyLoaded = true;
    if (observeArtifactRevision(state, result.artifact_revision)) renderArtifacts();
    historyNotice(() => days ? tr`已保存：未标记喜欢的图片保留 ${days} 天。` : t("已关闭自动清理。"));
    await refresh(true);
  } catch (error) { historyNotice(error.message, true); }
  finally { state.historyBusy = false; changed(); }
}
const commands = {
  'roam-settings-save': saveRoamSettings,
  'generated-more': loadMore,
  'generated-refresh': () => { state.generatedMutationError = ''; return refresh(true); },
  'generated-configure': openSettings,
  'generated-feedback': value => feedbackGenerated(value.id, value.toggle !== false),
  'generated-clear': clearGenerated,
  'liked-more': () => { if (state.view === 'liked') return loadMore(); },
  'liked-refresh': () => { if (state.likedSort === 'score') return likedRanking.load(state.likedTags, true); state.likedError = ''; return refresh(true); },
  'liked-feedback': value => feedbackGenerated(value.id, value.toggle !== false, 'liked'),
  'roam-playback-toggle': () => roamPlayback.toggle(),
  'before-update': () => !(localGeneration.model.data.dirty || localGeneration.model.data.busy || generation.dirty || backendSettings.dirty || promptSettings.model.data.dirty || promptSettings.model.data.signingIn || roamDraftDirty() || getUiState().editorDirty),
  'updating': () => { applicationUpdating = true; roamPlayback.pause(); },
  'update-finished': () => { applicationUpdating = false; return refresh(true); },
};
commands['liked-filter'] = value => {
  if (state.feedbackPending || state.generatedMutationPending) return;
  const tags = [...new Set(value.tags)];
  if (JSON.stringify(tags) === JSON.stringify(state.likedTags)) return;
  state.likedTags = tags; likedFilterVersion++;
  state.likedArtifacts = []; state.likedError = '';
  state.pages.liked = { hasMore: false, cursor: null, total: 0, loadedMore: false, loaded: false };
  elements.liked.scrollTop = 0;
  if (state.likedSort === 'score') { likedRanking.clear(); likedRanking.load(state.likedTags); }
  else { renderLikedResults(); refresh(true); }
};

commands['liked-sort'] = value => {
  const sort = value.sort;
  if (!['latest', 'score'].includes(sort) || state.likedSort === sort || state.feedbackPending) return;
  likedRanking.cancel(); state.likedSort = sort; likedFilterVersion++;
  state.likedArtifacts = []; state.likedError = '';
  state.pages.liked = { hasMore: false, cursor: null, total: 0, loadedMore: false, loaded: false };
  elements.liked.scrollTop = 0;
  if (sort === 'score') { likedRanking.clear(); likedRanking.load(state.likedTags); }
  else { renderLikedResults(); refresh(true); }
};
function setPrivacy(view, value) { state.privacy[view] = value; changed(); }
function imageLoaded() {
  state.imageReady = true; state.imageFailed = false;
  if (roamImageSwitchPending) { roamImageSwitchPending = false; playImageTransition(elements.image); }
  syncRoamPlayback(); changed();
}
function imageFailed() {
  if (!state.imageFailed) notifyError(() => t('图片读取失败，请检查服务与文件是否可用。'), { id: 'roam-image-error' });
  state.imageFailed = true; state.imageReady = false; roamImageSwitchPending = false;
  cancelImageTransition(elements.image); roamPlayback.pause(); syncRoamPlayback(); changed();
}
let realtimeConnected = false, eventSource, fallbackTimer;
function mount(refs) {
  elements = refs;
  immersive = createImmersiveViewer({ card: refs.card, toolbar: refs.toolbar, entry: refs.immersiveEntry, focusReturn: refs.options, exit: refs.immersiveExit,
    eligible: () => state.view === 'feed' && !!state.currentImage,
    changed: active => { state.immersive = active; publishUiState({ roamImmersive: active }); clearFeedbackNotice(); emitSignal('roam-options-close'); changed(); } });
  disposers.push(() => immersive.dispose());
  disposers.push(bindTouchNavigation(refs.stage, { navigate: direction => moveImage(direction), adjustFeedback: stepFeedback,
    verticalEnabled: () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true,
    enabled: () => state.view === 'feed' && !!state.currentImage && !state.feedbackPending && !document.querySelector('[role=dialog][data-state=open],[role=alertdialog],[data-slot=popover-content][data-state=open]') }));
  disposers.push(bindUiCommands(commands));
  listen(window, 'beforeunload', event => { if (!commands['before-update']()) { event.preventDefault(); event.returnValue = ''; } });
listen(document, 'keydown', (event) => {
  const action = keyboardAction(event, { editing: !!event.target.closest('input,textarea,select,[data-help],[role=combobox],[role=listbox],[role=option],[role=checkbox],[role=radio],[role=tab],[role=dialog],[data-slot=select-content],[data-slot=popover-content],[contenteditable]:not([contenteditable="false"])'), dialogOpen: !!document.querySelector('dialog[open],[role=dialog][data-state=open],[role=alertdialog]'), view: state.view, immersive: immersive.active, feedbackPending: state.feedbackPending });
  if (!action) return;
  event.preventDefault();
  if (action === 'increase') stepFeedback(1);
  else if (action === 'decrease') stepFeedback(-1);
  else if (action === 'privacy') {
    setPrivacy(state.view, !state.privacy[state.view]);
  }
  else moveImage(action);
});
listen(window, 'hashchange', () => setView(location.hash.slice(1) || 'feed', false));
setView(location.hash.slice(1) || 'feed', false);
disposers.push(subscribeUiActions((name, value) => { if (name === 'navigate') setView(value); }));
listen(document, 'visibilitychange', () => { if (applicationUpdating) return; if (document.hidden) roamPlayback.pause(); else { loadRoamSettings({ preserveDraft: true }); refresh(true); } });
void bootstrap().then(() => { if (!disposed) { updateRuleControls(); connectEvents(); } });
function syncTheme() {
  return loadTheme().catch(error => emitSignal('theme-error', tr`主题读取失败：${error.message}`));
}
function connectEvents() {
  if (!window.EventSource || eventSource) return;
  eventSource = new EventSource('/api/events');
  eventSource.addEventListener('open', () => { realtimeConnected = true; emitSignal('updates-changed'); void localGeneration.load(); if (applicationUpdating) return; syncTheme(); loadRoamSettings({ preserveDraft: true }); refresh(true); });
  // Queue another refresh if a change arrives while the current read is in flight.
  eventSource.addEventListener('change', event => {
    try {
      const topic = JSON.parse(event.data).topic;
      if (topic === 'local_generation') { void localGeneration.load(); return; }
      if (topic === 'backends') void localGeneration.load();
      if (topic === 'updates') { emitSignal('updates-changed'); return; }
      if (topic === 'prompting') { void promptSettings.load(true); emitSignal('prompt-settings-changed'); }
      if (topic === 'roam_settings' || topic === 'candidate') loadRoamSettings({ preserveDraft: true });
      if (topic === 'candidate') emitSignal('candidate-library-changed');
      if (topic === 'general_settings') syncTheme();
      if (topic === 'feedback') {
        state.feedbackRevision++;
        if (state.likedTags.length && state.likedSort !== 'score') { state.pages.liked.loaded = false; state.pages.liked.loadedMore = false; }
        renderLikedResults();
      }
    } catch {}
    refresh(true);
  });
  eventSource.addEventListener('error', () => { realtimeConnected = false; });
}
listen(window, 'pagehide', () => {
  roamPlayback.pause(); roamPageActive = false; viewRevision++; nextImageWait.cancel(); roamWindowLoading = false;
  eventSource?.close(); eventSource = undefined; realtimeConnected = false;
});
listen(window, 'pageshow', (event) => { roamPageActive = true; if (event.persisted) { renderArtifacts(); connectEvents(); refillRoam(); } });
// Existing polling remains the fallback while SSE is unsupported or reconnecting.
fallbackTimer = setInterval(() => { if (!realtimeConnected) refresh(); }, 2000);

// Preset changes refresh selectors without resetting generator counters or manual drafts.
disposers.push(onSignal('candidate-presets-changed', () => { loadRuleConfigs(); }));
disposers.push(onSignal('prompt-settings-changed', () => { generation.invalidatePrompt(); }));


disposers.push(onSignal('language-changed', () => { changed(); generation.model.changed(); backendSettings.model.changed(); renderJobPage(jobPager.state); renderArtifacts(); }));
  return () => {
    disposed = true; abort.abort(); clearInterval(fallbackTimer); clearTimeout(feedbackMotionTimer);
    promptSettings.dispose(); localGeneration.dispose();
    roamPlayback.pause(); nextImageWait.cancel(); likedRanking.cancel(); eventSource?.close();
    for (const dispose of disposers.splice(0)) dispose();
  };
}
return { model, generation, backendSettings, promptSettings, localGeneration, mount, commands, setPrivacy, setView, setSettingsSection, openSettings, moveImage, feedback,
  requestNextRoamImage, imageLoaded, imageFailed, cancelJob, jobPager, saveHistory, submitRoamSettings,
  editRoam(patch) { Object.assign(state.roamDraft, patch); changed(); },
  editHistory(value) { state.historyDraft = value; changed(); },
};
}
