import { t } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { HelpTip } from '../components/actions';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../components/ui/collapsible';
import { ChevronRight } from 'lucide-react';
import { JobHistory } from '../components/job-history';
export function HistorySettings() {
  const app = useApplication(), state = useModel(app.model);
  return <><Collapsible>
<CollapsibleTrigger asChild><Button type="button" variant="ghost" size="sm" className="group gap-2 rounded-none bg-transparent px-0 font-semibold hover:bg-transparent aria-expanded:bg-transparent dark:hover:bg-transparent"><ChevronRight className="transition-transform group-data-[state=open]:rotate-90" aria-hidden="true" />{t("图片清理")}</Button></CollapsibleTrigger>
<CollapsibleContent forceMount className="pt-4 data-[state=closed]:hidden"><form id="history-form" className="settings-stack" onSubmit={event => { event.preventDefault(); void app.saveHistory(); }}>
{"\n    "}<fieldset id="history-fields" disabled={state.historyBusy}>
<div className="settings-field"><Label htmlFor="history-retention-days"><span className="field-caption">{t("保留天数")}<HelpTip text={t("从图片入库起计时，默认 1 天；0 关闭过期清理，喜欢的图片保留。")} /></span></Label><Input id="history-retention-days" type="number" min="0" max="3650" step="1" required value={state.historyDraft} onChange={event => app.editHistory(event.target.value)} />
</div>
</fieldset>
{"\n    "}<p className="hint retention-warning">{t("到期且未喜欢的本地图片及提示词 JSON 将永久删除。")}<HelpTip text={t("取消喜欢后，已过期图片也会被清理。任务记录和 ComfyUI 文件保留。")} /></p>
{"\n    "}
<div className="dialog-footer">

<Button id="history-save" type="submit" className="primary" variant="default" data-tooltip={t("保存后立即检查；之后在启动、浏览或生成等操作时按需清理。")} disabled={state.historyBusy}>{t("保存设置")}</Button>
</div>
{"\n  "}</form></CollapsibleContent></Collapsible>
<JobHistory /></>;
}
