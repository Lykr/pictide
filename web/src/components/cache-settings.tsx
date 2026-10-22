import { useRef, useState } from 'react';
import { Eraser, LoaderCircle } from 'lucide-react';
import { t } from '../i18n/index.mjs';
import { dismissNotification, notifyError, notifySuccess } from '../shared/notifications.mjs';
import { SettingsRow } from './settings-row';
import { HelpTip } from './actions';
import { Button } from './ui/button';

export function CacheSettings() {
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const clear = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true);
    dismissNotification('cache-cleanup');
    try {
      const response = await fetch('/api/settings/cache/clear', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.error || t('缓存清理失败，请重试。'));
      if (!Number.isSafeInteger(result?.deleted_image_scores) || result.deleted_image_scores < 0) {
        throw new Error(t('响应不完整，请重试。'));
      }
      const count = result.deleted_image_scores;
      notifySuccess(() => count ? t('已清除 {count} 条缓存。', { count }) : t('没有需要清除的缓存。'), { id: 'cache-cleanup' });
    } catch (error) {
      notifyError(error instanceof Error ? error.message : String(error), { id: 'cache-cleanup' });
    } finally { pending.current = false; setBusy(false); }
  };
  return <SettingsRow label={<>{t('缓存')}<HelpTip text={t('清除已删除图片的评分缓存，保留图片和偏好。')} /></>}>
    <Button type="button" variant="outline" onClick={clear} aria-disabled={busy} aria-busy={busy} className="aria-disabled:opacity-50">
      {busy ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Eraser aria-hidden="true" />}{t('清除缓存')}
    </Button>
  </SettingsRow>;
}
