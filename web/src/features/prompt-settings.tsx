import { useEffect } from 'react';
import { useApplication, useModel } from '../shared/application-context';
import { t } from '../i18n/index.mjs';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { Disclosure } from '../components/disclosure';

export function PromptSettings() {
  const service = useApplication().backendSettings.prompting;
  const state = useModel(service.model);
  useEffect(() => { void service.load(); }, [service]);
  const input = (key: string) => ({ value: state.draft[key], onChange: (e: React.ChangeEvent<HTMLInputElement>) => service.edit(key, e.target.value) });
  return <Disclosure className="settings-stack" title={t('自然语言提示词服务')}>
    <p className="hint">{t('使用 OpenAI-compatible 文本 API，将标签转换为生图描述。标签会发送给此服务，调用可能产生费用。')}</p>
    <form className="settings-stack" inert={state.busy} onSubmit={e => { e.preventDefault(); void service.save(); }}>
      <div className="form-grid">
        <div className="settings-field"><Label htmlFor="prompt-api-url">{t('API 地址')}</Label><Input id="prompt-api-url" type="url" required placeholder="https://example.com/v1" {...input('base_url')} /></div>
        <div className="settings-field"><Label htmlFor="prompt-api-model">{t('文本模型')}</Label><Input id="prompt-api-model" required {...input('model')} /></div>
      </div>
      <div className="settings-field"><Label htmlFor="prompt-api-key">API Key</Label><Input id="prompt-api-key" type="password" autoComplete="new-password" {...input('key')} onFocus={e => { if (state.hasKey) e.target.select(); }} /></div>
      <div className="dialog-footer"><Button type="submit" disabled={state.busy || !state.loaded}>{t('保存提示词服务')}</Button></div>
    </form>
  </Disclosure>;
}
