export function jobPageNumber(value, totalPages) {
  const text = String(value).trim();
  const page = /^\d+$/.test(text) ? Number(text) : NaN;
  if (!Number.isSafeInteger(page) || page < 1 || page > totalPages) throw new Error(`页码须为 1 至 ${totalPages} 的整数。`);
  return page;
}

/** Latest navigation wins; refreshes coalesce without losing an in-flight update. */
export function createJobPager({ request, changed, active = () => true }) {
  const state = { items: [], page: 1, total: 0, totalPages: 1, loaded: false, loading: false, error: '' };
  let requestedPage = 1, revision = 0, current = null, queued = false;
  function load(page = requestedPage) {
    if (current && page === requestedPage) { queued = true; return current; }
    requestedPage = page;
    const token = ++revision;
    queued = false; state.loading = true; state.error = ''; changed(state);
    current = (async () => {
      try {
        const result = await request(page);
        if (token !== revision) return;
        state.items = result.jobs; state.page = result.page; requestedPage = result.page;
        state.total = result.total; state.totalPages = result.total_pages; state.loaded = true;
      } catch (error) {
        if (token !== revision) return;
        requestedPage = state.page; state.error = `任务加载失败：${error.message}`;
      } finally {
        if (token === revision) {
          const repeat = queued && active();
          current = null; queued = false; state.loading = false; changed(state);
          if (repeat) await load();
        }
      }
    })();
    return current;
  }
  return { state, load };
}
