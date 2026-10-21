import { createBackendSettings } from './backend-settings.js';
import { createGenerationController } from './generation-controller.js';
import { $, localizedMessages, describeAction, inlineStatus, translatedOption, option, dateLabel } from './dom-utils.mjs';
import { publishUiState, subscribeUiActions } from '../shared/ui-state.mjs';
import { t, tr, locale } from '../i18n/index.mjs';
import { loadTheme } from './theme.mjs';
import { notify, notifyError, notifySuccess, dismissNotification } from '../shared/notifications.mjs';
import { decorateElement, createIcon } from "../dom-primitives";
import { confirmAction } from '../components/confirm-action';
import { destinationIndex, keyboardAction, feedbackValue, steppedFeedbackValue } from './feed-controls.mjs';
import { applyArtifactPage, observeArtifactRevision, retentionDays } from './history-controls.mjs';
import { candidateCount, strongCandidateMultiplier, prefetchCount, maxHistoryImages, createRefillCoordinator, isTemporaryRefillError, mergeRoamDraft, likedTagsWait, roamGenerationChanged } from './roam-controls.mjs';
import { artifactPath, matchesLikedTags } from './generation-controls.mjs';
import { backendCapabilities, imageSeedLabel } from './backend-controls.mjs';
import { createGalleryCursors, createNextImageWait, roamArtifactPath, roamBoundaryAction, resolveGalleryCursor } from './roam-navigation.mjs';
import { playbackInterval, createRoamPlayback } from './roam-playback.mjs';
import { createImmersiveViewer } from './immersive-controls.mjs';
import { bindTouchNavigation } from './touch-navigation.mjs';
import { createJobPager } from './job-pages.mjs';
import { createPageScroll } from './page-scroll.mjs';
import { createLikedRanking } from './liked-ranking.mjs';

import { playImageTransition, cancelImageTransition } from './image-transitions.mjs';

