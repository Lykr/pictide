import { t } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { HelpTip } from '../components/actions';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { FormSelect } from '../components/form-select';
import { InputGroup, InputGroupAddon, InputGroupInput } from '../components/ui/input-group';
import { RoamSettingsChoices } from '../components/roam-playback';
import { PreferenceActions } from '../components/preference-actions';
import { backendCapabilities } from '../controllers/backend-controls.mjs';
export function RoamSettings() {
  const app = useApplication(), state = useModel(app.model);
  const roamInput = (key: string) => ({ value: state.roamDraft[key], onChange: (event: React.ChangeEvent<HTMLInputElement>) => app.editRoam({ [key]: event.target.value }) });
  return <form id="roam-form" className="settings-stack" onSubmit={event => { event.preventDefault(); void app.submitRoamSettings(); }}>
<fieldset id="roam-fields" className="settings-stack" disabled={state.roamSaving}>
<div className="form-grid">
<div className="settings-field"><Label htmlFor="roam-backend">{t("生图 API")}</Label><FormSelect id="roam-backend" value={state.roamDraft.backend_id} onValueChange={value => app.editRoam({ backend_id: value })} options={[{ value: "", label: t("自动选择 API") }, ...state.backends.map((item: any) => ({ value: item.id, label: item.name }))]}><option value="">{t("自动选择 API")}</option></FormSelect></div>
</div>
<p id="roam-cloud-note" className="hint" hidden={!backendCapabilities(state.roamDraft.backend_id ? state.backends.find((item: any) => item.id === state.roamDraft.backend_id) : state.backends[0]).cloud}>{t("提示词会发送给此服务；图片和反馈保存在本地。API 使用可能产生费用。")}{' '}{t("首次选择云端 API 会关闭自动预取；再次保存非零预取数量可开启连续生成。")}</p>
<RoamSettingsChoices value={state.roamDraft} onChange={app.editRoam} />
<div className="form-grid">
<div className="settings-field"><Label htmlFor="roam-prefetch-count"><span className="field-caption">{t("预取数量")}<HelpTip text={t("在当前图片后预备的张数；漫游页打开时按需补足，0 关闭自动预取。")} /></span></Label><Input id="roam-prefetch-count" {...roamInput("prefetch_count")} type="number" min="0" max="20" step="1" required /></div>
<div className="settings-field"><Label htmlFor="roam-max-history-images"><span className="field-caption">{t("历史图片数量上限")}<HelpTip text={t("超限时从最早图片处理：未喜欢的永久删除本地图片及提示词 JSON；喜欢的仅从漫游隐藏，喜欢页保留。")} /></span></Label><Input id="roam-max-history-images" {...roamInput("max_history_images")} data-tooltip={t("仅计算当前图片之前的漫游历史；当前、预取与生成页图片不计。0 关闭数量清理。")} type="number" min="0" max="100000" step="1" required /></div>
<div className="settings-field"><Label htmlFor="roam-playback-interval"><span className="field-caption">{t("自动播放")}<HelpTip text={t("每张图片加载完成后开始计时；下一张未就绪时等待。")} /></span></Label><InputGroup><InputGroupInput id="roam-playback-interval" {...roamInput("playback_interval_seconds")} aria-label={t("自动播放间隔（秒）")} type="number" min="1" max="600" step="1" required /><InputGroupAddon align="inline-end">{t("秒")}</InputGroupAddon></InputGroup></div>
<div className="settings-field"><Label htmlFor="roam-candidate-count"><span className="field-caption">{t("候选组合数量")}<HelpTip text={t("标准模式每次准备的完整组合数；强力模式按倍数增加。候选越多通常等待越久。")} /></span></Label><Input id="roam-candidate-count" {...roamInput("candidate_count")} type="number" min="1" max="20" step="1" required /></div>
<div className="settings-field"><Label htmlFor="roam-strong-candidate-multiplier"><span className="field-caption">{t("强力候选倍数")}<HelpTip text={t("强力模式的候选组合数量 = 候选组合数量 × 倍数。只影响新任务。")} /></span></Label><Input id="roam-strong-candidate-multiplier" {...roamInput("strong_candidate_multiplier")} type="number" min="1" max="5" step="1" required /></div>
</div>
</fieldset>
<PreferenceActions />
<div className="dialog-footer"><Button id="roam-save" type="submit" disabled={state.roamSaving}>{t("保存设置")}</Button></div>
</form>;
}
