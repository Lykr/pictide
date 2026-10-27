import { useLayoutEffect, useRef, useState } from 'react';
import { LoaderCircle, LockKeyhole, Scan, X } from 'lucide-react';
import { useApplication, useModel, useUiFact } from '../shared/application-context';
import { runUiCommand } from '../shared/ui-state.mjs';
import { backendCapabilities } from '../controllers/backend-controls.mjs';
import { generationSizes, generationSizeFields } from '../controllers/generation-controls.mjs';
import { t, tr } from '../i18n/index.mjs';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { useErrorNotice } from './notifications';

/** A canvas pin affects future image tasks, independently of prompt anchors. */
export function RoamCanvas() {
  const app = useApplication(), state = useModel(app.model);
  const pools = useModel(app.canvasPools.model);
  const options = useUiFact('roamOptions');
  const image = useUiFact('imageInfo');
  const pixels = useUiFact('imagePixels');
  const immersive = useUiFact('roamImmersive', false);
  const root = useRef<HTMLElement>(null);
  const [container, setContainer] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => { setContainer(immersive ? root.current?.closest<HTMLElement>('.image-card') ?? null : null); }, [immersive]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useErrorNotice(error, { id: 'roam-canvas' });
  const backend = state.backends.find((item: any) => item.id === options?.backend_id) || (!options?.backend_id ? state.backends[0] : null);
  const supported = !!backend && backendCapabilities(backend).dimensions;
  const pinned = options?.pinned_canvas;
  const value = pinned ? `${pinned.width}x${pinned.height}` : '';
  const current = image?.width && image?.height ? `${image.width}x${image.height}`
    : image?.id && pixels?.id === image.id && pixels.width && pixels.height ? `${pixels.width}x${pixels.height}` : '';
  const usable = (size: string) => {
    if (!backend || !size) return false;
    try { generationSizeFields(size, backend); return true; } catch { return false; }
  };
  const currentUsable = usable(current);
  const sizes = generationSizes(backend, pools.pools);
  for (const size of [value, currentUsable ? current : '']) {
    if (size && !sizes.some((item: any) => item.value === size)) sizes.push({ value: size, label: size.replace('x', '×') });
  }
  const save = async (size: string) => {
    if (!options || busy) return;
    setBusy(true); setError('');
    try {
      await runUiCommand('roam-settings-save', { pinned_canvas: size ? generationSizeFields(size, backend) : null });
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setBusy(false); }
  };
  return <section ref={root} className="roam-anchor-canvas" aria-label={t('画幅')}>
    <div className="roam-canvas-heading">
      <Label htmlFor="roam-canvas-size">{t('画幅')}</Label>
      {pinned && <span className="roam-canvas-state"><LockKeyhole className="size-3" aria-hidden="true" />{t('已固定')}</span>}
      {busy && <LoaderCircle className="size-3 animate-spin" aria-label={t('正在保存…')} />}
      {pinned && <Button variant="ghost" size="icon-sm" className="ml-auto" aria-label={t('清除画幅固定')} data-tooltip={t('恢复漫游画幅设置')} disabled={busy} onClick={() => void save('')}><X aria-hidden="true" /></Button>}
    </div>
    <div className="roam-canvas-controls">
      <div className="roam-canvas-select">
        <Select value={value || '__follow__'} onValueChange={next => void save(next === '__follow__' ? '' : next)} disabled={!options || busy || !supported || !sizes.length}>
          <SelectTrigger id="roam-canvas-size" className="w-full min-w-0" size="sm" aria-label={t('固定画幅')}><SelectValue /></SelectTrigger>
          <SelectContent className="roam-canvas-options" position="popper" align="start" container={container}>
            <SelectItem value="__follow__">{t('跟随漫游')}</SelectItem>
            {sizes.map((size: any) => <SelectItem key={size.value} value={size.value}>{size.label}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <Button variant="outline" size="sm" disabled={!options || busy || !currentUsable} onClick={() => void save(current)} data-tooltip={current ? tr`固定当前图片的画幅：${current.replace('x', '×')}` : t('图片载入后可固定当前画幅')}><Scan aria-hidden="true" />{t('固定当前')}</Button>
    </div>
    {(!supported || value && !usable(value)) && <p className="hint roam-canvas-note">{t(supported ? '当前生图 API 不支持所选像素尺寸。' : '当前生图 API 不支持像素画幅。')}</p>}
  </section>;
}
