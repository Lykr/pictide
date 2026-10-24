import { emitSignal } from '../shared/signals.mjs';
import { createModel } from '../shared/model.mjs';
import { notifySuccess, notifyError } from '../shared/notifications.mjs';
import { API_KEY_MASK, apiKeyFields } from './settings-controls.mjs';
import { t } from '../i18n/index.mjs';

export function createPromptSettings(api) {
  const model = createModel({ draft: { base_url: '', model: '', key: '' }, loaded: false, busy: false, dirty: false, hasKey: false });
  const apply = value => {
    model.data.hasKey = value.has_api_key;
    Object.assign(model.data.draft, { base_url: value.base_url, model: value.model, key: value.has_api_key ? API_KEY_MASK : '' });
    model.data.loaded = true; model.data.dirty = false;
  };
  return {
    model,
    edit(key, value) { model.data.draft[key] = value; model.data.dirty = true; model.changed(); },
    async load() {
      if (model.data.loaded || model.data.busy) return;
      model.data.busy = true; model.changed();
      try { apply(await api('/api/settings/prompting')); }
      catch (error) { notifyError(error.message); }
      finally { model.data.busy = false; model.changed(); }
    },
    async save() {
      if (model.data.busy) return;
      model.data.busy = true; model.changed();
      try {
        const { base_url, model: name, key } = model.data.draft;
        apply(await api('/api/settings/prompting', { method: 'PUT', body: JSON.stringify({ base_url, model: name, ...apiKeyFields(key, model.data.hasKey) }) }));
        emitSignal('prompt-settings-changed');
        notifySuccess(t('提示词服务已保存。'));
      } catch (error) { notifyError(error.message); }
      finally { model.data.busy = false; model.changed(); }
    },
  };
}
