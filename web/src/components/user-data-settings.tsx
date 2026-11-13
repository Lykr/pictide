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
import { Checkbox } from './ui/checkbox';
import { HelpTip, IconButton } from './actions';

async function responseError(response: Response) {
  const body = await response.json().catch(() => null);
  return body?.error || tr`请求失败（${response.status}）`;
}

export function UserDataSettings() {
  const app = useApplication(), state = useModel(app.model);
  const input = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [includeLiked, setIncludeLiked] = useState(true);
  const [includePreferences, setIncludePreferences] = useState(true);
  const [error, setError] = useState('');
  useErrorNotice(t(messageKey(error)), { id: 'user-data' });
  const busy = exporting || importing;
  const local = state.userDataLocal === true;
  const selected = includeLiked || includePreferences;

  const exportData = async () => {
    if (busy || !local) return;
    if (!selected) { setError(t('至少选择一种要导出的数据。')); return; }
    setExporting(true); setError('');
    try {
      const response = await fetch('/api/user-data/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/zip' },
        body: JSON.stringify({ liked_images: includeLiked, preferences: includePreferences }),
      });
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
    if (!await confirmAction(t('导入用户数据？仅会应用压缩包包含的数据：包括喜欢图片时会添加缺失图片；包括学习偏好时会替换当前学习状态。未包含的数据保持不变。现有数据库会先自动备份。'))) return;
    setImporting(true); setError('');
    try {
      const response = await fetch('/api/user-data/import', {
        method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      const likedCount = result.liked_imported.toLocaleString();
      const evidenceCount = result.preference_evidence.toLocaleString();
      const summary = result.categories?.liked_images && result.categories?.preferences
        ? t('已导入 {liked} 张喜欢图片和 {evidence} 条偏好证据', { liked: likedCount, evidence: evidenceCount })
        : result.categories?.liked_images
          ? t('已导入 {liked} 张喜欢图片', { liked: likedCount })
          : t('已导入 {evidence} 条偏好证据', { evidence: evidenceCount });
      notifySuccess(summary, { id: 'user-data-import' });
      setTimeout(() => window.location.reload(), 700);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally { setImporting(false); }
  };

  return <div className="settings-stack">
    <SettingsRow className="settings-data-location" label={t('数据位置')} stackOnMobile>
      <code id="data-directory">{state.dataDirectory || t('读取中…')}</code>
    </SettingsRow>
    <SettingsRow stackOnMobile label={<div className="flex items-center gap-1">
      <span>{t('迁移用户数据')}</span>
      <HelpTip text={local
        ? t('选择要导出的类别。导入时只应用压缩包包含的数据；未包含的数据保持不变。')
        : t('导入和导出仅可在运行 Pictide 的电脑上通过本机地址操作。')} />
    </div>}>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <label className="flex items-center gap-2" htmlFor="user-data-include-liked">
            <Checkbox id="user-data-include-liked" checked={includeLiked} onCheckedChange={value => setIncludeLiked(value === true)} disabled={busy} />
            {t('喜欢图片和提示词')}
          </label>
          <label className="flex items-center gap-2" htmlFor="user-data-include-preferences">
            <Checkbox id="user-data-include-preferences" checked={includePreferences} onCheckedChange={value => setIncludePreferences(value === true)} disabled={busy} />
            {t('反馈和学习偏好')}
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <IconButton id="user-data-export" className={`border border-border ${exporting ? '[&_svg]:animate-spin' : ''}`} icon={exporting ? LoaderCircle : Download} label={exporting ? t('正在导出用户数据') : t('导出所选用户数据')} tooltip={t('导出所选的喜欢图片和/或学习偏好')} disabled={busy || !local} onClick={() => void exportData()} />
          <IconButton id="user-data-import" className={`border border-border ${importing ? '[&_svg]:animate-spin' : ''}`} icon={importing ? LoaderCircle : Upload} label={importing ? t('正在导入用户数据') : t('导入用户数据')} tooltip={t('仅应用压缩包包含的数据类别；现有数据库会先自动备份')} disabled={busy || !local} onClick={() => input.current?.click()} />
          <input ref={input} id="user-data-file" className="sr-only" type="file" accept=".zip,application/zip" aria-label={t('选择用户数据压缩包')} onChange={event => void importData(event)} />
        </div>
      </div>
    </SettingsRow>
    <PreferenceActions />
    <ImageCleanupSettings />
  </div>;
}