let roamImageSwitchPending = false;
const state = { backends: [], jobs: [], artifacts: [], view: 'feed', activeId: null, polling: false, saving: false, currentImage: null, feedbackPending: false, feedbackRevision: 0 };
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
let jobsSignature = '';
let generationFailureSignature = '';
let historyLoaded = false;
let historyLoading = false;
const expandedJobs = new Set();
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
  changed: detail => document.dispatchEvent(new CustomEvent('pictide:roam-playback-state', { detail })),
  cancelWait: () => { nextImageWait.cancel(); renderArtifacts(); },
});
function syncRoamPlayback(artifact = null) {
  const image = $('main-image');
  publishUiState({ imageId: artifact?.id || null,
    imageLoading: !!artifact && state.currentImage === artifact.id && !image.complete && $('image-error').hidden,
    imageReady: !!artifact && state.currentImage === artifact.id && image.complete && image.naturalWidth > 0 && $('image-error').hidden,
    imageFeedback: artifact?.feedback ?? null });
  roamPlayback.update({ imageId: artifact?.id || null,
    ready: !!artifact && state.currentImage === artifact.id && image.complete && image.naturalWidth > 0 && $('image-error').hidden,
    active: state.view === 'feed' && roamPageActive && !document.hidden,
    busy: !!nextImageWait.current || roamWindowLoading || !!roamSwitch || state.feedbackPending,
    // A paused generator must not disable playback of already saved pictures.
    blocked: !!roamSwitch || !$('image-error').hidden,
  });
}
function publishPlaybackInterval(settings) {
  document.dispatchEvent(new CustomEvent('pictide:roam-playback-interval', { detail: settings.playback_interval_seconds ?? 8 }));
  document.dispatchEvent(new CustomEvent('pictide:roam-options-settings', { detail: settings }));
}
const immersive = createImmersiveViewer({
  card: $('image-card'), toolbar: document.querySelector('.image-toolbar'),
  entry: $('roam-immersive'), focusReturn: $('roam-options'), exit: $('roam-immersive-exit'),
  eligible: () => state.view === 'feed' && !$('image-card').hidden && !!state.currentImage,
  changed: active => { publishUiState({ roamImmersive: active }); clearFeedbackNotice(); document.dispatchEvent(new Event('pictide:roam-options-close')); },
});
bindTouchNavigation(document.querySelector('#image-card .image-stage'), {
  navigate: direction => moveImage(direction),
  adjustFeedback: direction => stepFeedback(direction),
  verticalEnabled: () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true,
  enabled: () => state.view === 'feed' && !!state.currentImage && !state.feedbackPending && !document.querySelector('[role=dialog][data-state=open],[role=alertdialog],[data-slot=popover-content][data-state=open]'),
});
const refillRoam = createRefillCoordinator({
  active: () => galleryCursors.ready && roamPageActive && roamSettingsLoaded && !roamSwitch && !anchorPrefetchDeferred && !roamBlocked && (!!state.activeId || !!nextImageWait.current) && (roamSettings.prefetch_count > 0 || !!nextImageWait.current) && state.view === 'feed' && !document.hidden,
  version: () => `${roamVersion}:${nextImageWait.current?.token || 0}`,
  anchor: () => state.activeId || null,
  request: anchor_id => api('/api/roam/ensure', { method: 'POST', body: JSON.stringify({ anchor_id, demand: !!nextImageWait.current }) }),
  result: result => {
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
  const element = $('backend-status');
  element.textContent = pending ? t("检查中") : available ? t("可用") : state.backends.length ? t("不可用") : t("未配置");
  element.dataset.tooltip = pending ? t("正在检查生图 API 连接") : available ? t("至少一个生图 API 已通过连接检查") : state.backends.length ? t("生图 API 未通过连接检查，可在设置中测试连接") : t("在设置中添加生图 API");
  element.classList.toggle('connected', available);
  element.dataset.availability = pending ? 'pending' : available ? 'available' : 'unavailable';
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
const backendSettings = createBackendSettings({ state, api, checkBackendAvailability, showBackendAvailability,
  updateGenerationHints: () => generation.updateGenerationHints(), renderRoamBackends, renderArtifacts, loadRoamSettings });
const { renderBackends, loadBackend, loadWorkflowLibrary } = backendSettings;
const generation = createGenerationController({ state, api, getRoamSettings: () => roamSettings, renderJobs, refresh });
const { updateGenerationHints, updateRuleControls, loadRuleConfigs } = generation;

const seedLabel = imageSeedLabel;
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
  document.dispatchEvent(new Event('pictide:close-image-info'));
  if (view === 'settings' && ['general', 'backend', 'roam', 'history'].includes(section)) state.settingsSection = section;
  const editor = view === 'prompts';
  document.querySelectorAll('[data-view]').forEach((button) => {
    const selected = button.dataset.view === view;
    button.classList.toggle('active', selected);
    if (selected) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('view-title').textContent = t(viewTitles[view]);
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
  if (view === 'settings') setSettingsSection(state.settingsSection, false);
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#${view}${view === 'settings' ? `/${state.settingsSection}` : ''}`);
  // Keep controllers and their inputs mounted: navigation never discards drafts.
  if (!editor) { renderArtifacts(); renderJobs(); if (galleryCursors.ready) refresh(true); }
  if (enteringLiked && state.likedSort === 'score') likedRanking.load(state.likedTags);
  refillRoam();
  pageScroll.restore(view);
}
function setSettingsSection(section, updateUrl = true) {
  if (!['general', 'backend', 'roam', 'history'].includes(section)) section = 'general';
  state.settingsSection = section;
  if (state.view === 'settings') publishUiState({ route: `settings/${section}` });
  document.querySelectorAll('[data-settings-section]').forEach((button) => {
    const active = button.dataset.settingsSection === section;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  for (const name of ['general', 'backend', 'roam', 'history']) $(`settings-${name}`).hidden = name !== section;
  if (section === 'roam' && !roamSettingsLoading && !roamSettingsLoaded) loadRoamSettings();
  if (section === 'history') {
    if (!historyLoaded && !historyLoading) loadHistorySettings();
    jobPager.load();
  }
  if (updateUrl) history.replaceState(null, '', `${location.pathname}${location.search}#settings/${section}`);
}
function renderGalleryLoading() {
  publishUiState({ imageReady: false, imageLoading: false });
  syncRoamPlayback();
  $('roam-immersive').disabled = true;
  immersive.leave();
  $('empty-state').hidden = false; $('image-card').hidden = true;
  $('empty-title').hidden = true; $('empty-description').textContent = t("正在读取图片…");
  $('empty-settings').hidden = true; $('empty-generate').hidden = true; $('load-more').hidden = true;
  $('roam-loading').hidden = state.view !== 'feed';
  $('roam-loading-label').textContent = t("正在读取漫游图片");
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
  publishUiState({ waiting });
  $('load-more').hidden = roam || !page.hasMore;
  $('load-more').disabled = state.loadingMore || state.feedbackPending;
  $('load-more').textContent = state.loadingMore ? t("加载中…") : t("更早图片");
  $('load-more').dataset.tooltip = tr`已加载 ${items.length} / ${page.total} 张图片`;
  if (selection.id !== state.activeId) state.activeId = selection.id;
  const index = Math.max(0, items.findIndex((item) => item.id === state.activeId));
  const artifact = items[index];
  $('empty-state').hidden = !!artifact; $('image-card').hidden = !artifact;
  $('empty-title').hidden = false;
  $('empty-description').textContent = state.view === 'liked' ? t("喜欢的图片会保存在这里。") : waiting ? t("正在准备漫游图片…") : state.backends.length ? t("开始漫游，发现下一张图片。") : t("连接生图 API，开始生成。");
  $('empty-settings').hidden = state.view === 'liked' || state.backends.length > 0;
  $('empty-generate').hidden = !roam || !state.backends.length || waiting;
  $('empty-generate').textContent = t("开始漫游");
  $('empty-settings').textContent = t("配置生图 API");
  $('roam-loading').hidden = !waiting;
  $('roam-loading-label').textContent = artifact ? t("正在加载下一张漫游图片") : t("正在生成漫游图片");
  $('image-card').setAttribute('aria-busy', String(waiting));
  $('roam-immersive').disabled = !roam || !artifact;
  if (!artifact) { cancelImageTransition($('main-image')); roamImageSwitchPending = false; syncRoamPlayback(); immersive.leave(); state.currentImage = null; document.dispatchEvent(new CustomEvent('pictide:image-info', { detail: null })); return; }
  document.dispatchEvent(new CustomEvent('pictide:image-info', { detail: { id: artifact.id, seed: artifact.seed_applied === false ? imageSeedLabel(artifact) : String(artifact.seed ?? '—'), positive: artifact.positive || '', negative: artifact.negative || '' } }));
  if (state.currentImage !== artifact.id) {
    clearFeedbackNotice();
    cancelImageTransition($('main-image'));
    roamImageSwitchPending = state.currentImage !== null;
    state.currentImage = artifact.id; $('image-error').hidden = true; dismissNotification('roam-image-error');
    const imageUrl = `/api/artifacts/${encodeURIComponent(artifact.id)}/image`;
    $('main-image').src = imageUrl;
    $('image-date').textContent = dateLabel(artifact.created_at);
  }
  $('image-index').textContent = `${index + 1} / ${page.total || items.length}`;
  $('like').setAttribute('aria-pressed', String(artifact.feedback === 1));
  describeAction($('like'), artifact.feedback === 1 ? t("已喜欢，点击撤回") : t("喜欢 · ↑"));
  $('dislike').setAttribute('aria-pressed', String(artifact.feedback === -1));
  describeAction($('dislike'), artifact.feedback === -1 ? t("已不喜欢，点击撤回") : t("不喜欢 · ↓"));
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
let feedbackMotion = null, feedbackMotionTimer;
function clearFeedbackNotice() {
  clearTimeout(feedbackMotionTimer);
  feedbackMotion?.cancel(); feedbackMotion = null;
  $('immersive-feedback').hidden = true;
}
function showFeedbackNotice(value, previous) {
  clearFeedbackNotice();
  const overlay = $('immersive-feedback');
  overlay.dataset.value = value === null ? 'clear' : String(value);
  $('immersive-feedback-label').textContent = value === 1 ? t("已喜欢") : value === -1 ? t("已不喜欢")
    : previous === 1 ? t("已取消喜欢") : t("已取消不喜欢");
  overlay.hidden = false;
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    feedbackMotion = overlay.firstElementChild.animate([
      { opacity: 0, transform: 'translateY(12px) scale(.86)', offset: 0 },
      { opacity: 1, transform: 'translateY(0) scale(1.06)', offset: .18 },
      { opacity: 1, transform: 'translateY(0) scale(1)', offset: .3 },
      { opacity: 1, transform: 'translateY(0) scale(1)', offset: .7 },
      { opacity: 0, transform: 'translateY(-8px) scale(.98)', offset: 1 },
    ], { duration: 900, easing: 'ease-out', fill: 'both' });
  }
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
function createJobCard(job) {
  const card = document.createElement('details'); card.className = 'job'; card.dataset.jobId = job.id;
  card.open = expandedJobs.has(job.id);
  card.addEventListener('toggle', () => { if (card.open) expandedJobs.add(job.id); else expandedJobs.delete(job.id); });
  const summary = document.createElement('summary');
  const label = t(statusNames[job.status] || job.status);
  summary.setAttribute('aria-label', tr`${label} · ${job.id} · ${dateLabel(job.created_at)} · 任务详情`);
  summary.dataset.tooltip = t("展开或收起任务详情");
  const iconName = { queued: 'Clock', submitting: 'LoaderCircle', running: 'LoaderCircle', completed: 'CircleCheck', failed: 'CircleX', cancelled: 'CircleSlash' }[job.status] || 'CircleHelp';
  const status = document.createElement('span'); status.className = `job-status job-status-${job.status}`; status.dataset.tooltip = label;
  status.setAttribute('role', 'img'); status.setAttribute('aria-label', label); status.append(createIcon(iconName));
  const clock = document.createElement('span'); clock.className = 'job-time'; clock.dataset.tooltip = new Date(job.created_at).toLocaleString(locale());
  clock.setAttribute('role', 'img'); clock.setAttribute('aria-label', clock.dataset.tooltip); clock.append(createIcon('Clock'));
  const identifier = document.createElement('span'); identifier.className = 'job-identifier'; identifier.textContent = job.id;
  identifier.dataset.tooltip = tr`任务 ID：${job.id}`;
  summary.append(status, identifier, clock);
  const body = document.createElement('div'); body.className = 'job-body';
  const meta = document.createElement('dl'); meta.className = 'job-meta';
  for (const [name, value] of [[t("状态"), label], [t("时间"), new Date(job.created_at).toLocaleString(locale())], [t("生图 API"), job.backend_name || job.backend_id], [t("种子"), seedLabel(job)], [t("任务 ID"), job.id]]) {
    const term = document.createElement('dt'), detail = document.createElement('dd'); term.textContent = name; detail.textContent = value; meta.append(term, detail);
  }
  body.append(meta);
  for (const [name, value] of [[t("正向提示词"), job.positive], [t("负向提示词"), job.negative]]) {
    if (!value) continue;
    const heading = document.createElement('h3'); heading.textContent = name;
    const prompt = document.createElement('p'); prompt.className = 'job-prompt'; prompt.textContent = value; body.append(heading, prompt);
  }
  if (job.error) { const error = document.createElement('p'); error.className = 'job-error'; error.textContent = job.error; body.append(error); }
  if (activeStatuses.has(job.status)) { const actions = document.createElement('div'); actions.className = 'job-actions'; const cancel = document.createElement('button'); cancel.textContent = t("取消任务"); decorateElement(cancel, 'button', {}); cancel.addEventListener('click', () => cancelJob(job.id, cancel)); actions.append(cancel); body.append(actions); }
  card.append(summary, body);
  return card;
}
function renderJobs() {
  renderGeneratedResults();
}
function renderJobPage(page) {
  const signature = JSON.stringify([locale(), page.page, page.items]);
  if (signature !== jobsSignature) { jobsSignature = signature; $('job-list').replaceChildren(...page.items.map(createJobCard)); }
  $('job-list').inert = page.loading;
  $('job-list').setAttribute('aria-busy', String(page.loading));
  $('jobs-empty').hidden = !page.loaded || page.total > 0 || page.loading || !!page.error;
  document.dispatchEvent(new CustomEvent('pictide:jobs-pagination', { detail: {
    page: page.page, totalPages: page.totalPages, loading: page.loading,
    visible: page.loading || !!page.error || page.total > 0,
  } }));
  inlineStatus('jobs-page-message', page.loading ? t("正在读取任务…") : '', page.loading);
  if (page.error) notifyError(page.error, { id: 'jobs-page-error', action: { label: () => t('重试'), onClick: () => jobPager.load() } });
  else dismissNotification('jobs-page-error');
}
document.addEventListener('pictide:jobs-page', event => {
  if (!jobPager.state.loading) jobPager.load(event.detail.page);
});
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
    sort: state.likedSort, tags: state.likedTags, refreshedAt: likedRanking.snapshot().refreshedAt, filterVersion: likedFilterVersion, revision: state.feedbackRevision + state.artifactRevision,
    hasMore: state.pages.liked.hasMore, loading: state.likedSort === 'score' ? likedRanking.snapshot().loading : !state.pages.liked.loaded && !state.likedError || state.loadingMore,
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
async function cancelJob(id, button) {
  button.disabled = true;
  try { const result = await api(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }); state.jobs = state.jobs.map((job) => job.id === id ? result.job : job); renderJobs(); if (viewingHistory()) await jobPager.load(); }
  catch (error) { showNotice(error.message, true); button.disabled = false; }
}
async function refresh(force = false) {
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
  if (!backendSettings.initialized) loadBackend($('edit-backend').value);
  setView('settings/backend');
}
function renderRoamBackends() {
  const selected = $('roam-backend').value;
  $('roam-backend').replaceChildren(translatedOption('', "自动选择 API"), ...state.backends.map(item => option(item.id, item.name)));
  if (selected && !state.backends.some(item => item.id === selected)) $('roam-backend').append(translatedOption(selected, "已移除的生图 API，请重新选择"));
  $('roam-backend').value = selected;
  updateRoamBackendNote();
}
function updateRoamBackendNote() {
  const selected = $('roam-backend').value;
  const backend = selected ? state.backends.find(item => item.id === selected) : state.backends[0];
  $('roam-cloud-note').hidden = !backendCapabilities(backend).cloud;
}
$('roam-backend').addEventListener('change', updateRoamBackendNote);
const roamFields = {
  recommendation_strength: 'roam-recommendation-strength', strong_candidate_multiplier: 'roam-strong-candidate-multiplier',
  candidate_count: 'roam-candidate-count', prefetch_count: 'roam-prefetch-count', max_history_images: 'roam-max-history-images',
  backend_id: 'roam-backend',
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
  if (transition?.resume && !anchorPrefetchDeferred && transition.view === viewRevision && state.view === 'feed' && !document.hidden && !roamBlocked && !roamPlayback.playing) roamPlayback.toggle();
  refillRoam();
}
async function applyRoamSettings(settings, savedFields = []) {
  const next = { ...settings, recommendation_strength: settings.recommendation_strength ?? 'standard', strong_candidate_multiplier: strongCandidateMultiplier(settings.strong_candidate_multiplier ?? 2), candidate_count: candidateCount(settings.candidate_count ?? 10), prefetch_count: prefetchCount(settings.prefetch_count ?? 2), max_history_images: maxHistoryImages(settings.max_history_images ?? 20), liked_tags_only: !!settings.liked_tags_only, prompt_mode: settings.prompt_mode ?? 'random', playback_interval_seconds: settings.playback_interval_seconds ?? 8 };
  if (!roamSettingsLoaded || next.preset_id !== roamSettings.preset_id) {
    const control = $('rule-config');
    if (next.preset_id && ![...control.options].some(item => item.value === next.preset_id)) control.append(option(next.preset_id, next.preset_id));
    control.value = next.preset_id || control.options[0]?.value || '';
  }
  const switched = roamSettingsLoaded && roamGenerationChanged(roamSettings, next);
  if (roamSettingsLoaded && JSON.stringify(roamSettings.pinned_positive ?? []) !== JSON.stringify(next.pinned_positive ?? [])) {
    // Saving anchors still discards the old window, but editing must not launch
    // replacements through settings/SSE/page refresh events. Next navigation resumes it.
    anchorPrefetchDeferred = true;
  }
  if (switched) beginRoamSwitch();
  const draft = Object.fromEntries(Object.entries(roamFields).map(([key, id]) => [key, key === 'liked_tags_only' ? $(id).checked : $(id).value]));
  const merged = mergeRoamDraft(roamSettings, next, draft, savedFields);
  const backendControl = $('roam-backend');
  if (merged.backend_id && ![...backendControl.options].some(item => item.value === merged.backend_id)) backendControl.append(option(merged.backend_id, merged.backend_id));
  for (const [key, id] of Object.entries(roamFields)) {
    if (key === 'liked_tags_only') $(id).checked = merged[key];
    else $(id).value = String(merged[key] ?? '');
  }
  document.dispatchEvent(new CustomEvent('pictide:roam-settings-draft', { detail: merged }));
  roamSettings = next; roamSettingsLoaded = true; roamVersion++;
  updateRoamBackendNote();
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
    if (Object.hasOwn(patch, 'preset_id')) $('rule-config').value = result.preset_id || $('rule-config').options[0]?.value || '';
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
    const payload = { recommendation_strength: $('roam-recommendation-strength').value, strong_candidate_multiplier: strongCandidateMultiplier($('roam-strong-candidate-multiplier').value), candidate_count: candidateCount($('roam-candidate-count').value), prefetch_count: prefetchCount($('roam-prefetch-count').value), max_history_images: maxHistoryImages($('roam-max-history-images').value), backend_id: $('roam-backend').value, playback_interval_seconds: playbackInterval($('roam-playback-interval').value), liked_tags_only: $('roam-liked-tags-only').checked, prompt_mode: $('roam-prompt-mode').value };
    await saveRoamSettings(payload);
    notifySuccess(() => t("已保存漫游设置。"), { id: 'roam-settings' });
    await refresh(true);
  } catch (error) { notifyError(error.message, { id: 'roam-settings' }); }
  finally { $('roam-save').disabled = false; $('roam-fields').disabled = false; }
});
async function bootstrap() {
  try {
    const data = await api('/api/bootstrap'); state.backends = data.backends || []; state.jobs = data.jobs || []; state.artifacts = data.artifacts || []; state.artifactRevision = data.artifact_revision ?? 0; state.dataDirectory = data.data_directory || '';
    galleryCursors.restore(data.roam_view || {});
    if (data.artifact_page?.anchor_id !== undefined && galleryCursors.get('feed') && !state.artifacts.some(item => item.id === galleryCursors.get('feed'))) selectImage(data.artifact_page.anchor_id, 'feed');
    state.pages.feed.loaded = true; state.pages.feed.total = data.counts?.roam ?? state.artifacts.length; state.pages.feed.hasMore = data.artifact_page?.has_more ?? state.pages.feed.total > state.artifacts.length; state.pages.feed.hasNewer = !!data.artifact_page?.has_newer; state.pages.feed.cursor = data.artifact_page?.next_cursor ?? state.artifacts.at(-1)?.id ?? null; state.pages.liked.total = data.counts?.liked ?? 0; state.pages.generate.total = data.counts?.generate ?? 0;
    if (data.backend_types?.length) $('backend-kind').replaceChildren(...data.backend_types.map((type) => option(type.kind, type.label)));
    renderBackends(); renderJobs(); renderArtifacts();
    if (data.roam_settings) await applyRoamSettings(data.roam_settings, Object.keys(roamFields));
    if (viewingHistory()) jobPager.load();
    $('data-directory').textContent = state.dataDirectory || t("服务尚未返回数据目录");
    await loadWorkflowLibrary();
    loadBackend($('edit-backend').value);
    if (!roamSettingsLoaded) await loadRoamSettings();
    publishUiState({ ready: true });
  } catch (error) { showNotice(tr`无法读取平台数据：${error.message}`, true); }
}

$('empty-settings').addEventListener('click', () => { if (state.view === 'feed' && state.backends.length) setView('settings/roam'); else openSettings(); });
$('empty-generate').addEventListener('click', requestNextRoamImage);
async function loadHistorySettings() {
  historyLoading = true;
  $('history-fields').disabled = true; $('history-save').disabled = true; $('history-save').textContent = t("保存设置");
  historyNotice(() => t("正在读取清理设置…"), false, 'info');
  try {
    const result = await api('/api/settings/history');
    $('history-retention-days').value = String(retentionDays(result.unliked_retention_days));
    if (observeArtifactRevision(state, result.artifact_revision)) { renderArtifacts(); await refresh(true); }
    historyLoaded = true; historyNotice('');
  } catch (error) {
    try { retentionDays($('history-retention-days').value); } catch { $('history-retention-days').value = '1'; }
    $('history-save').textContent = t("重新保存");
    historyNotice(() => tr`读取失败：${error.message}。配置损坏时过期清理会暂停；可修改天数并重新保存以修复设置。`, true);
  } finally { historyLoading = false; $('history-fields').disabled = false; $('history-save').disabled = false; }
}
$('history-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if ($('history-save').disabled) return;
  try {
    const days = retentionDays($('history-retention-days').value);
    $('history-save').disabled = true; $('history-fields').disabled = true;
    const result = await api('/api/settings/history', { method: 'PUT', body: JSON.stringify({ unliked_retention_days: days }) });
    $('history-retention-days').value = String(retentionDays(result.unliked_retention_days));
    $('history-save').textContent = t("保存设置"); historyLoaded = true;
    if (observeArtifactRevision(state, result.artifact_revision)) renderArtifacts();
    historyNotice(() => days ? tr`已保存：未标记喜欢的图片保留 ${days} 天。` : t("已关闭自动清理。"));
    await refresh(true);
  } catch (error) { historyNotice(error.message, true); }
  finally { $('history-save').disabled = false; $('history-fields').disabled = false; }
});
window.addEventListener('beforeunload', (event) => { if (generation.dirty || backendSettings.dirty || roamDraftDirty()) { event.preventDefault(); event.returnValue = ''; } });
$('like').addEventListener('click', () => feedback(1));
$('dislike').addEventListener('click', () => feedback(-1));
$('previous').addEventListener('click', () => moveImage('older')); $('next').addEventListener('click', () => moveImage('newer'));
$('load-more').addEventListener('click', loadMore);
document.addEventListener('pictide:generated-more', loadMore);
document.addEventListener('pictide:generated-refresh', () => { state.generatedMutationError = ''; refresh(true); });
document.addEventListener('pictide:generated-configure', openSettings);
document.addEventListener('pictide:generated-feedback', event => feedbackGenerated(event.detail.id, event.detail.toggle !== false));
document.addEventListener('pictide:generated-clear', clearGenerated);
document.addEventListener('pictide:liked-filter', event => {
  if (state.feedbackPending || state.generatedMutationPending) return;
  const tags = [...new Set(event.detail.tags)];
  if (JSON.stringify(tags) === JSON.stringify(state.likedTags)) return;
  state.likedTags = tags; likedFilterVersion++;
  state.likedArtifacts = []; state.likedError = '';
  state.pages.liked = { hasMore: false, cursor: null, total: 0, loadedMore: false, loaded: false };
  $('liked-view').scrollTop = 0;
  if (state.likedSort === 'score') { likedRanking.clear(); likedRanking.load(state.likedTags); }
  else { renderLikedResults(); refresh(true); }
});

document.addEventListener('pictide:liked-sort', event => {
  const sort = event.detail.sort;
  if (!['latest', 'score'].includes(sort) || state.likedSort === sort || state.feedbackPending) return;
  likedRanking.cancel(); state.likedSort = sort; likedFilterVersion++;
  state.likedArtifacts = []; state.likedError = '';
  state.pages.liked = { hasMore: false, cursor: null, total: 0, loadedMore: false, loaded: false };
  $('liked-view').scrollTop = 0;
  if (sort === 'score') { likedRanking.clear(); likedRanking.load(state.likedTags); }
  else { renderLikedResults(); refresh(true); }
});

document.addEventListener('pictide:liked-more', () => { if (state.view === 'liked') loadMore(); });
document.addEventListener('pictide:liked-refresh', () => {
  if (state.likedSort === 'score') likedRanking.load(state.likedTags, true);
  else { state.likedError = ''; refresh(true); }
});
document.addEventListener('pictide:liked-feedback', event => feedbackGenerated(event.detail.id, event.detail.toggle !== false, 'liked'));
$('main-image').addEventListener('load', () => {
  if (roamImageSwitchPending) { roamImageSwitchPending = false; playImageTransition($('main-image')); }
  syncRoamPlayback(state.artifacts.find(item => item.id === state.activeId));
});
$('main-image').addEventListener('error', () => { if ($('image-error').hidden) notifyError(() => t('图片读取失败，请检查服务与文件是否可用。'), { id: 'roam-image-error' }); publishUiState({ imageReady: false, imageLoading: false }); roamImageSwitchPending = false; cancelImageTransition($('main-image')); $('image-error').hidden = false; roamPlayback.pause(); });
document.addEventListener('pictide:roam-playback-toggle', () => roamPlayback.toggle());
document.addEventListener('pictide:roam-playback-interval', event => {
  roamSettings.playback_interval_seconds = event.detail;
  roamPlayback.setInterval(event.detail);
});
document.querySelectorAll('[data-settings-section]').forEach((button) => button.addEventListener('click', () => setSettingsSection(button.dataset.settingsSection)));
document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
document.addEventListener('keydown', (event) => {
  const action = keyboardAction(event, { editing: !!event.target.closest('input,textarea,select,[data-help],[role=combobox],[role=listbox],[role=option],[role=checkbox],[role=radio],[role=tab],[role=dialog],[data-slot=select-content],[data-slot=popover-content],[contenteditable]:not([contenteditable="false"])'), dialogOpen: !!document.querySelector('dialog[open],[role=dialog][data-state=open],[role=alertdialog]'), view: state.view, immersive: immersive.active, feedbackPending: state.feedbackPending });
  if (!action) return;
  event.preventDefault();
  if (action === 'increase') stepFeedback(1);
  else if (action === 'decrease') stepFeedback(-1);
  else if (action === 'privacy') {
    const control = ['generate', 'liked'].includes(state.view) ? document.querySelector(`.generated-privacy-toggle[data-collection="${state.view}"]`) : $(immersive.active ? 'roam-immersive-privacy' : 'roam-privacy');
    control?.click();
  }
  else moveImage(action);
});
window.addEventListener('hashchange', () => setView(location.hash.slice(1) || 'feed', false));
setView(location.hash.slice(1) || 'feed', false);
subscribeUiActions((name, value) => { if (name === 'navigate') setView(value); });
document.addEventListener('visibilitychange', () => { if (document.hidden) roamPlayback.pause(); else { loadRoamSettings({ preserveDraft: true }); refresh(true); } });
await bootstrap();
updateRuleControls();
let realtimeConnected = false;
let eventSource;
function syncTheme() {
  return loadTheme().catch(error => document.dispatchEvent(new CustomEvent('pictide:theme-error', { detail: tr`主题读取失败：${error.message}` })));
}
function connectEvents() {
  if (!window.EventSource || eventSource) return;
  eventSource = new EventSource('/api/events');
  eventSource.addEventListener('open', () => { realtimeConnected = true; syncTheme(); loadRoamSettings({ preserveDraft: true }); refresh(true); });
  // Queue another refresh if a change arrives while the current read is in flight.
  eventSource.addEventListener('change', event => {
    try {
      const topic = JSON.parse(event.data).topic;
      if (topic === 'roam_settings' || topic === 'candidate') loadRoamSettings({ preserveDraft: true });
      if (topic === 'candidate') document.dispatchEvent(new Event('pictide:candidate-library-changed'));
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
connectEvents();
window.addEventListener('pagehide', () => {
  roamPlayback.pause(); roamPageActive = false; viewRevision++; nextImageWait.cancel(); roamWindowLoading = false;
  eventSource?.close(); eventSource = undefined; realtimeConnected = false;
});
window.addEventListener('pageshow', (event) => { roamPageActive = true; if (event.persisted) { renderArtifacts(); connectEvents(); refillRoam(); } });
// Existing polling remains the fallback while SSE is unsupported or reconnecting.
setInterval(() => { if (!realtimeConnected) refresh(); }, 2000);

// Preset changes refresh selectors without resetting generator counters or manual drafts.
document.addEventListener('pictide:candidate-presets-changed', () => { loadRuleConfigs(); });


document.addEventListener('pictide:language-changed', () => queueMicrotask(() => {
  $('view-title').textContent = t(viewTitles[state.view]);
  const availability = $('backend-status').dataset.availability;
  showBackendAvailability(availability === 'available', availability === 'pending');
  for (const item of document.querySelectorAll('option[data-i18n-key]')) item.textContent = t(item.dataset.i18nKey);
  updateGenerationHints();
  $('data-directory').textContent = state.dataDirectory || t('服务尚未返回数据目录');
  for (const [id, message] of localizedMessages) if ($(id)) $(id).textContent = message();
  jobsSignature = '';
  renderJobPage(jobPager.state);
  renderArtifacts();
  renderGeneratedResults();
  renderLikedResults();
}));
