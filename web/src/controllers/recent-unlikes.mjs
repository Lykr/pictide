import { createModel } from '../shared/model.mjs';

/** A recovery window independent of the Liked page's filters and sort. */
export function createRecentUnlikes({ request, pageSize = 100, clock = Date.now, schedule = setInterval, unschedule = clearInterval }) {
  const state = { open: false, artifacts: [], total: 0, hasMore: false, loading: false, error: '', now: clock() };
  const model = createModel(state);
  let cursor = null, version = 0, controller, timer, serverTime = clock(), receivedAt = clock(), retryMore = false;
  function cancel() { version++; controller?.abort(); controller = undefined; state.loading = false; }
  function tick() {
    state.now = serverTime + clock() - receivedAt;
    const live = state.artifacts.filter(item => Date.parse(item.unliked_protected_until) > state.now);
    state.total = Math.max(0, state.total - state.artifacts.length + live.length);
    if (live.length !== state.artifacts.length) state.artifacts = live;
    model.changed();
  }
  async function load(append = false) {
    if (!state.open || append && (state.loading || !state.hasMore)) return;
    cancel();
    const current = version;
    controller = new AbortController();
    const signal = controller.signal;
    retryMore = append;
    state.loading = true; state.error = ''; model.changed();
    const query = new URLSearchParams({ limit: String(pageSize) });
    if (append && cursor) query.set('before', cursor);
    try {
      const result = await request(`/api/liked/recently-unliked?${query}`, { signal });
      if (current !== version || signal.aborted) return;
      serverTime = Date.parse(result.server_time); receivedAt = clock(); state.now = serverTime;
      const items = append ? [...state.artifacts, ...result.artifacts] : result.artifacts;
      state.artifacts = [...new Map(items.map(item => [item.id, item])).values()];
      state.total = result.total; state.hasMore = result.has_more; cursor = result.next_cursor;
      tick();
    } catch (error) {
      if (current === version && !signal.aborted) state.error = error.message;
    } finally {
      if (current === version && !signal.aborted) { state.loading = false; controller = undefined; model.changed(); }
    }
  }
  return {
    model,
    setOpen(open) {
      if (state.open === open) return;
      cancel(); unschedule(timer); timer = undefined; state.open = open; state.error = '';
      if (open) {
        state.artifacts = []; state.total = 0; state.hasMore = false; cursor = null;
        timer = schedule(tick, 30000);
        void load();
      }
      model.changed();
    },
    more: () => load(true),
    retry: () => load(retryMore),
    invalidate: () => load(),
    remove(id) {
      cancel();
      const previous = state.artifacts.length;
      state.artifacts = state.artifacts.filter(item => item.id !== id);
      state.total = Math.max(0, state.total - previous + state.artifacts.length);
      model.changed();
    },
    dispose() { cancel(); unschedule(timer); state.open = false; },
  };
}
