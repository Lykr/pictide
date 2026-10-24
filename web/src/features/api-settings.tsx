import { t } from '../i18n/index.mjs';
import { useMemo, useRef } from 'react';
import { useApplication, useModel } from '../shared/application-context';
import { IconButton, HelpTip } from '../components/actions';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { FormSelect } from '../components/form-select';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '../components/ui/collapsible';
import { RefreshCw, SlidersHorizontal, Trash2, ChevronRight, Download } from 'lucide-react';
import { uiTarget } from '../shared/ui-targets';
import { WorkflowPicker } from '../components/workflow-picker';
import { WorkflowNodeFields, WorkflowOutputs } from '../components/workflow-node-fields';
export function ApiSettings() {
  const app = useApplication(), state = useModel(app.model);
  const api = app.backendSettings, settings = useModel(api.model), apiDraft = settings.draft;
  const llms = useModel(app.promptSettings.model);
  const nodeParametersOpen = settings.nodeParametersOpen, setNodeParametersOpen = api.setNodeParametersExpanded;
  const file = useRef<HTMLInputElement>(null);
  const targets = useMemo(() => Object.fromEntries(['api.form', 'api.test', 'api.save'].map(key => [key, uiTarget(key)])), []);
  const apiInput = (key: string) => ({ value: apiDraft[key], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => api.edit(key, event.target.value) });
  const apiSelect = (key: string) => ({ value: apiDraft[key], onValueChange: (value: string) => api.edit(key, value) });
  const cloud = apiDraft.kind !== 'comfyui', custom = apiDraft.workflowMode !== 'default';
  return <><form id="settings-form" ref={targets["api.form"]} inert={settings.pending.saving} onInvalidCapture={event => {
    const field = event.target as HTMLInputElement;
    if (field.closest('#node-parameter-fields')) {
      event.preventDefault();
      setNodeParametersOpen(true);
      requestAnimationFrame(() => field.focus());
    }
  }} onSubmit={event => { event.preventDefault(); void api.save(); }}>
<div className="form-grid">
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="edit-backend">{t("已有 API")}</Label><IconButton id="delete-backend" icon={Trash2} label={t("删除 API 配置")} size="icon-xs" onClick={api.deleteBackend} disabled={apiDraft.selectedId === "__new__"} /></div>
<FormSelect id="edit-backend" {...apiSelect("selectedId")} options={[...state.backends.map((item: any) => ({ value: item.id, label: item.name })), { value: "__new__", label: t("＋ 添加 API") }]} />
</div>
<div className="settings-field"><Label htmlFor="backend-name">{t("API 名称")}</Label><Input id="backend-name" {...apiInput("name")} required placeholder={t("本机 ComfyUI")} /></div>
<div className="settings-field"><Label htmlFor="backend-kind">{t("API 类型")}</Label><FormSelect id="backend-kind" {...apiSelect("kind")}><option value="comfyui">ComfyUI</option><option value="openai">OpenAI Images</option><option value="gemini">Gemini</option></FormSelect></div>
<div className="settings-field"><Label htmlFor="backend-prompt-type">{t("提示词类型")}</Label><FormSelect id="backend-prompt-type" {...apiSelect("prompt_type")} options={[{ value: "danbooru", label: "Danbooru" }, { value: "natural_language", label: t("自然语言") }]} /></div>
<div className="settings-field"><Label htmlFor="backend-url">{t("API 地址")}</Label><Input id="backend-url" {...apiInput("url")} type="url" required /></div>
</div>
{apiDraft.prompt_type === 'natural_language' && <div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="backend-llm">LLM API</Label><Button type="button" variant="link" onClick={() => app.setSettingsSection('llm')}>{t('管理 LLM API')}</Button></div>
<FormSelect id="backend-llm" value={apiDraft.llm_id || ''} onValueChange={value => api.edit('llm_id',value)} options={[{value:'',label:t('选择 LLM API')}, ...llms.connections.map((row: any) => ({value:row.id,label:row.name}))]} />
</div>}
<div className="settings-field">
<Label htmlFor="backend-key"><span className="field-caption">API Key<HelpTip id="key-state" text={t("可选。保留遮罩不修改密钥，清空并保存可移除。")} /></span></Label>
<Input id="backend-key" {...apiInput("key")} type="password" autoComplete="new-password" onFocus={event => { if (settings.hasSavedApiKey) event.target.select(); }} />
</div>
<fieldset id="cloud-backend" className="settings-stack" hidden={!cloud} disabled={!cloud}>
<div className="settings-field"><Label htmlFor="backend-model">{t("模型")}</Label><Input id="backend-model" {...apiInput("model")} required placeholder={t("填写服务支持的生图模型 ID")} /><p className="hint">{t("请填写服务支持的生图模型 ID；可选参数留空时使用服务默认值。")}</p></div>
<fieldset id="openai-options" className="form-grid" hidden={apiDraft.kind !== "openai"} disabled={apiDraft.kind !== "openai"}>
<div className="settings-field"><Label htmlFor="backend-size">{t("图片尺寸（可选）")}</Label><Input id="backend-size" {...apiInput("size")} placeholder="1024x1024" /></div>
<div className="settings-field"><Label htmlFor="backend-quality">{t("图片质量（可选）")}</Label><Input id="backend-quality" {...apiInput("quality")} placeholder="auto" /></div>
</fieldset>
<fieldset id="gemini-options" className="form-grid" hidden={apiDraft.kind !== "gemini"} disabled={apiDraft.kind !== "gemini"}>
<div className="settings-field"><Label htmlFor="backend-aspect-ratio">{t("宽高比（可选）")}</Label><Input id="backend-aspect-ratio" {...apiInput("aspect_ratio")} placeholder="1:1" /></div>
<div className="settings-field"><Label htmlFor="backend-image-size">{t("图片分辨率（可选）")}</Label><Input id="backend-image-size" {...apiInput("image_size")} placeholder="1K" /></div>
</fieldset>
<p className="hint">{t("提示词会发送给此服务；图片和反馈保存在本地。API 使用可能产生费用。")}</p>
<p className="hint">{t("测试连接只读取服务信息，不会生成图片。")}</p>
</fieldset>
<div id="workflow-picker-field" className="settings-field" hidden={cloud}>
<div className="settings-field-heading"><Label htmlFor="workflow-name--control">{t("工作流")}</Label><div className="workflow-actions">
<IconButton id="delete-workflow" icon={Trash2} label={t("删除工作流")} size="icon-xs" onClick={api.deleteWorkflow} disabled={!state.workflowId || settings.pending.saving} />
<IconButton id="reload-workflows" icon={RefreshCw} label={t("刷新工作流列表")} size="icon-xs" onClick={api.reloadWorkflows} disabled={settings.pending.library} />
</div></div>
<WorkflowPicker mode={apiDraft.workflowMode} name={apiDraft.workflowName} options={[{ value: 'default', text: t('默认文生图') }, ...state.workflows.map((item: any) => ({ value: `saved:${item.id}`, text: item.name })), { value: 'custom', text: t('自定义 API 工作流') }]} disabled={settings.pending.workflow} onModeChange={value => api.edit('workflowMode', value)} onNameChange={value => api.edit('workflowName', value)} />
</div>
<section id="default-workflow" hidden={cloud || custom}>
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="default-checkpoint"><span className="field-caption">{t("模型")}<HelpTip text={t("从配置的 ComfyUI 读取模型，留空时自动选择第一个可用模型。")} /></span></Label><IconButton id="load-models" icon={RefreshCw} label={t("读取 API 模型")} size="icon-xs" onClick={api.loadModels} disabled={settings.pending.models} /></div>
<FormSelect id="default-checkpoint" {...apiSelect("checkpoint")} options={[{ value: "", label: t("自动选择第一个可用模型") }, ...settings.models.map((value: string) => ({ value, label: value }))]}><option value="">{t("自动选择第一个可用模型")}</option></FormSelect>
</div>
<Button id="edit-default-parameters" type="button" className="quiet" variant="outline" data-tooltip={t("将默认工作流展开为自定义草稿，编辑采样、尺寸等节点参数")} onClick={api.editDefaultParameters} disabled={settings.pending.template}><SlidersHorizontal aria-hidden="true" />{t("节点参数")}</Button>
</section>
<fieldset id="custom-workflow" hidden={cloud || !custom} disabled={cloud || !custom}>
<Collapsible id="node-parameters" className="node-parameters" data-editor-mode={settings.editorMode} open={nodeParametersOpen} onOpenChange={setNodeParametersOpen}>
<div className="node-parameters-heading"><h3><CollapsibleTrigger asChild><Button id="toggle-node-parameters" type="button" variant="ghost" size="sm" className="justify-start gap-2 rounded-none bg-transparent px-0 font-semibold hover:bg-transparent aria-expanded:bg-transparent dark:hover:bg-transparent"><ChevronRight className={nodeParametersOpen ? "rotate-90" : ""} aria-hidden="true" />{t("节点参数")}</Button></CollapsibleTrigger></h3><div className="node-parameters-actions">
<Button id="toggle-workflow-json" type="button" variant="ghost" size="sm" aria-controls="node-parameter-fields workflow-json-editor" aria-label={t("编辑 API 工作流 JSON")} data-tooltip={t("编辑 API 工作流 JSON")} aria-pressed={settings.editorMode === "json"} onClick={() => api.setWorkflowPanelMode(settings.editorMode === "json" ? "parameters" : "json")}>JSON</Button>
<IconButton icon={Download} label={t("导入 ComfyUI API 工作流 JSON")} onClick={() => file.current?.click()} />
<input id="workflow-file" type="file" accept=".json,application/json" hidden ref={file} onChange={event => { void api.importWorkflow(event.target.files?.[0]); event.target.value = ""; }} />
</div></div>
<CollapsibleContent forceMount hidden={!nodeParametersOpen}>
<WorkflowNodeFields />
<div id="workflow-json-editor" hidden={settings.editorMode !== "json"}><Label htmlFor="workflow-json" className="sr-only">{t("API 工作流 JSON")}</Label><Textarea id="workflow-json" {...apiInput("workflowJson")} className="code-input" rows={7} placeholder={'{"6":{"class_type":"CLIPTextEncode","inputs":{"text":"…"}}}'} spellCheck={false} aria-invalid={!settings.workflowValid} /></div>
</CollapsibleContent>
</Collapsible>
<div id="workflow-error" className={`validation${settings.workflowValid ? " valid" : ""}`} role="status">{settings.workflowMessage?.()}</div>
<div className="form-grid workflow-bindings">
<div className="binding-inputs">
<div className="settings-field"><Label htmlFor="binding-positive">{t("正向提示词输入")}</Label><FormSelect id="binding-positive" {...apiSelect("positive")} options={[{ value: "", label: t("选择正向 text 输入") }, ...settings.textInputs]}><option value="">{t("先导入工作流")}</option></FormSelect></div>
<div className="settings-field"><Label htmlFor="binding-negative">{t("负向提示词输入")}</Label><FormSelect id="binding-negative" {...apiSelect("negative")} options={[{ value: "", label: t("选择负向 text 输入") }, ...settings.textInputs]}><option value="">{t("选择负向 text 输入")}</option></FormSelect></div>
<div className="settings-field"><Label htmlFor="binding-seed">{t("图像种子输入（可选）")}</Label><FormSelect id="binding-seed" {...apiSelect("seed")} options={[{ value: "", label: t("不绑定") }, ...settings.seedInputs]}><option value="">{t("不绑定")}</option></FormSelect></div>
</div>
<div className="settings-field"><Label htmlFor="output-nodes"><span className="field-caption">{t("输出节点")}<HelpTip text={t("可多选；留空时使用生图 API 返回的图像输出。")} /></span></Label><WorkflowOutputs /></div>
</div>
</fieldset>
<div className="dialog-footer"><Button id="test-backend" ref={targets["api.test"]} type="button" className="quiet" variant="outline" onClick={api.testBackend} disabled={settings.pending.test}>{t("测试连接")}</Button><Button id="save-backend" ref={targets["api.save"]} type="submit" className="primary" variant="default" disabled={settings.pending.saving}>{t("保存 API")}</Button></div>
</form></>;
}
