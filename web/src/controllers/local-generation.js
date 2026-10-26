import { createModel } from '../shared/model.mjs';
import { t } from '../i18n/index.mjs';

const empty = () => ({ enabled: false, backend_id: '', install_dir: '', python: '', entry: '', cwd: '', args: '' });
const draftOf = config => ({ ...config, args: config.args.join('\n') });

export function createLocalGeneration(request) {
  const state = { draft: empty(), saved: null, choices: [], candidates: [], status: null,
    canConfigure: null, restartRequired: false, dirty: false, busy: '', error: '' };
  const model = createModel(state);
  let revision = 0, readRevision = 0, disposed = false;
  const changed = () => { if (!disposed) model.changed(); };
  const dirty = () => { state.dirty = !!state.saved && JSON.stringify(state.draft) !== JSON.stringify(draftOf(state.saved)); };
  function receive(next, replaceDraft = false) {
    state.canConfigure = next.can_configure;
    if (!next.can_configure) return;
    state.status = next.status; state.choices = next.choices;
    state.restartRequired = next.restart_required;
    if (replaceDraft || !state.saved || !state.dirty) state.draft = draftOf(next.config);
    state.saved = next.config;
    dirty();
  }
  async function load() {
    const current = ++readRevision;
    try {
      const next = await request('/api/settings/local-generation');
      if (disposed || current !== readRevision) return;
      if (state.canConfigure === null) state.error = '';
      receive(next); changed();
    } catch (error) {
      if (disposed || current !== readRevision) return;
      state.error = error.message; changed();
    }
  }
  function edit(key, value) {
    revision++;
    state.draft[key] = value;
    if (key === 'install_dir') Object.assign(state.draft, { python: '', entry: '', cwd: '' });
    if (key === 'enabled' && value && !state.draft.backend_id && state.choices.length === 1) state.draft.backend_id = state.choices[0].id;
    state.candidates = []; state.error = ''; dirty(); changed();
  }
  function choose(index) {
    const item = state.candidates[index];
    if (!item) return;
    revision++;
    const { install_dir, python, entry, cwd, args } = item;
    Object.assign(state.draft, { install_dir, python, entry, cwd, args: args.join('\n') });
    state.error = ''; dirty(); changed();
  }
  async function detect() {
    if (state.busy) return;
    state.busy = 'detect'; state.error = ''; state.candidates = []; changed();
    const current = revision;
    try {
      const result = await request('/api/settings/local-generation/detect', { method: 'POST', body: JSON.stringify({
        backend_id: state.draft.backend_id, install_dir: state.draft.install_dir,
      }) });
      if (disposed || revision !== current) return;
      state.candidates = result.candidates;
      if (result.candidates.length === 1) choose(0);
      else if (!result.candidates.length) state.error = t('没有识别到可启动的 ComfyUI，请手动指定路径和 Python。');
    } catch (error) { if (!disposed && revision === current) state.error = error.message; }
    finally { state.busy = ''; changed(); }
  }
  async function save() {
    if (state.busy) return false;
    state.busy = 'save'; state.error = ''; changed();
    const current = revision;
    const payload = { ...state.draft, args: state.draft.args.split(/\r?\n/).filter(value => value !== '') };
    try {
      const next = await request('/api/settings/local-generation', { method: 'PUT', body: JSON.stringify(payload) });
      if (disposed) return false;
      ++readRevision;
      receive(next, revision === current);
      state.candidates = [];
      return true;
    } catch (error) { if (!disposed) state.error = error.message; return false; }
    finally { state.busy = ''; changed(); }
  }
  return { model, load, edit, detect, choose, save, dispose() { disposed = true; } };
}
