import { createModel } from '../shared/model.mjs';
import { createRequestId } from '../shared/request-id.mjs';
import { notifySuccess, notifyError } from '../shared/notifications.mjs';
import { confirmAction } from '../components/confirm-action';
import { t } from '../i18n/index.mjs';

const row = (size = { width: 1024, height: 1024 }) => ({ key: createRequestId(), width: String(size.width), height: String(size.height) });
const empty = () => ({ id: '__new__', name: '', sizes: [row()] });
export function createCanvasPools(api) {
  const model = createModel({ pools: [], draft: empty(), loaded: false, busy: false, dirty: false });
  const state = model.data;
  let disposed = false, revision = 0;
  function select(id) {
    const pool = state.pools.find(item => item.id === id);
    state.draft = pool ? { ...pool, sizes: pool.sizes.map(row) } : empty();
    state.dirty = false; model.changed();
  }
  async function load(force = false) {
    if (state.loaded && !force) return;
    const current = ++revision;
    try {
      const pools = await api('/api/canvas-pools');
      if (disposed || current !== revision) return;
      state.pools = pools;
      if (!state.loaded) { if (!state.dirty) select(pools[0]?.id || '__new__'); }
      else if (!state.dirty && !state.busy) select(state.draft.id);
      state.loaded = true; model.changed();
    } catch (error) { if (!disposed) notifyError(error.message); }
  }
  async function run(action) {
    if (state.busy) return;
    state.busy = true; revision++; model.changed();
    try { await action(); } catch (error) { notifyError(t(error.message)); }
    finally { state.busy = false; model.changed(); }
  }
  return {
    model, load,
    edit(key, value) { state.draft[key] = value; state.dirty = true; model.changed(); },
    editSize(key, field, value) {
      const size = state.draft.sizes.find(item => item.key === key);
      if (size) { size[field] = value; state.dirty = true; model.changed(); }
    },
    addSize() { if (state.draft.sizes.length < 64) { state.draft.sizes.push(row()); state.dirty = true; model.changed(); } },
    removeSize(key) { if (state.draft.sizes.length > 1) { state.draft.sizes = state.draft.sizes.filter(item => item.key !== key); state.dirty = true; model.changed(); } },
    async select(id) {
      if (state.busy || state.dirty && !await confirmAction(t('放弃未保存的画幅池修改？'))) return;
      select(id);
    },
    save: () => run(async () => {
      const id = state.draft.id === '__new__' ? createRequestId() : state.draft.id;
      const sizes = state.draft.sizes.map(({width, height}) => ({width: Number(width), height: Number(height)}));
      state.pools = await api('/api/canvas-pools/' + encodeURIComponent(id), {
        method: 'PUT', body: JSON.stringify({name: state.draft.name, sizes}),
      });
      state.loaded = true; select(id); notifySuccess(() => t('画幅池已保存。'));
    }),
    remove: () => run(async () => {
      if (state.draft.id === '__new__' || !await confirmAction(t('删除此画幅池？'))) return;
      state.pools = await api('/api/canvas-pools/' + encodeURIComponent(state.draft.id), {method: 'DELETE', body: '{}'});
      select(state.pools[0]?.id || '__new__'); notifySuccess(() => t('画幅池已删除。'));
    }),
    dispose() { disposed = true; revision++; },
  };
}
