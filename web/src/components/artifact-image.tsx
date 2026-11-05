import { useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { t } from '../i18n/index.mjs';
import { imageSeedLabel } from '../controllers/backend-controls.mjs';
import { notifyError } from '../shared/notifications.mjs';
import type { GeneratedArtifact } from './generated-viewer';

export function ArtifactImage({ item, label }: { item: GeneratedArtifact; label: string }) {
  const [status, setStatus] = useState('loading');
  return <div className="generated-thumbnail">
    <img src={`/api/artifacts/${encodeURIComponent(item.id)}/image?thumbnail=1`} alt={`${label} · ${imageSeedLabel(item)}`} loading="lazy" decoding="async"
      onLoad={() => setStatus('ready')}
      onError={() => { setStatus('error'); notifyError(t('图片已清理或读取失败'), { id: 'artifact-image-load' }); }} />
    {status === 'loading' && <span className="generated-image-state" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" /><span className="sr-only">{t('图片加载中')}</span></span>}
    {status === 'error' && <span className="generated-image-state" role="status">{t('图片已清理或读取失败')}</span>}
  </div>;
}
