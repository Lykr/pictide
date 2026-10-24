import { NaturalPrompt } from '../components/natural-prompt';
import { t } from '../i18n/index.mjs';
import { useApplication, useModel } from '../shared/application-context';
import { IconButton, HelpTip } from '../components/actions';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { FormSelect } from '../components/form-select';
import { Checkbox } from '../components/ui/checkbox';
import { RefreshCw, Sparkles, CircleSlash, LoaderCircle } from 'lucide-react';
import { backendCapabilities } from '../controllers/backend-controls.mjs';
import { ruleVisibility } from '../controllers/rule-controls.mjs';
import { Disclosure } from '../components/disclosure';
export function GenerationForm() {
  const app = useApplication(), state = useModel(app.model);
  const generation = app.generation, gen = useModel(generation.model), draft = gen.draft;
  const genInput = (key: string) => ({ value: draft[key], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => generation.edit(key, event.target.value) });
  const genSelect = (key: string) => ({ value: draft[key], onValueChange: (value: string) => generation.edit(key, value) });
  const capabilities = backendCapabilities(state.backends.find((item: any) => item.id === draft.backendId));
  const natural = state.backends.find((item: any) => item.id === draft.backendId)?.prompt_type === 'natural_language';
  const rules = ruleVisibility(draft.source, draft.mode, draft.automatic);
  return <div className="generation-form-panel">
{"\n      "}<div className="compose-heading">
<h2>{t("图像生成")}</h2>
</div>
{"\n      "}<form id="generate-form" inert={gen.busy} onSubmit={event => { event.preventDefault(); void generation.submit(); }}>
{"\n        "}<Label>{t("生图 API")}<FormSelect options={state.backends.length ? state.backends.map((item: any) => ({ value: item.id, label: item.name })) : [{ value: "", label: t("请先配置生图 API") }]} id="generate-backend" aria-label={t("生图 API")} {...genSelect("backendId")} required size="sm">
</FormSelect>
</Label>
{"\n        "}<Label>{t("提示词来源")}<FormSelect id="prompt-source" aria-label={t("提示词来源")} {...genSelect("source")} size="sm">
<option value="manual">{t("手动输入")}</option>
<option value="rules">{t("共现候选")}</option>
</FormSelect>
</Label>
<fieldset id="rule-section" className="rule-section" hidden={!rules.rules} disabled={!rules.rules}>
  <div className="rule-primary-fields">
    <div className="rule-field">
      <div className="rule-field-heading"><Label htmlFor="rule-config">{t("生成预设")}</Label><IconButton id="reload-rule-configs" icon={RefreshCw} label={t("刷新生成预设")} size="icon-xs" disabled={gen.loadingPresets} onClick={() => generation.loadRuleConfigs(true)} /></div>
      <FormSelect id="rule-config" {...genSelect("presetId")} required aria-label={t("生成预设")} options={gen.presets.length ? gen.presets.map((item: any) => ({ value: item.id, label: item.name })) : [{ value: "", label: t("请先新建生成预设") }]} />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-mode">{t("抽取模式")}</Label>
      <FormSelect id="rule-mode" {...genSelect("mode")} aria-label={t("抽取模式")}>
        <option value="random_each_run">{t("每次随机")}</option>
        <option value="fixed_seed">{t("固定提示词种子")}</option>
        <option value="sequence">{t("连续序列")}</option>
      </FormSelect>
    </div>
  </div>
  <p id="rule-config-note" className="hint" role="status" hidden={gen.presets.length > 0}>{t("还没有生成预设，请在提示词页新建。")}</p>
  <fieldset id="rule-seed-fields" className="rule-control-grid" hidden={!rules.seed} disabled={!rules.seed}>
    <div className="rule-field">
      <Label htmlFor="rule-seed"><span className="field-caption">{t("提示词种子")}<HelpTip text={t("控制共现标签抽取，与图像种子独立。")} /></span></Label>
      <Input id="rule-seed" {...genInput("ruleSeed")} type="number" min="0" max="9007199254740991" step="1" required />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-seed-control">{t("种子生成后")}</Label>
      <FormSelect id="rule-seed-control" {...genSelect("seedControl")} aria-label={t("种子生成后")} data-tooltip={t("每轮抽取后更新提示词种子，供下一轮使用。")}>
        <option value="fixed">{t("固定")}</option><option value="increment">{t("递增")}</option><option value="decrement">{t("递减")}</option><option value="randomize">{t("随机")}</option>
      </FormSelect>
    </div>
  </fieldset>
  <fieldset id="rule-sequence-fields" className="rule-control-grid" hidden={!rules.sequence} disabled={!rules.sequence}>
    <div className="rule-field">
      <Label htmlFor="sequence-step"><span className="field-caption">{t("帧序号")}<HelpTip text={t("同一提示词种子下按帧衔接，0 为起始帧。")} /></span></Label>
      <Input id="sequence-step" {...genInput("step")} type="number" min="0" max="1000" step="1" required />
    </div>
    <div className="rule-field">
      <Label htmlFor="sequence-control">{t("帧序号生成后")}</Label>
      <FormSelect id="sequence-control" {...genSelect("stepControl")} aria-label={t("帧序号生成后")} data-tooltip={t("每轮抽取后更新帧序号；递增可衔接下一帧。")}>
        <option value="increment">{t("递增")}</option><option value="fixed">{t("固定")}</option><option value="decrement">{t("递减")}</option><option value="randomize">{t("随机")}</option>
      </FormSelect>
    </div>
  </fieldset>
  <Disclosure className="rule-advanced" title={t("搜索设置")}>
    <div className="rule-field"><Label htmlFor="rule-max-steps"><span className="field-caption">{t("搜索上限")}<HelpTip text={t("限制共现搜索步数，适用于所有抽取模式。")} /></span></Label><Input id="rule-max-steps" {...genInput("maxSteps")} type="number" min="1" max="1000000" step="1" required /></div>
  </Disclosure>
  <div className="rule-actions">
    <Label className="checkbox-label auto-prompts"><Checkbox id="auto-prompts" checked={draft.automatic} onCheckedChange={value => generation.edit("automatic", value === true)} />{t("生图前自动抽取")}<HelpTip text={t("开启后每轮重新抽取提示词；手动编辑会关闭此项，改用当前文本。")} /></Label>
    <Button id="generate-prompts" type="button" variant="secondary" size="sm" disabled={gen.busy} onClick={generation.drawPrompts}>{gen.feedback.prompts ? <LoaderCircle className="animate-spin" /> : <Sparkles aria-hidden="true" />}{t("抽取提示词")}</Button>
  </div>
  <p id="rule-generation-note" className="hint" role="status" data-tooltip={t(draft.automatic ? "计数已更新为下次值，当前提示词可直接编辑。" : "抽取报告对应编辑前的结果，重新勾选自动抽取可恢复共现生成。")} hidden={!gen.promptNote}>{gen.promptNote?.()}</p>
  <Disclosure id="rule-report" className="rule-report" hidden={!gen.report} title={t("抽取报告")}><pre id="rule-report-content">{JSON.stringify(gen.report, null, 2)}</pre></Disclosure>
</fieldset>
{"\n        "}<Label>{t(natural ? "正向标签" : "正向提示词")}<Textarea id="positive" {...genInput("positive")} rows={8} placeholder={t("描述你想看到的画面…")} required={rules.positiveRequired}>
</Textarea>
</Label>
{"\n        "}<Label id="negative-field" hidden={!natural && capabilities.cloud && !capabilities.negative_prompt}>{t(natural ? "负向标签" : "负向提示词")}<Textarea id="negative" {...genInput("negative")} rows={4} placeholder={t("不希望出现的内容（可选）")} disabled={!natural && capabilities.cloud && !capabilities.negative_prompt}>
</Textarea>
<small id="negative-binding-note" hidden={natural || !state.backends.length || capabilities.negative_prompt || capabilities.cloud}>{t("当前生图 API 未绑定负向输入，请保持为空，或在生图 API 设置中绑定。")}</small>
</Label>
<NaturalPrompt prompt={gen.rendered} />
<p id="generation-capability-note" className="hint" hidden={!capabilities.cloud || natural}>{t("此生图 API 不支持负向提示词和图像种子；本次仅发送正向提示词，原输入保留。候选预设中的负向词仍需移除。")}</p>
<p id="generation-cloud-note" className="hint" hidden={!capabilities.cloud}>{t("提示词会发送给此服务；图片和反馈保存在本地。API 使用可能产生费用。")}</p>
{"\n        "}<div className="generation-plan-fields"><Label id="seed-field" hidden={capabilities.cloud && !capabilities.seed}><span className="field-caption">{t("图像种子")}<HelpTip id="seed-note" text={t(capabilities.seed ? "-1 每个任务随机；非负值按任务递增，跨轮延续。实际种子随图片保存。" : "未绑定种子输入，将使用工作流自身的种子设置。")} /></span><Input id="seed" {...genInput("seed")} type="number" min="-1" max="9007199254740991" step="1" disabled={!capabilities.seed} />

</Label>
<div className="form-grid">
<Label htmlFor="generation-count"><span className="field-caption">{t("每次数量")}<HelpTip text={t("每轮提交的生成任务数，同轮共用提示词；单个任务可能输出多张图片。")} /></span><Input id="generation-count" {...genInput("count")} type="number" min="1" max="10" step="1" required /></Label>
<Label htmlFor="generation-repetitions"><span className="field-caption">{t("生成次数")}<HelpTip text={t("整批生成的轮数；每轮包含左侧设置的生成任务数。")} /></span><Input id="generation-repetitions" {...genInput("repetitions")} type="number" min="1" max="10" step="1" required /></Label>
</div></div>
{"\n        "}<div className="generation-actions"><Button id="generate" aria-busy={gen.busy} className="primary" type="submit" variant="default" data-tooltip={t("提交整批任务；关闭网页不会取消已提交任务。")} disabled={gen.busy || !state.backends.length}>{gen.feedback.submit ? <LoaderCircle className="animate-spin" /> : <Sparkles aria-hidden="true" />}{t("生成图片")}</Button>
<Button id="cancel-pending" type="button" variant="outline" data-tooltip={t("取消生成页全部待执行任务；保留已开始的任务和漫游预取。")} disabled={gen.busy} onClick={generation.cancelPending}>{gen.feedback.cancel ? <LoaderCircle className="animate-spin" /> : <CircleSlash aria-hidden="true" />}{t("取消待执行任务")}</Button></div>

{"\n      "}</form>
</div>;
}
