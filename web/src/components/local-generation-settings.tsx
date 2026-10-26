import '../styles/local-generation.css';
import { useEffect, useState } from 'react';
import { ChevronDown, LoaderCircle, Search } from 'lucide-react';
import { useApplication, useModel } from '../shared/application-context';
import { t, messageKey } from '../i18n/index.mjs';
import { notifySuccess } from '../shared/notifications.mjs';
import { SettingsRow } from './settings-row';
import { useErrorNotice } from './notifications';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from './ui/select';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible';

const phases: Record<string, string> = {
  disabled: '未启用', starting: '正在启动 ComfyUI…', running: 'ComfyUI 已由 Pictide 启动',
  external: '正在使用已运行的 ComfyUI', failed: 'ComfyUI 启动失败', stopped: 'ComfyUI 已停止',
};

export function LocalGenerationSettings() {
  const app = useApplication();
  const application = useModel(app.model);
  const controller = app.localGeneration;
  const state = useModel(controller.model);
  const [advanced, setAdvanced] = useState(false);
  const [selected, setSelected] = useState('');
  const busy = !!state.busy;
  const draft = state.draft;
  const visible = application.view === 'settings' && application.settingsSection === 'general';
  useEffect(() => { if (visible) void controller.load(); }, [controller, visible]);
  useErrorNotice(t(messageKey(state.error)), { id: 'local-generation-settings' });
  useEffect(() => setSelected(''), [state.candidates]);
  const field = (key: string) => ({ value: draft[key], disabled: busy,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => controller.edit(key, event.target.value) });
  const save = async () => {
    if (await controller.save()) notifySuccess(() => t('已保存，下次启动 Pictide 时生效。'), { id: 'local-generation-saved' });
  };
  return <SettingsRow separated stackOnMobile className="local-generation-settings" label={t('ComfyUI 随应用启停')}>
    {state.canConfigure === null ? <div className="flex flex-col items-start gap-2"><span className="text-sm text-muted-foreground">{t(state.error ? '读取启停设置失败。' : '正在读取…')}</span>
      {state.error && <Button type="button" variant="outline" onClick={() => void controller.load()}>{t('重试')}</Button>}</div> : state.canConfigure === false ?
      <p className="text-sm text-muted-foreground">{t('请在运行 Pictide 的电脑上通过本机地址配置。')}</p> :
      <div className="flex min-w-0 flex-col gap-3">
        <Label htmlFor="local-generation-enabled" className="gap-2">
          <Checkbox id="local-generation-enabled" checked={draft.enabled} disabled={busy} onCheckedChange={value => controller.edit('enabled', value === true)} />
          <span>{t('跟随 Pictide 启动和退出')}</span>
        </Label>
        <p className="text-sm leading-relaxed text-muted-foreground">{t('已运行的 ComfyUI 会直接复用；退出时只关闭本次由 Pictide 启动的进程。')}</p>
        {draft.enabled && <div className="flex min-w-0 flex-col gap-3">
          {state.choices.length ? <div className="grid min-w-0 gap-1.5">
            <Label htmlFor="local-generation-backend">{t('关联生图 API')}</Label>
            <Select value={draft.backend_id} disabled={busy} onValueChange={value => controller.edit('backend_id', value)}>
              <SelectTrigger id="local-generation-backend" className="w-full"><SelectValue placeholder={t('选择本机 ComfyUI')} /></SelectTrigger>
              <SelectContent>{state.choices.map((item: { id: string; name: string }) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
            </Select>
          </div> : <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-muted-foreground">{t('请先保存一个本机 ComfyUI 生图 API。')}</p>
            <Button type="button" variant="outline" onClick={() => app.setSettingsSection('backend')}>{t('配置生图 API')}</Button>
          </div>}
          <div className="grid min-w-0 gap-1.5">
            <Label htmlFor="local-generation-path">{t('ComfyUI 安装路径')}</Label>
            <Input id="local-generation-path" autoComplete="off" placeholder={t('输入安装目录，或留空后自动识别')} {...field('install_dir')} />
          </div>
          <Button type="button" className="self-start" variant="outline" disabled={busy || !draft.backend_id} onClick={() => void controller.detect()}>
            {state.busy === 'detect' ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Search aria-hidden="true" />}{t('自动识别')}
          </Button>
          {state.candidates.length > 1 && <div className="grid min-w-0 gap-1.5">
            <Label htmlFor="local-generation-candidates">{t('选择识别结果')}</Label>
            <Select value={selected} disabled={busy} onValueChange={value => { setSelected(value); controller.choose(Number(value)); }}>
              <SelectTrigger id="local-generation-candidates" className="w-full"><SelectValue placeholder={t('选择 ComfyUI 安装')} /></SelectTrigger>
              <SelectContent className="max-w-[calc(100vw-2rem)]">{state.candidates.map((item: { install_dir: string }, index: number) => <SelectItem className="wrap-anywhere whitespace-normal" key={index} value={String(index)}>{item.install_dir}</SelectItem>)}</SelectContent>
            </Select>
          </div>}
          <Collapsible open={advanced} onOpenChange={setAdvanced}>
            <CollapsibleTrigger asChild><Button type="button" variant="ghost" size="sm"><ChevronDown aria-hidden="true" />{t('高级启动配置')}</Button></CollapsibleTrigger>
            <CollapsibleContent className="mt-2 grid min-w-0 gap-3">
              {([['python', 'Python 解释器'], ['entry', 'ComfyUI 入口文件'], ['cwd', '工作目录']] as const).map(([key, label]) => <div className="grid min-w-0 gap-1.5" key={key}>
                <Label htmlFor={`local-generation-${key}`}>{t(label)}</Label><Input id={`local-generation-${key}`} autoComplete="off" {...field(key)} />
              </div>)}
              <div className="grid min-w-0 gap-1.5"><Label htmlFor="local-generation-args">{t('启动参数（每行一个参数）')}</Label>
                <Textarea id="local-generation-args" className="min-h-32 font-mono text-xs" spellCheck={false} {...field('args')} />
                <p className="text-sm text-muted-foreground">{t('带空格的路径也占一行，无需引号。监听地址和端口跟随关联 API。')}</p>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" disabled={busy || !state.dirty} onClick={() => void save()}>
            {state.busy === 'save' && <LoaderCircle className="animate-spin" aria-hidden="true" />}{t('保存启停设置')}
          </Button>
          {state.dirty && <span className="text-sm text-muted-foreground">{t('有未保存的修改')}</span>}
        </div>
        {state.restartRequired && <p className="text-sm text-muted-foreground" role="status">{t('下次启动 Pictide 时生效。')}</p>}
        {state.status && <div className="grid min-w-0 gap-1 text-sm text-muted-foreground" data-local-generation-status="">
          <span>{t('本次运行：{status}', { status: t(phases[state.status.phase] || '未启用') })}</span>
          {state.status.url && <span className="wrap-anywhere">{state.status.url}</span>}
          {state.status.error && <><p className="wrap-anywhere">{t(messageKey(state.status.error))}</p>
            <span className="wrap-anywhere">{t('日志：{path}', { path: state.status.log_path })}</span></>}
        </div>}
      </div>}
  </SettingsRow>;
}
