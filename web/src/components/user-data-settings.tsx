import { useRef, useState } from 'react';
import { Download, LoaderCircle, Upload } from 'lucide-react';
import { useApplication, useModel } from '../shared/application-context';
import { t, messageKey, tr } from '../i18n/index.mjs';
import { notifySuccess } from '../shared/notifications.mjs';
import { confirmAction } from './confirm-action';
import { useErrorNotice } from './notifications';
import { PreferenceActions } from './preference-actions';
import { ImageCleanupSettings } from '../features/history-settings';
import { SettingsRow } from './settings-row';
import { Button } from './ui/button';

async function responseError(response: Response) {
  const body = await response.json().catch(() => null);
  return body?.error || tr`请求失败（${response.status}）`;
}

export function UserDataSettings() {
  const app = useApplication(), state = useModel(app.model);
  const input = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  useErrorNotice(t(messageKey(error)), { id: 'user-data' });
  const busy = exporting || importing;
  const local = state.userDataLocal === true;

  const exportData = async () => {
    if (busy || !local) return;
    setExporting(true); setError('');
    try {
      const response = await fetch('/api/user-data/export', { headers: { Accept: 'application/zip' } });
      if (!response.ok) throw new Error(await responseError(response));
      const disposition = response.headers.get('Content-Disposition') || '';
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] || 'pictide-user-data.zip';
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notifySuccess(t('用户数据已导出'), { id: 'user-data-export' });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally { setExporting(false); }
  };

  const importData = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || busy || !local) return;
    if (!await confirmAction(t('导入用户数据？将添加压缩包中的喜欢图片，并替换当前学习偏好。现有数据库会先自动备份。'))) return;
    setImporting(true); setError('');
    try {
      const response = await fetch('/api/user-data/import', {
        method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      notifySuccess(t('已导入 {liked} 张喜欢图片和 {evidence} 条偏好证据', {
        liked: result.liked_imported.toLocaleString(), evidence: result.preference_evidence.toLocaleString(),
      }), { id: 'user-data-import' });
      setTimeout(() => window.location.reload(), 700);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally { setImporting(false); }
  };

  return <div className="settings-stack">
    <SettingsRow className="settings-data-location" label={t('数据位置')} stackOnMobile>
      <code id="data-directory">{state.dataDirectory || t('读取中…')}</code>
    </SettingsRow>
    <SettingsRow stackOnMobile label={<div className="flex flex-col gap-1">
      <span>{t('迁移用户数据')}</span>
      <span className="text-sm text-muted-foreground">{t('包含喜欢图片、反馈和已学习的偏好。')}</span>
    </div>}>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button id="user-data-export" type="button" variant="outline" disabled={busy || !local} onClick={() => void exportData()}>
            {exporting ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Download aria-hidden="true" />}
            {t('导出用户数据')}
          </Button>
          <Button id="user-data-import" type="button" variant="outline" disabled={busy || !local} onClick={() => input.current?.click()}>
            {importing ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}
            {t('导入用户数据')}
          </Button>
          <input ref={input} id="user-data-file" className="sr-only" type="file" accept=".zip,application/zip" aria-label={t('选择用户数据压缩包')} onChange={event => void importData(event)} />
        </div>
        {!local && <p className="hint">{t('请在运行 Pictide 的电脑上通过本机地址操作。')}</p>}
      </div>
    </SettingsRow>
    <PreferenceActions />
    <ImageCleanupSettings />
  </div>;
}
