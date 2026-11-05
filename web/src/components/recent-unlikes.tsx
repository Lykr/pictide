import { useEffect, useState } from 'react';
import { HeartPlus, History, LoaderCircle, RotateCw } from 'lucide-react';
import { useApplication, useModel } from '../shared/application-context';
import { t } from '../i18n/index.mjs';
import { IconButton } from './actions';
import { ArtifactImage } from './artifact-image';
import { GeneratedViewer, type GeneratedArtifact } from './generated-viewer';
import { useErrorNotice } from './notifications';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog';
import '../styles/recent-unlikes.css';

type RecoverableArtifact = GeneratedArtifact & { unliked_protected_until: string };

function remaining(deadline: string, now: number) {
  const minutes = Math.max(1, Math.ceil((Date.parse(deadline) - now) / 60000));
  return minutes > 60 ? t('剩余 {count} 小时', { count: Math.ceil(minutes / 60) }) : t('剩余 {count} 分钟', { count: minutes });
}

export function RecentUnlikes({ visible, busy, privacyBlur, onPrivacyChange }: {
  visible: boolean; busy: boolean; privacyBlur: boolean; onPrivacyChange: (value: boolean) => void;
}) {
  const app = useApplication(), service = app.recentUnlikes;
  const state = useModel(service.model);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => { if (!visible) service.setOpen(false); }, [visible, service]);
  useEffect(() => () => service.setOpen(false), [service]);
  useEffect(() => { if (!state.open) setSelectedId(null); }, [state.open]);
  useErrorNotice(state.error, { id: 'recent-unlikes', visible: state.open, retry: () => service.retry() });
  const restore = (item: GeneratedArtifact) => { void app.restoreLike(item.id); };
  const label = t('最近取消喜欢');
  return <Dialog open={state.open} onOpenChange={value => service.setOpen(value)}>
    <DialogTrigger asChild data-slot="button"><IconButton icon={History} label={label} className="generated-privacy-toggle" data-tooltip-hover-only="" /></DialogTrigger>
    <DialogContent className="recent-unlikes-dialog">
      <DialogHeader className="pr-8">
        <DialogTitle>{label}</DialogTitle>
        <DialogDescription>{t('缓冲期内可重新喜欢；到期后按清理规则处理。')}</DialogDescription>
      </DialogHeader>
      <div className="recent-unlikes-scroll" aria-busy={state.loading}>
        {state.loading && !state.artifacts.length && <div className="recent-unlikes-empty" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" />{t('加载中…')}</div>}
        {!state.loading && !state.error && !state.artifacts.length && <div className="recent-unlikes-empty"><History aria-hidden="true" /><p>{t('最近 24 小时没有取消喜欢的图片。')}</p></div>}
        <div className={`recent-unlikes-grid${privacyBlur ? ' generated-privacy-blurred' : ''}`}>
          {state.artifacts.map((item: RecoverableArtifact) => <Card key={item.id} className="gap-0 py-0" data-recent-unlike={item.id}>
            <Button type="button" variant="ghost" className="recent-unlikes-image" aria-label={t('查看图片 {id}', { id: item.id })} onClick={() => setSelectedId(item.id)}>
              <ArtifactImage item={item} label={label} />
            </Button>
            <div className="recent-unlikes-actions">
              <span className="text-xs text-muted-foreground">{remaining(item.unliked_protected_until, state.now)}</span>
              <Button type="button" variant="secondary" className="w-full" disabled={busy} onClick={() => restore(item)}><HeartPlus aria-hidden="true" />{t('重新喜欢')}</Button>
            </div>
          </Card>)}
        </div>
        {(state.hasMore || state.error) && <div className="recent-unlikes-more">
          <Button type="button" variant="outline" disabled={state.loading} onClick={() => state.error ? service.retry() : service.more()}>
            {state.loading ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : state.error ? <RotateCw aria-hidden="true" /> : null}
            {state.loading ? t('加载中…') : state.error ? t('重试') : t('加载更多')}
          </Button>
        </div>}
      </div>
    </DialogContent>
    <GeneratedViewer items={state.artifacts} activeId={state.open ? selectedId : null} onActiveChange={setSelectedId}
      imageLabel={label} privacyBlur={privacyBlur} onPrivacyChange={onPrivacyChange} busy={busy}
      onLike={restore} hasMore={state.hasMore} loadingMore={state.loading} onMore={() => service.more()} error={state.error} />
  </Dialog>;
}
