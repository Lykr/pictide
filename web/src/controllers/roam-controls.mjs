import { t, tr, locale } from '../i18n/index.mjs';
export function prefetchCount(value) {
  if (!['number', 'string'].includes(typeof value)) throw new Error(t("请输入有效的预取数量。"));
  if (typeof value === 'string' && !value.trim()) throw new Error(t("请输入预取数量。"));
  const count = Number(value);
  if (!Number.isInteger(count) || count < 0 || count > 20) throw new Error(t("预取数量须为 0–20 之间的整数。"));
  return count;
}

export function candidateCount(value) {
  if (!['number', 'string'].includes(typeof value) || typeof value === 'string' && !value.trim()) throw new Error(t("请输入候选组合数量。"));
  const count = Number(value);
  if (!Number.isInteger(count) || count < 1 || count > 20) throw new Error(t("候选组合数量须为 1–20 之间的整数。"));
  return count;
}

export function strongCandidateMultiplier(value) {
  if (!['number', 'string'].includes(typeof value) || typeof value === 'string' && !value.trim()) throw new Error(t("请输入强力候选倍数。"));
  const count = Number(value);
  if (!Number.isInteger(count) || count < 1 || count > 5) throw new Error(t("强力候选倍数须为 1–5 之间的整数。"));
  return count;
}

export function maxHistoryImages(value) {
  if (!['number', 'string'].includes(typeof value) || typeof value === 'string' && !value.trim()) {
    throw new Error(t("请输入历史图片数量上限。"));
  }
  const count = Number(value);
  if (!Number.isSafeInteger(count) || count < 0 || count > 100000) {
    throw new Error(t("历史图片数量上限须为 0–100000 之间的整数，0 表示关闭数量清理。"));
  }
  return count;
}

// Browser events may overlap. Keep one request in flight and then use the latest
// cursor; the server separately serializes requests from different tabs.
export function createRefillCoordinator({ active, anchor, request, result, error, version = () => 0 }) {
  let busy = false, again = false;
  const refill = async () => {
    if (!active()) { again = false; return; }
    if (busy) { again = true; return; }
    busy = true;
    const current = anchor();
    const revision = version();
    try {
      const response = await request(current);
      if (active() && current === anchor() && revision === version()) result(response);
    } catch (failure) { if (active() && current === anchor() && revision === version()) error(failure); }
    finally { busy = false; if (again) { again = false; await refill(); } }
  };
  return refill;
}

// Transport failures recover at the next existing page/SSE event, without a timer.
export function isTemporaryRefillError(error) {
  const status = error?.status;
  return !Number.isInteger(status) || status === 0 || status === 408 || status === 429 || status >= 500;
}

// A saved field may change from the roam menu or another tab. Only replace an
// untouched draft, unless this tab explicitly saved that same field.
export function mergeRoamDraft(previous, saved, draft, savedFields = []) {
  return Object.fromEntries(Object.keys(draft).map(key => [key,
    savedFields.includes(key) || String(draft[key]) === String(previous[key]) ? saved[key] : draft[key],
  ]));
}

export function likedTagsWait(result, waitingForNext) {
  return !!result.waiting_for_liked_tags && waitingForNext && !(result.ready > 0);
}

// These fields change future prompts/images and invalidate the prefetched window.
export function roamGenerationChanged(previous, next) {
  return ['liked_tags_only', 'prompt_mode', 'backend_id', 'preset_id', 'use_canvas_pool'].some(key => previous[key] !== next[key])
    || ['pinned_positive', 'preset_base_positive'].some(key => JSON.stringify(previous[key] ?? []) !== JSON.stringify(next[key] ?? []));
}
