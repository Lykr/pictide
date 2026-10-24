import { useEffect } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { useApplication, useModel } from '../shared/application-context';
import { t } from '../i18n/index.mjs';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { FormSelect } from '../components/form-select';
import { IconButton } from '../components/actions';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../components/ui/dialog';

export function PromptSettings() {
  const service = useApplication().promptSettings;
  const state = useModel(service.model), draft = state.draft;
  useEffect(() => { void service.load(); }, [service]);
  const input = (key: string) => ({ value: draft[key], onChange: (e: React.ChangeEvent<HTMLInputElement>) => service.edit(key, e.target.value) });
  const chatgpt = draft.kind === 'chatgpt';
  const choices = state.models.length ? state.models : draft.model ? [{value:draft.model, label:draft.model}] : [{value:'', label:t('读取模型后选择')}];
  return <>
    <form className="settings-stack" inert={state.busy} onSubmit={e => { e.preventDefault(); void service.save(); }}>
      <div className="form-grid">
        <div className="settings-field"><div className="settings-field-heading"><Label htmlFor="edit-llm">{t('已有 API')}</Label><IconButton icon={Trash2} label={t('删除 LLM API')} size="icon-xs" onClick={service.remove} disabled={draft.id === '__new__' || state.signingIn} /></div>
          <FormSelect id="edit-llm" value={draft.id} onValueChange={service.select} disabled={state.signingIn} options={[...state.connections.map((row: any) => ({value:row.id,label:row.name})), {value:'__new__',label:t('＋ 添加 API')}]} /></div>
        <div className="settings-field"><Label htmlFor="llm-name">{t('API 名称')}</Label><Input id="llm-name" required maxLength={100} {...input('name')} disabled={state.signingIn} /></div>
        <div className="settings-field"><Label htmlFor="llm-kind">{t('接入方式')}</Label><FormSelect id="llm-kind" value={draft.kind} onValueChange={value => service.edit('kind',value)} disabled={draft.id !== '__new__'} options={[{value:'openai',label:'OpenAI-compatible API'}, {value:'chatgpt',label:'ChatGPT'}]} /></div>
      </div>
      {!chatgpt ? <>
        <div className="form-grid">
          <div className="settings-field"><Label htmlFor="prompt-api-url">{t('API 地址')}</Label><Input id="prompt-api-url" type="url" required placeholder="https://example.com/v1" {...input('base_url')} /></div>
          <div className="settings-field"><Label htmlFor="prompt-api-model">{t('文本模型')}</Label><Input id="prompt-api-model" required {...input('model')} /></div>
        </div>
        <div className="settings-field"><Label htmlFor="prompt-api-key">API Key</Label><Input id="prompt-api-key" type="password" autoComplete="new-password" {...input('key')} onFocus={e => { if (state.hasKey) e.target.select(); }} /></div>
        <p className="hint">{t('标签会发送给此服务，API 调用可能产生费用。')}</p>
      </> : <>
        <p className="hint">{t('使用 ChatGPT 订阅额度生成自然语言提示词。')}</p>
        {state.account?.connected && <p>{state.account.email || 'ChatGPT'} · {t(state.account.plan_enabled ? '已连接' : '尚未授权使用订阅额度')}</p>}
        <div className="button-row">
          {state.signingIn ? <><span role="status">{t('等待浏览器授权…')}</span><Button variant="outline" type="button" onClick={service.cancel}>{t('取消')}</Button></> : <Button variant="outline" type="button" onClick={service.connect}>{t('使用 ChatGPT 继续')}</Button>}
          {state.account?.connected && !state.signingIn && <Button variant="ghost" type="button" onClick={service.disconnect}>{t('断开连接')}</Button>}
        </div>
        {state.account?.connected && state.account.plan_enabled && <div className="settings-field">
          <div className="settings-field-heading"><Label htmlFor="prompt-chatgpt-model">{t('文本模型')}</Label><IconButton icon={RefreshCw} label={t('读取模型')} size="icon-xs" onClick={service.models} disabled={state.signingIn} /></div>
          <FormSelect id="prompt-chatgpt-model" value={draft.model} onValueChange={value => service.edit('model',value)} options={choices} disabled={state.signingIn} />
          <p className="hint">{t('正在使用 ChatGPT 订阅')} · <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noreferrer">{t('管理用量')}</a></p>
        </div>}
      </>}
      <div className="dialog-footer"><Button type="submit" disabled={!state.loaded || state.signingIn}>{t('保存 LLM API')}</Button></div>
    </form>
    <Dialog open={state.welcome} onOpenChange={open => { if (!open) void service.welcome(); }}><DialogContent><DialogHeader><DialogTitle>{t('正在使用 ChatGPT 订阅')}</DialogTitle><DialogDescription>{t('Pictide 生成提示词将使用你的订阅额度，可在 ChatGPT 设置中管理用量。')}</DialogDescription></DialogHeader><DialogFooter><Button onClick={service.welcome}>{t('知道了')}</Button></DialogFooter></DialogContent></Dialog>
  </>;
}
