/** Each gallery owns its cursor; liking/browsing another view never moves roam. */
export function createGalleryCursors() {
  const cursors = { feed: null, liked: null };
  let initialized = false, clock = 0;
  return {
    get ready() { return initialized; },
    get: view => cursors[view === 'liked' ? 'liked' : 'feed'],
    restore(record = {}) {
      if (initialized) return;
      cursors.feed = record.artifact_id || null;
      clock = Number.isSafeInteger(record.viewed_at) ? record.viewed_at : 0;
      initialized = true;
    },
    select(view, id, now = Date.now()) {
      const key = view === 'liked' ? 'liked' : 'feed';
      if (!initialized || cursors[key] === id) return null;
      cursors[key] = id || null;
      if (key !== 'feed') return null;
      clock = Math.max(clock + 1, now);
      return { artifact_id: cursors.feed, viewed_at: clock };
    },
  };
}

/** One user intent may span queue events, but can advance the gallery only once. */
export function createNextImageWait() {
  let waiting = null, serial = 0;
  return {
    get current() { return waiting; },
    begin(anchor) {
      if (waiting) return null;
      waiting = { anchor: anchor || null, token: ++serial };
      return waiting;
    },
    cancel() { waiting = null; serial++; },
    consume(items, active, visible) {
      if (!waiting || !visible || active !== waiting.anchor) return null;
      const index = items.findIndex(item => item.id === waiting.anchor);
      const next = waiting.anchor === null ? items.at(-1) : index > 0 ? items[index - 1] : null;
      if (!next) return null;
      waiting = null;
      return next.id;
    },
  };
}

export function roamArtifactPath(anchor = null) {
  const query = new URLSearchParams({ limit: '200', source: 'roam' });
  if (anchor) query.set('around', anchor);
  return `/api/artifacts?${query}`;
}

export function roamBoundaryAction(direction, page) {
  if (direction === 'older') return page.hasMore ? 'load' : 'idle';
  return page.hasNewer ? 'load' : 'generate';
}

/** An invalidated cache is not evidence that the viewed image was deleted. */
export function resolveGalleryCursor(items, cursor, loaded) {
  if (!loaded) return { loading: true, id: cursor };
  return { loading: false, id: items.some(item => item.id === cursor) ? cursor : items[0]?.id || null };
}
