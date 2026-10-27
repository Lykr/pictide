import { useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useApplication, useModel } from '../shared/application-context';
import { t } from '../i18n/index.mjs';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { FormSelect } from '../components/form-select';
import { IconButton } from '../components/actions';

export function CanvasPools() {
  const service = useApplication().canvasPools, state = useModel(service.model), draft = state.draft;
  useEffect(() => { void service.load(); }, [service]);
  return <form id="canvas-pool-form" className="settings-stack" inert={state.busy} onSubmit={event => { event.preventDefault(); void service.save(); }}>
    <div className="form-grid">
      <div className="settings-field"><div className="settings-field-heading"><Label htmlFor="edit-canvas-pool">{t('已有画幅池')}</Label><IconButton icon={Trash2} label={t('删除画幅池')} size="icon-xs" onClick={service.remove} disabled={draft.id === '__new__'} /></div>
        <FormSelect id="edit-canvas-pool" value={draft.id} onValueChange={service.select} options={[...state.pools.map((pool: any) => ({value: pool.id, label: pool.name})), {value: '__new__', label: t('＋ 添加画幅池')}]} />
      </div>
      <div className="settings-field"><Label htmlFor="canvas-pool-name">{t('画幅池名称')}</Label><Input id="canvas-pool-name" required maxLength={100} value={draft.name} onChange={event => service.edit('name', event.target.value)} /></div>
    </div>
    <p className="hint">{t('保存多组像素宽高，供不同生图 API 复用。漫游时可从中随机抽取。')}</p>
    <div id="canvas-pool-sizes" className="settings-stack">
      {draft.sizes.map((size: any, index: number) => <div key={size.key} data-canvas-size className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] items-end gap-2">
        <div className="settings-field min-w-0"><Label htmlFor={`canvas-width-${size.key}`}>{t('宽度（像素）')}</Label><Input id={`canvas-width-${size.key}`} aria-label={t('第 {index} 组宽度', {index: index + 1})} type="number" min={1} max={16384} step={1} required value={size.width} onChange={event => service.editSize(size.key, 'width', event.target.value)} /></div>
        <span className="pb-2" aria-hidden="true">×</span>
        <div className="settings-field min-w-0"><Label htmlFor={`canvas-height-${size.key}`}>{t('高度（像素）')}</Label><Input id={`canvas-height-${size.key}`} aria-label={t('第 {index} 组高度', {index: index + 1})} type="number" min={1} max={16384} step={1} required value={size.height} onChange={event => service.editSize(size.key, 'height', event.target.value)} /></div>
        <IconButton icon={Trash2} label={t('移除第 {index} 组尺寸', {index: index + 1})} className="mb-0.5" disabled={draft.sizes.length === 1} onClick={() => service.removeSize(size.key)} />
      </div>)}
    </div>
    <div><Button type="button" variant="outline" onClick={service.addSize} disabled={draft.sizes.length >= 64}><Plus aria-hidden="true" />{t('添加尺寸')}</Button></div>
    <div className="dialog-footer"><Button id="save-canvas-pool" type="submit" disabled={!state.dirty || state.busy}>{t('保存画幅池')}</Button></div>
  </form>;
}
