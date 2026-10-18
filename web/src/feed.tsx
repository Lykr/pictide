import { t, tr } from './i18n/index.mjs';
import { useState } from "react";
import { EditorWorkspace } from "./editor";
import { GeneratedResults } from "./components/generated-results";
import { JobPageControls } from "./components/page-controls";
import { GeneralSettings } from "./components/general-settings";
import { PreferenceActions } from "./components/preference-actions";
import { ImageInfo } from "./components/image-info";
import { RoamPlaybackButton, RoamOptions, RoamSettingsChoices } from "./components/roam-playback";
import { ArrowLeft, ArrowRight, Eye, EyeOff, FolderOpen, Heart, History, Image, ListFilter, LoaderCircle, Maximize, Minimize, RefreshCw, Settings, Settings2, Compass, SlidersHorizontal, Sparkles, CircleSlash, Trash2, Download, ThumbsDown, ChevronRight } from "lucide-react";
import { IconButton, HelpTip } from "./components/actions";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./components/ui/input-group";
import { Textarea } from "./components/ui/textarea";
import { Label } from "./components/ui/label";
import { Toggle } from "./components/ui/toggle";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "./components/ui/collapsible";
import { nativeSelectClassName, NativeSelect } from "./components/ui/native-select";
import "./styles/theme.css";
import "./styles/feed.css";

