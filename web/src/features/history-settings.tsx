import { t } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { HelpTip, IconButton } from '../components/actions';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { LoaderCircle, Save } from 'lucide-react';
import { JobHistory } from '../components/job-history';

export function ImageCleanupSettings() {
  const app = useApplication(), state = useModel(app.model);
  return <>
<h2 id="image-cleanup-title" className="flex items-center gap-1 text-sm font-semibold">{t("图片清理")}<HelpTip text={t("到期且未喜欢的本地图片及提示词 JSON 将永久删除。撤回喜欢后保留 24 小时缓冲；任务记录和 ComfyUI 文件保留。")} /></h2>
<form id="history-form" className="settings-stack" aria-labelledby="image-cleanup-title" onSubmit={event => { event.preventDefault(); void app.saveHistory(); }}>
{"\n    "}<fieldset id="history-fields" disabled={state.historyBusy}>
<div className="settings-field"><Label htmlFor="history-retention-days"><span className="field-caption">{t("保留天数")}<HelpTip text={t("从图片入库起计时，默认 1 天；0 关闭过期清理，喜欢的图片保留。")} /></span></Label><Input id="history-retention-days" type="number" min="0" max="3650" step="1" required value={state.historyDraft} onChange={event => app.editHistory(event.target.value)} />
</div>
</fieldset>
<div className="dialog-footer">

<IconButton id="history-save" type="submit" className={`primary [&_svg]:text-current ${state.historyBusy ? '[&_svg]:animate-spin' : ''}`} icon={state.historyBusy ? LoaderCircle : Save} tooltip={t("保存后立即检查；之后在启动、浏览或生成等操作时按需清理。")} label={t("保存图片清理设置")} disabled={state.historyBusy} aria-busy={state.historyBusy} />
</div>
{"\n  "}</form></>;
}

export function HistorySettings() {
  return <JobHistory />;
}
