import { emitSignal } from '../shared/signals.mjs';
import { createModel } from '../shared/model.mjs';
import { createRequestId } from '../shared/request-id.mjs';
import { notifySuccess, notifyError, notify } from '../shared/notifications.mjs';
import { API_KEY_MASK, apiKeyFields } from './settings-controls.mjs';
import { confirmAction } from '../components/confirm-action';
import { t } from '../i18n/index.mjs';

const empty = () => ({ id: '__new__', name: '', kind: 'openai', base_url: '', model: '', key: '' });
export function createPromptSettings(api) {
  const model = createModel({ draft: empty(), connections: [], models: [], account: null, loaded: false,
    busy: false, dirty: false, hasKey: false, signingIn: false, welcome: false });
  const state = model.data;
  let timer, disposed = false;
  const route = (id = state.draft.id) => '/api/llm-apis/' + encodeURIComponent(id);
  function select(id) {
    const value = state.connections.find(item => item.id === id);
    state.draft = value ? { ...value, key: value.has_api_key ? API_KEY_MASK : '' } : empty();
    state.hasKey = !!value?.has_api_key; state.account = value?.account || null;
    state.dirty = false; state.models = []; model.changed();
  }
  async function load(force = false) {
    if (state.loaded && !force) return;
    const rows = await api('/api/llm-apis');
    if (disposed) return;
    state.connections = rows;
    if (!state.loaded) select(rows[0]?.id || '__new__');
    else state.account = rows.find(row => row.id === state.draft.id)?.account || null;
    state.loaded = true; model.changed();
  }
  async function persist() {
    const { id, name, kind, base_url, model: selectedModel, key } = state.draft;
    const identifier = id === '__new__' ? createRequestId() : id;
    const payload = { name, kind, base_url, model: selectedModel,
      ...(kind === 'openai' ? apiKeyFields(key, state.hasKey) : {}) };
    const catalog = state.models;
    state.connections = await api(route(identifier), { method: 'PUT', body: JSON.stringify(payload) });
    select(identifier);
    if (identifier === id) state.models = catalog;
    emitSignal('prompt-settings-changed');
    return identifier;
  }
  async function run(action) {
    if (state.busy) return;
    state.busy = true; model.changed();
    try { await action(); } catch (error) { notifyError(error.message); }
    finally { state.busy = false; model.changed(); }
  }
  async function models() {
    const id = state.draft.id;
    const result = await api(route(id) + '/models', { method: 'POST', body: '{}' });
    if (id !== state.draft.id || disposed) return;
    state.models = result.models;
    if (!state.draft.model && result.models.length) { state.draft.model = result.models[0].value; state.dirty = true; }
    model.changed();
  }
  async function poll(id) {
    try {
      const result = await api(route(id) + '/status');
      if (disposed || !state.signingIn) return;
      if (['pending', 'exchanging'].includes(result.status)) { timer = setTimeout(() => poll(id), 1000); return; }
      state.signingIn = false;
      if (result.status !== 'connected') throw new Error(result.error || t('登录已取消或过期，请重试。'));
      await load(true);
      if (id !== state.draft.id) return;
      state.welcome = !!state.account?.plan_enabled && !state.account?.welcomed;
      emitSignal('prompt-settings-changed'); model.changed();
      notifySuccess(t('ChatGPT 已连接。'));
      if (state.account?.plan_enabled) await models();
    } catch (error) { state.signingIn = false; notifyError(error.message); }
    finally { model.changed(); }
  }
  return {
    model,
    load: (force = false) => load(force).catch(error => notifyError(error.message)),
    edit(key, value) { state.draft[key] = value; state.dirty = true; model.changed(); },
    async select(id) {
      if (state.busy || state.signingIn) return;
      if (state.dirty && !await confirmAction(t('放弃未保存的 LLM API 修改？'))) return;
      select(id);
    },
    save: () => run(async () => { await persist(); notifySuccess(t('LLM API 已保存。')); }),
    models: () => run(models),
    connect() {
      if (state.busy || state.signingIn) return;
      if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) {
        notifyError(t('请在运行 Pictide 的电脑上，通过本机地址登录 ChatGPT。')); return;
      }
      const popup = window.open('about:blank', '_blank');
      if (!popup) { notifyError(t('请允许弹出登录窗口后重试。')); return; }
      popup.opener = null;
      return run(async () => {
        try {
          const id = await persist();
          const result = await api(route(id) + '/sign-in', { method: 'POST', body: '{}' });
          popup.location.replace(result.authorization_url);
          state.signingIn = true; timer = setTimeout(() => poll(id), 1000);
        } catch (error) { popup.close(); throw error; }
      });
    },
    cancel: () => run(async () => {
      clearTimeout(timer); state.signingIn = false;
      await api(route() + '/cancel', { method: 'POST', body: '{}' });
    }),
    disconnect: () => run(async () => {
      if (!await confirmAction(t('断开此 ChatGPT 连接？使用它的生图 API 将暂停自然语言转换。'))) return;
      const result = await api(route() + '/disconnect', { method: 'POST', body: '{}' });
      await load(true); state.models = []; emitSignal('prompt-settings-changed');
      notify(t(result.revoked ? '已断开连接。' : '已在本机断开；远端撤销未确认，请在 ChatGPT 设置中断开应用。'), { kind: result.revoked ? 'success' : 'warning' });
    }),
    remove: () => run(async () => {
      if (state.draft.id === '__new__' || !await confirmAction(t('删除此 LLM API 配置？'))) return;
      const result = await api(route(), { method: 'DELETE', body: '{}' });
      state.connections = result.connections; select(state.connections[0]?.id || '__new__');
      emitSignal('prompt-settings-changed');
      notify(t(result.revoked ? 'LLM API 已删除。' : '已在本机断开；远端撤销未确认，请在 ChatGPT 设置中断开应用。'), { kind: result.revoked ? 'success' : 'warning' });
    }),
    welcome: () => run(async () => {
      await api(route() + '/welcome', { method: 'POST', body: '{}' }); state.welcome = false;
    }),
    dispose() { disposed = true; clearTimeout(timer); },
  };
}
