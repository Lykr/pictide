import { mergeArtifacts } from './feed-controls.mjs';

export function retentionDays(raw) {
  const value = Number(raw);
  if (!['string', 'number'].includes(typeof raw) || typeof raw === 'string' && !raw.trim() || !Number.isSafeInteger(value) || value < 0 || value > 3650) {
    throw new Error('保留天数须为 0–3650 之间的整数，0 表示关闭自动清理。');
  }
  return value;
}

function emptyPage() { return { hasMore: false, cursor: null, total: 0, loadedMore: false, loaded: false }; }

/** A deletion invalidates every image list, including previously loaded pages. */
export function observeArtifactRevision(store, revision) {
  if (!Number.isSafeInteger(revision) || revision <= store.artifactRevision) return false;
  store.artifactRevision = revision;
  store.artifacts = []; store.likedArtifacts = [];
  store.pages = { feed: emptyPage(), liked: emptyPage() };
  if ('generatedArtifacts' in store) { store.generatedArtifacts = []; store.pages.generate = emptyPage(); }
  store.currentImage = null;
  return true;
}

export function applyArtifactPage(store, view, result, { append = false, replace = false, requestRevision = store.artifactRevision } = {}) {
  const revision = Number.isSafeInteger(result.revision) ? result.revision : store.artifactRevision;
  if (revision < store.artifactRevision) return { accepted: false, reset: false, refresh: false };
  const reset = observeArtifactRevision(store, revision);
  // A cursor belongs to its original snapshot. A tail page cannot replace the
  // current first page when a cleanup occurred while the request was in flight.
  if (append && requestRevision !== revision) return { accepted: false, reset, refresh: true };
  const key = view === 'liked' ? 'likedArtifacts' : view === 'generate' ? 'generatedArtifacts' : 'artifacts';
  const page = store.pages[view];
  page.loaded = true;
  store[key] = replace ? [...result.artifacts] : mergeArtifacts(store[key], result.artifacts, append);
  if (replace) page.loadedMore = false;
  page.total = result.total ?? store[key].length;
  if (append || !page.loadedMore) {
    page.cursor = result.next_cursor ?? result.artifacts.at(-1)?.id ?? null;
    page.hasMore = !!result.has_more;
  }
  if (append) page.loadedMore = true;
  page.hasNewer = !!result.has_newer;
  if (store[key].length >= page.total) page.hasMore = false;
  if (result.counts) {
    if (Number.isSafeInteger(result.counts.roam)) store.pages.feed.total = result.counts.roam;
    else if (Number.isSafeInteger(result.counts.artifacts)) store.pages.feed.total = result.counts.artifacts;
    if (Number.isSafeInteger(result.counts.liked)) store.pages.liked.total = result.counts.liked;
    if (store.pages.generate && Number.isSafeInteger(result.counts.generate)) store.pages.generate.total = result.counts.generate;
  }
  return { accepted: true, reset, refresh: false };
}