// Mount once; the established controller owns form values and dynamic regions.
export function FeedShell({ themeError = "" }: { themeError?: string }) {
  const [privacyBlur, setPrivacyBlur] = useState(true);
  const [nodeParametersOpen, setNodeParametersOpen] = useState(false);
  const privacyLabel = privacyBlur ? t("关闭毛玻璃，显示图片") : t("开启毛玻璃，模糊图片");
  return <div className={`feed-page${privacyBlur ? " privacy-blurred" : ""}`}>
{"\n  "}<header className="topbar">
<a className="brand" href="/" aria-label={t("Pictide 图片工作台")}>
<span className="brand-mark" aria-hidden="true"><img src={`${import.meta.env.BASE_URL}icons/pictide.svg?v=wave-v1`} alt="" /></span>
<div>
<strong>Pictide</strong>

</div>
</a>
<div className="top-actions">
<span id="backend-status" className="status" role="status">{t("未配置")}</span>
</div>
</header>
{"\n  "}<div id="app-workspace" className="workspace">
{"\n    "}<nav className="sidebar" aria-label={t("视图")}>
<Button className="nav active" data-view="feed" variant="ghost" type="button"><Compass aria-hidden="true" />{t("漫游")}</Button>
<Button className="nav" data-view="generate" variant="ghost" type="button"><Sparkles aria-hidden="true" />{t("生成")}</Button>
<Button className="nav" data-view="liked" variant="ghost" type="button"><Heart aria-hidden="true" />{t("喜欢")}</Button>
<Button className="nav" data-view="prompts" variant="ghost" type="button"><ListFilter aria-hidden="true" />{t("提示词")}</Button>
<div className="sidebar-foot">
<Button className="nav" data-view="settings" variant="ghost" type="button"><Settings aria-hidden="true" />{t("设置")}</Button>
</div>
</nav>
{"\n    "}<main id="feed-main" className="main workspace-content">
{"\n      "}<div className="section-heading">
<div className="view-heading">
<h1 id="view-title">{t("漫游")}</h1>
<span id="roam-loading" className="roam-loading" role="status" hidden><LoaderCircle aria-hidden="true" /><span id="roam-loading-label" className="sr-only">{t("正在生成漫游图片")}</span></span>
</div>
<div className="roam-heading-actions">
<span id="liked-privacy-controls" hidden />
<span id="roam-options-controls" className="inline-flex items-center gap-1"><RoamPlaybackButton /><Toggle id="roam-privacy" size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={tr`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={tr`${privacyLabel} · 空格。刷新页面后默认开启。`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle><IconButton id="roam-immersive" icon={Maximize} label={t("进入沉浸模式")} aria-controls="image-card" aria-pressed="false" disabled onClick={() => document.dispatchEvent(new Event("pictide:roam-options-close"))} /><RoamOptions /></span>
</div>
</div>
{"\n      "}<div id="notice" role="status" className="notice" hidden>
</div>
{"\n      "}<section id="gallery-view" className="gallery-view">
{"\n        "}<div id="empty-state" className="empty">
<div className="empty-mark"><Image aria-hidden="true" /></div>
<h2 id="empty-title">{t("从第一张图片开始")}</h2>
<p id="empty-description">{t("连接 ComfyUI，开始生成。")}</p>
<Button id="empty-settings" className="primary" variant="default" type="button">{t("配置后端")}</Button>
<Button id="empty-generate" variant="default" type="button" hidden>{t("开始生成")}</Button>
</div>
{"\n        "}<Card id="image-card" className="image-card gap-0 py-0" tabIndex={-1} aria-label={t("图片浏览")} hidden>
<div className="immersive-actions" role="toolbar" aria-label={t("沉浸模式设置")}>
<RoamPlaybackButton immersive />
<Toggle id="roam-immersive-privacy" size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={tr`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={tr`${privacyLabel} · 空格`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle>
<IconButton id="roam-immersive-exit" icon={Minimize} label={t("退出沉浸模式")} hidden />
</div>
<div className="image-stage">
<img id="main-image" alt={t("生成的图片")} draggable={false} />
<div id="image-error" className="image-error" hidden>{t("图片读取失败，请检查服务与文件是否可用。")}</div>
</div>
<div className="image-toolbar">
<div className="image-meta">
<strong id="image-index">
</strong>
<span id="image-date">
</span>
</div>
<div className="image-navigation">
<IconButton id="previous" icon={ArrowLeft} label={t("上一张较旧图片 · ←")} variant="ghost" type="button" />
<IconButton id="like" icon={Heart} label={t("喜欢 · ↑")} variant="ghost" type="button" className="feedback" aria-pressed="false" />
<IconButton id="dislike" icon={ThumbsDown} label={t("不喜欢 · ↓")} variant="ghost" type="button" className="feedback" aria-pressed="false" />
<IconButton id="next" icon={ArrowRight} label={t("下一张较新图片 · →")} variant="ghost" type="button" />
</div>
<div className="image-info">
<ImageInfo />
</div>
</div>
</Card>
{"\n        "}<div className="load-more-row">
<Button id="load-more" className="quiet" hidden variant="outline" type="button">{t("加载更早图片")}</Button>
</div>
{"\n      "}</section>
{"\n      "}<section id="liked-view" hidden><GeneratedResults collection="liked" /></section>

{"\n    "}<section id="compose" className="compose" hidden>
<div className="generation-form-panel">
{"\n      "}<div className="compose-heading">
<h2>{t("图像生成")}</h2>
</div>
{"\n      "}<form id="generate-form">
{"\n        "}<Label>{t("后端")}<NativeSelect id="generate-backend" required size="sm">
</NativeSelect>
</Label>
{"\n        "}<Label>{t("提示词来源")}<NativeSelect id="prompt-source" size="sm">
<option value="manual">{t("手动输入")}</option>
<option value="rules">{t("共现候选")}</option>
</NativeSelect>
</Label>
<fieldset id="rule-section" className="rule-section" hidden disabled>
  <div className="rule-primary-fields">
    <div className="rule-field">
      <div className="rule-field-heading"><Label htmlFor="rule-config--control">{t("生成预设")}</Label><IconButton id="reload-rule-configs" icon={RefreshCw} label={t("刷新生成预设")} size="icon-xs" /></div>
      <NativeSelect id="rule-config" required aria-label={t("生成预设")} />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-mode--control">{t("抽取模式")}</Label>
      <NativeSelect id="rule-mode" aria-label={t("抽取模式")}>
        <option value="random_each_run">{t("每次随机")}</option>
        <option value="fixed_seed">{t("固定提示词种子")}</option>
        <option value="sequence">{t("连续序列")}</option>
      </NativeSelect>
    </div>
  </div>
  <p id="rule-config-note" className="hint" role="status" hidden />
  <fieldset id="rule-seed-fields" className="rule-control-grid" hidden disabled>
    <div className="rule-field">
      <Label htmlFor="rule-seed"><span className="field-caption">{t("提示词种子")}<HelpTip text={t("控制共现标签抽取，与图像种子独立。")} /></span></Label>
      <Input id="rule-seed" type="number" min="0" max="9007199254740991" step="1" required defaultValue="0" />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-seed-control--control">{t("种子生成后")}</Label>
      <NativeSelect id="rule-seed-control" aria-label={t("种子生成后")} data-tooltip={t("每轮抽取后更新提示词种子，供下一轮使用。")}>
        <option value="fixed">{t("固定")}</option><option value="increment">{t("递增")}</option><option value="decrement">{t("递减")}</option><option value="randomize">{t("随机")}</option>
      </NativeSelect>
    </div>
  </fieldset>
  <fieldset id="rule-sequence-fields" className="rule-control-grid" hidden disabled>
    <div className="rule-field">
      <Label htmlFor="sequence-step"><span className="field-caption">{t("帧序号")}<HelpTip text={t("同一提示词种子下按帧衔接，0 为起始帧。")} /></span></Label>
      <Input id="sequence-step" type="number" min="0" max="1000" step="1" required defaultValue="0" />
    </div>
    <div className="rule-field">
      <Label htmlFor="sequence-control--control">{t("帧序号生成后")}</Label>
      <NativeSelect id="sequence-control" aria-label={t("帧序号生成后")} data-tooltip={t("每轮抽取后更新帧序号；递增可衔接下一帧。")}>
        <option value="increment">{t("递增")}</option><option value="fixed">{t("固定")}</option><option value="decrement">{t("递减")}</option><option value="randomize">{t("随机")}</option>
      </NativeSelect>
    </div>
  </fieldset>
  <details className="rule-advanced">
    <summary>{t("搜索设置")}</summary>
    <div className="rule-field"><Label htmlFor="rule-max-steps"><span className="field-caption">{t("搜索上限")}<HelpTip text={t("限制共现搜索步数，适用于所有抽取模式。")} /></span></Label><Input id="rule-max-steps" type="number" min="1" max="1000000" step="1" required defaultValue="100" /></div>
  </details>
  <div className="rule-actions">
    <Label className="checkbox-label auto-prompts"><input id="auto-prompts" type="checkbox" defaultChecked />{t("生图前自动抽取")}<HelpTip text={t("开启后每轮重新抽取提示词；手动编辑会关闭此项，改用当前文本。")} /></Label>
    <Button id="generate-prompts" type="button" variant="secondary" size="sm"><Sparkles aria-hidden="true" />{t("抽取提示词")}</Button>
  </div>
  <p id="rule-generation-note" className="hint" role="status" hidden />
  <details id="rule-report" className="rule-report" hidden><summary>{t("抽取报告")}</summary><pre id="rule-report-content" /></details>
</fieldset>
{"\n        "}<Label>{t("正向提示词")}<Textarea id="positive" rows={8} placeholder={t("描述你想看到的画面…")} required>
</Textarea>
</Label>
{"\n        "}<Label>{t("负向提示词")}<Textarea id="negative" rows={4} placeholder={t("不希望出现的内容（可选）")}>
</Textarea>
<small id="negative-binding-note" hidden>{t("当前后端未绑定负向输入，请保持为空，或在后端设置中绑定。")}</small>
</Label>
{"\n        "}<div className="generation-plan-fields"><Label><span className="field-caption">{t("图像种子")}<HelpTip id="seed-note" text={t("-1 每个任务随机；非负值按任务递增，跨轮延续。实际种子随图片保存。")} /></span><Input id="seed" type="number" min="-1" max="9007199254740991" step="1" defaultValue="-1" />

</Label>
<div className="form-grid">
<Label htmlFor="generation-count"><span className="field-caption">{t("每次数量")}<HelpTip text={t("每轮执行的工作流次数，同轮共用提示词；单次工作流可能输出多张图片。")} /></span><Input id="generation-count" type="number" min="1" max="10" step="1" defaultValue="1" required /></Label>
<Label htmlFor="generation-repetitions"><span className="field-caption">{t("生成次数")}<HelpTip text={t("整批生成的轮数；每轮包含左侧设置的工作流次数。")} /></span><Input id="generation-repetitions" type="number" min="1" max="10" step="1" defaultValue="1" required /></Label>
</div></div>
{"\n        "}<div className="generation-actions"><Button id="generate" className="primary" type="submit" variant="default" data-tooltip={t("提交整批任务；关闭网页不会取消已提交任务。")}><Sparkles aria-hidden="true" />{t("生成图片")}</Button>
<Button id="cancel-pending" type="button" variant="outline" data-tooltip={t("取消生成页全部待执行任务；保留已开始的任务和漫游预取。")}><CircleSlash aria-hidden="true" />{t("取消待执行任务")}</Button></div>

{"\n      "}</form>
</div>
<GeneratedResults />
{"\n    "}</section>
<section id="settings-view" className="settings-view" hidden>
<nav className="settings-navigation" aria-label={t("设置分类")}>
<Button data-settings-section="general" variant="ghost" type="button"><Settings2 aria-hidden="true" />{t("通用")}</Button>
<Button data-settings-section="roam" variant="ghost" type="button"><Compass aria-hidden="true" />{t("漫游")}</Button>
<Button data-settings-section="backend" variant="ghost" type="button"><SlidersHorizontal aria-hidden="true" />{t("后端")}</Button>
<Button data-settings-section="history" variant="ghost" type="button"><History aria-hidden="true" />{t("历史")}</Button>
</nav>
<div className="settings-content">
<section id="settings-general" className="settings-category space-y-6"><GeneralSettings initialError={themeError} /><section className="settings-data-section" aria-label={t("数据位置")}>
<h2>{t("数据位置")}</h2>
<dl className="data-locations"><div><dt>{t("数据目录")}</dt><dd id="data-directory">{t("读取中…")}</dd></div><div><dt>{t("数据库")}</dt><dd id="database-path">{t("读取中…")}</dd></div></dl>
</section></section>
<section id="settings-backend" className="settings-category"><form id="settings-form">
<div className="form-grid">
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="edit-backend">{t("已有后端")}</Label><IconButton id="delete-backend" icon={Trash2} label={t("删除后端配置")} size="icon-xs" disabled /></div>
<NativeSelect id="edit-backend" />
</div>
<div className="settings-field"><Label htmlFor="backend-name">{t("后端名称")}</Label><Input id="backend-name" required placeholder={t("本机 ComfyUI")} /></div>
<div className="settings-field"><Label htmlFor="backend-kind">{t("后端类型")}</Label><NativeSelect id="backend-kind"><option value="comfyui">ComfyUI</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="backend-url">{t("API 地址")}</Label><Input id="backend-url" type="url" required defaultValue="http://127.0.0.1:8188" /></div>
</div>
<div className="settings-field">
<Label htmlFor="backend-key"><span className="field-caption">API Key<HelpTip id="key-state" text={t("可选。保留遮罩不修改密钥，清空并保存可移除。")} /></span></Label>
<Input id="backend-key" type="password" autoComplete="new-password" />
</div>
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="workflow-name--control">{t("工作流")}</Label><div className="workflow-actions">
<IconButton id="delete-workflow" icon={Trash2} label={t("删除工作流")} size="icon-xs" disabled />
<IconButton id="reload-workflows" icon={RefreshCw} label={t("刷新工作流列表")} size="icon-xs" />
</div></div>
<div data-workflow-picker="">
<select id="workflow-mode" aria-hidden="true" tabIndex={-1}><option value="default">{t("默认文生图")}</option><option value="custom">{t("自定义 API 工作流")}</option></select>
<input id="workflow-name" aria-hidden="true" tabIndex={-1} maxLength={120} />
</div>
</div>
<section id="default-workflow">
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="default-checkpoint"><span className="field-caption">{t("模型")}<HelpTip text={t("从配置的 ComfyUI 读取模型，留空时自动选择第一个可用模型。")} /></span></Label><IconButton id="load-models" icon={RefreshCw} label={t("读取后端模型")} size="icon-xs" /></div>
<NativeSelect id="default-checkpoint"><option value="">{t("自动选择第一个可用模型")}</option></NativeSelect>
</div>
<p id="model-note" className="hint" role="status" hidden />
<Button id="edit-default-parameters" type="button" className="quiet" variant="outline" data-tooltip={t("将默认工作流展开为自定义草稿，编辑采样、尺寸等节点参数")}><SlidersHorizontal aria-hidden="true" />{t("节点参数")}</Button>
</section>
<fieldset id="custom-workflow" hidden disabled>
<Collapsible id="node-parameters" className="node-parameters" data-editor-mode="parameters" open={nodeParametersOpen} onOpenChange={setNodeParametersOpen}>
<div className="node-parameters-heading"><h3><CollapsibleTrigger asChild><Button id="toggle-node-parameters" type="button" variant="ghost" size="sm" className="justify-start gap-2 rounded-none bg-transparent px-0 font-semibold hover:bg-transparent aria-expanded:bg-transparent dark:hover:bg-transparent"><ChevronRight className={nodeParametersOpen ? "rotate-90" : ""} aria-hidden="true" />{t("节点参数")}</Button></CollapsibleTrigger></h3><div className="node-parameters-actions">
<Button id="toggle-workflow-json" type="button" variant="ghost" size="sm" aria-pressed="false" aria-controls="node-parameter-fields workflow-json-editor" aria-label={t("编辑 API 工作流 JSON")} data-tooltip={t("编辑 API 工作流 JSON")}>JSON</Button>
<IconButton icon={Download} label={t("导入 ComfyUI API 工作流 JSON")} onClick={() => document.getElementById("workflow-file")?.click()} />
<input id="workflow-file" type="file" accept=".json,application/json" hidden />
</div></div>
<CollapsibleContent forceMount hidden={!nodeParametersOpen}>
<div id="node-parameter-fields" />
<div id="workflow-json-editor" hidden><Label htmlFor="workflow-json" className="sr-only">{t("API 工作流 JSON")}</Label><Textarea id="workflow-json" className="code-input" rows={7} placeholder={'{"6":{"class_type":"CLIPTextEncode","inputs":{"text":"…"}}}'} spellCheck={false} /></div>
</CollapsibleContent>
</Collapsible>
<div id="workflow-error" className="validation" role="status" />
<div className="form-grid workflow-bindings">
<div className="binding-inputs">
<div className="settings-field"><Label htmlFor="binding-positive">{t("正向提示词输入")}</Label><NativeSelect id="binding-positive"><option value="">{t("先导入工作流")}</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="binding-negative">{t("负向提示词输入")}</Label><NativeSelect id="binding-negative"><option value="">{t("选择负向 text 输入")}</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="binding-seed">{t("图像种子输入（可选）")}</Label><NativeSelect id="binding-seed"><option value="">{t("不绑定")}</option></NativeSelect></div>
</div>
<div className="settings-field"><Label htmlFor="output-nodes"><span className="field-caption">{t("输出节点")}<HelpTip text={t("可多选；留空时使用后端返回的图像输出。")} /></span></Label><select id="output-nodes" data-slot="native-select" className={nativeSelectClassName} multiple size={3} /></div>
</div>
</fieldset>
<div id="settings-result" className="notice" role="status" hidden />
<div className="dialog-footer"><Button id="test-backend" type="button" className="quiet" variant="outline">{t("测试连接")}</Button><Button id="save-backend" type="submit" className="primary" variant="default">{t("保存后端")}</Button></div>
</form></section>
<section id="settings-roam" className="settings-category" hidden><form id="roam-form" className="settings-stack">
<fieldset id="roam-fields" className="settings-stack">
<div className="form-grid">
<div className="settings-field"><Label htmlFor="roam-backend">{t("生图后端")}</Label><NativeSelect id="roam-backend"><option value="">{t("自动选择后端")}</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="roam-config"><span className="field-caption">{t("候选预设")}<HelpTip text={t("使用该预设的固定词、共现规则和顺流变化预算。")} /></span></Label><NativeSelect id="roam-config"><option value="">{t("自动选择预设")}</option></NativeSelect></div>
</div>
<RoamSettingsChoices />
<div className="form-grid">
<div className="settings-field"><Label htmlFor="roam-prefetch-count"><span className="field-caption">{t("预取数量")}<HelpTip text={t("在当前图片后预备的张数；漫游页打开时按需补足，0 关闭自动预取。")} /></span></Label><Input id="roam-prefetch-count" type="number" min="0" max="20" step="1" defaultValue="0" required /></div>
<div className="settings-field"><Label htmlFor="roam-max-history-images"><span className="field-caption">{t("历史图片数量上限")}<HelpTip text={t("超限时从最早图片处理：未喜欢的永久删除本地图片及提示词 JSON；喜欢的仅从漫游隐藏，喜欢页保留。")} /></span></Label><Input id="roam-max-history-images" data-tooltip={t("仅计算当前图片之前的漫游历史；当前、预取与生成页图片不计。0 关闭数量清理。")} type="number" min="0" max="100000" step="1" defaultValue="0" required /></div>
<div className="settings-field"><Label htmlFor="roam-playback-interval"><span className="field-caption">{t("自动播放")}<HelpTip text={t("每张图片加载完成后开始计时；下一张未就绪时等待。")} /></span></Label><InputGroup><InputGroupInput id="roam-playback-interval" aria-label={t("自动播放间隔（秒）")} type="number" min="1" max="600" step="1" defaultValue="5" required /><InputGroupAddon align="inline-end">{t("秒")}</InputGroupAddon></InputGroup></div>
<div className="settings-field"><Label htmlFor="roam-candidate-count"><span className="field-caption">{t("候选组合数量")}<HelpTip text={t("标准模式每次准备的完整组合数；强力模式按倍数增加。候选越多通常等待越久。")} /></span></Label><Input id="roam-candidate-count" type="number" min="1" max="20" step="1" defaultValue="4" required /></div>
<div className="settings-field"><Label htmlFor="roam-strong-candidate-multiplier"><span className="field-caption">{t("强力候选倍数")}<HelpTip text={t("强力模式的候选组合数量 = 候选组合数量 × 倍数。只影响新任务。")} /></span></Label><Input id="roam-strong-candidate-multiplier" type="number" min="1" max="5" step="1" defaultValue="2" required /></div>
</div>
</fieldset>
<PreferenceActions />
<div id="roam-result" className="notice" role="status" hidden />
<div className="dialog-footer"><Button id="roam-save" type="submit">{t("保存设置")}</Button></div>
</form></section>
<section id="settings-history" className="settings-category space-y-6" hidden>
<Collapsible>
<CollapsibleTrigger asChild><Button type="button" variant="ghost" size="sm" className="group gap-2 rounded-none bg-transparent px-0 font-semibold hover:bg-transparent aria-expanded:bg-transparent dark:hover:bg-transparent"><ChevronRight className="transition-transform group-data-[state=open]:rotate-90" aria-hidden="true" />{t("图片清理")}</Button></CollapsibleTrigger>
<CollapsibleContent forceMount className="pt-4 data-[state=closed]:hidden"><form id="history-form" className="settings-stack">
{"\n    "}<fieldset id="history-fields">
<div className="settings-field"><Label htmlFor="history-retention-days"><span className="field-caption">{t("保留天数")}<HelpTip text={t("从图片入库起计时，默认 1 天；0 关闭过期清理，喜欢的图片保留。")} /></span></Label><Input id="history-retention-days" type="number" min="0" max="3650" step="1" required defaultValue="1" />
</div>
</fieldset>
{"\n    "}<p className="hint retention-warning">{t("到期且未喜欢的本地图片及提示词 JSON 将永久删除。")}<HelpTip text={t("取消喜欢后，已过期图片也会被清理。任务记录和 ComfyUI 文件保留。")} /></p>
{"\n    "}
{"\n    "}<div id="history-result" className="notice" role="status" hidden>
</div>
<div className="dialog-footer">

<Button id="history-save" type="submit" className="primary" variant="default" data-tooltip={t("保存后立即检查；之后在启动、浏览或生成等操作时按需清理。")}>{t("保存设置")}</Button>
</div>
{"\n  "}</form></CollapsibleContent></Collapsible>
<section id="jobs-view" aria-label={t("任务记录")}>
<h2 className="mb-4">{t("任务记录")}</h2>
<div id="jobs-empty" className="empty small" hidden>
<h2>{t("还没有生成任务")}</h2>

</div>
<div id="job-list" className="job-list">
</div>
<p id="jobs-page-message" className="hint" role="status" hidden />
<JobPageControls />
</section>
</section>

</div>
</section>
</main>
<EditorWorkspace />
</div>
</div>; }
