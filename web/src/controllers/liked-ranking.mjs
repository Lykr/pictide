/** A browsing snapshot: ranking is refreshed only by explicit page actions. */
export function createLikedRanking({ request, changed, pageSize = 15 }) {
  let items = [], visible = pageSize, error = '', loading = false;
  let version = 0, controller;
  const snapshot = () => ({ artifacts: items.slice(0, visible), total: items.length,
    hasMore: items.length > visible, loading, error });
  const publish = () => changed(snapshot());
  function cancel() { version++; controller?.abort(); controller = undefined; loading = false; }
  return {
    snapshot,
    cancel,
    clear() { cancel(); items = []; visible = pageSize; error = ''; publish(); },
    more() { if (!loading) { visible += pageSize; publish(); } },
    update(artifact) {
      // Other pages and devices are incorporated at the next explicit refresh.
      if (artifact.feedback !== 1) items = items.filter(item => item.id !== artifact.id);
      else items = items.map(item => item.id === artifact.id ? artifact : item);
      publish();
    },
    async load(tags = []) {
      cancel(); const current = version; controller = new AbortController();
      const signal = controller.signal;
      loading = true; error = ''; publish();
      const query = new URLSearchParams();
      for (const tag of new Set(tags)) query.append('tag', tag);
      try {
        const result = await request(`/api/liked/ranked${query.size ? `?${query}` : ''}`, { signal });
        if (current !== version || signal.aborted) return;
        items = result.artifacts; visible = pageSize;
        error = result.error || (result.scoring_available === false ? '暂无法按偏好评分排序，已按时间展示。' : '');
      } catch (failure) {
        if (current !== version || signal.aborted) return;
        error = failure.message;
      } finally {
        if (current === version && !signal.aborted) { loading = false; controller = undefined; publish(); }
      }
    },
  };
}
