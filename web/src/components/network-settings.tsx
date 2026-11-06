import { useEffect, useState } from 'react';
import { Copy, LoaderCircle, RefreshCw } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useApplication, useModel } from '../shared/application-context';
import { t, messageKey } from '../i18n/index.mjs';
import { copyText } from '../lib/copy-text';
import { notifySuccess } from '../shared/notifications.mjs';
import { useErrorNotice } from './notifications';
import { SettingsRow } from './settings-row';
import { IconButton } from './actions';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

type NetworkStatus = { enabled: boolean; available: boolean; can_configure: boolean; urls: string[] };

export function NetworkSettings() {
  const app = useApplication(), application = useModel(app.model);
  const [status, setStatus] = useState<NetworkStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const visible = application.view === 'settings' && application.settingsSection === 'general';
  useErrorNotice(t(messageKey(error)), { id: 'network-settings', visible });
  const url = status?.urls.includes(selected) ? selected : status?.urls[0] || '';
  const load = async (enabled?: boolean, signal?: AbortSignal) => {
    setBusy(true); setError('');
    try {
      const response = await fetch('/api/settings/network', {
        signal, ...(enabled === undefined ? {} : { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || t('局域网设置读取失败'));
      setStatus(result);
    } catch (failure) {
      if (!signal?.aborted) setError(failure instanceof Error ? failure.message : String(failure));
    } finally { if (!signal?.aborted) setBusy(false); }
  };
  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    void load(undefined, controller.signal);
    return () => controller.abort();
  }, [visible]);
  const copy = async () => {
    try { await copyText(url); notifySuccess(t('已复制'), { id: 'clipboard' }); }
    catch { setError(t('复制失败，请选中文本复制')); }
  };
  return <SettingsRow separated stackOnMobile align="start" label={t('局域网访问')}>
    <div className="flex min-w-0 flex-col items-start gap-3" data-network-settings="">
      <Label htmlFor="network-enabled" className="gap-2">
        <Checkbox id="network-enabled" checked={status?.enabled ?? false}
          disabled={busy || !status?.can_configure || !status.available}
          onCheckedChange={value => void load(value === true)} />
        {t('允许同一局域网的设备访问')}{busy && <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />}
      </Label>
      <p className="text-sm text-muted-foreground">{t('立即生效，本次运行有效。访问设备共用图片、设置和偏好。')}</p>
      {status && !status.can_configure && <p className="text-sm text-muted-foreground">{t('请在运行 Pictide 的电脑上通过本机地址配置。')}</p>}
      {error && <Button variant="outline" type="button" disabled={busy} onClick={() => void load()}>{t('重试')}</Button>}
      {status?.enabled && <>
        {status.urls.length > 1 && <Select value={url} onValueChange={setSelected}>
          <SelectTrigger aria-label={t('局域网地址')} className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>{status.urls.map(address => <SelectItem key={address} value={address}>{address}</SelectItem>)}</SelectContent>
        </Select>}
        {url ? <>
          <div className="flex w-full min-w-0 items-center gap-2">
            <a className="min-w-0 break-all text-sm underline" href={url}>{url}</a>
            <IconButton icon={Copy} label={t('复制访问地址')} onClick={() => void copy()} />
            <IconButton icon={busy ? LoaderCircle : RefreshCw} className={busy ? '[&_svg]:animate-spin' : ''} label={t('刷新访问地址')} disabled={busy} onClick={() => void load()} />
          </div>
          <QRCodeSVG value={url} size={160} marginSize={4} title={t('手机扫码访问 Pictide')} className="max-w-full rounded-md" />
          <p className="text-sm text-muted-foreground">{t('地址对应本机的不同网卡。手机连接同一局域网后扫码，连接受阻时检查防火墙的专用网络权限。')}</p>
        </> : <p className="text-sm text-muted-foreground">{t('未找到局域网地址，请检查网络后刷新。')}</p>}
      </>}
    </div>
  </SettingsRow>;
}
