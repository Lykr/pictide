import { useState } from "react";
import { EditorWorkspace } from "./editor";
import { GeneratedResults } from "./components/generated-results";
import { JobPageControls } from "./components/page-controls";
import { GeneralSettings } from "./components/general-settings";
import { PreferenceActions } from "./components/preference-actions";
import { ImageInfo } from "./components/image-info";
import { RoamPlaybackButton, RoamOptions, RoamSettingsChoices } from "./components/roam-playback";
import { ArrowLeft, ArrowRight, Eye, EyeOff, FolderOpen, Heart, History, Image, ListFilter, LoaderCircle, Maximize, RefreshCw, Settings2, Database, Compass, SlidersHorizontal, Sparkles, CircleSlash, Trash2, Download, ThumbsDown, ChevronRight } from "lucide-react";
import { IconButton, HelpTip } from "./components/actions";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
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
  const privacyLabel = privacyBlur ? "关闭毛玻璃，显示图片" : "开启毛玻璃，模糊图片";
  return <div className={`feed-page${privacyBlur ? " privacy-blurred" : ""}`}>
{"\n  "}<header className="topbar">
<a className="brand" href="/" aria-label="Pictide 图片工作台">
<span className="brand-mark" aria-hidden="true">P</span>
<div>
<strong>Pictide</strong>

</div>
</a>
<div className="top-actions">
<span id="backend-status" className="status" role="status">{"未配置"}</span>
</div>
</header>
{"\n  "}<div id="app-workspace" className="workspace">
{"\n    "}<nav className="sidebar" aria-label="视图">
<Button className="nav active" data-view="feed" variant="ghost" type="button"><Compass aria-hidden="true" />漫游</Button>
<Button className="nav" data-view="generate" variant="ghost" type="button"><Sparkles aria-hidden="true" />生成</Button>
<Button className="nav" data-view="liked" variant="ghost" type="button"><Heart aria-hidden="true" />喜欢
</Button>
<Button className="nav" data-view="jobs" variant="ghost" type="button"><History aria-hidden="true" />{"任务"}</Button>
<Button className="nav" data-view="prompts" variant="ghost" type="button"><ListFilter aria-hidden="true" />{"提示词"}</Button>
<div className="sidebar-foot">
<Button className="nav" data-view="settings" variant="ghost" type="button"><Settings2 aria-hidden="true" />设置</Button>
</div>
</nav>
{"\n    "}<main id="feed-main" className="main workspace-content">
{"\n      "}<div className="section-heading">
<div className="view-heading">
<h1 id="view-title">{"漫游"}</h1>
<span id="roam-loading" className="roam-loading" role="status" hidden><LoaderCircle aria-hidden="true" /><span id="roam-loading-label" className="sr-only">正在生成漫游图片</span></span>
</div>
<div className="roam-heading-actions">
<span id="liked-privacy-controls" hidden />
<span id="roam-options-controls"><RoamOptions privacy={<Toggle id="roam-privacy" size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={`${privacyLabel} · 空格。刷新页面后默认开启。`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle>} immersive={<IconButton id="roam-immersive" icon={Maximize} label="进入沉浸模式" aria-controls="image-card" aria-pressed="false" disabled onClick={() => document.dispatchEvent(new Event("pictide:roam-options-close"))} />} /></span>
</div>
</div>
{"\n      "}<div id="notice" role="status" className="notice" hidden>
</div>
{"\n      "}<section id="gallery-view" className="gallery-view">
{"\n        "}<div id="empty-state" className="empty">
<div className="empty-mark"><Image aria-hidden="true" /></div>
<h2 id="empty-title">{"从第一张图片开始"}</h2>
<p id="empty-description">{"连接 ComfyUI，开始生成。"}</p>
<Button id="empty-settings" className="primary" variant="default" type="button">配置后端</Button>
<Button id="empty-generate" variant="default" type="button" hidden>开始生成</Button>
</div>
{"\n        "}<Card id="image-card" className="image-card gap-0 py-0" tabIndex={-1} aria-label="图片浏览" hidden>
<div className="image-stage">
<img id="main-image" alt="生成的图片" draggable={false} />
<div id="image-error" className="image-error" hidden>{"图片读取失败，请检查服务与文件是否可用。"}</div>
</div>
<div className="image-toolbar">
<div className="image-meta">
<strong id="image-index">
</strong>
<span id="image-date">
</span>
</div>
<div className="image-navigation">
<IconButton id="previous" icon={ArrowLeft} label="上一张较旧图片 · ←" variant="ghost" type="button" />
<RoamPlaybackButton />
<IconButton id="like" icon={Heart} label="喜欢 · ↑" variant="ghost" type="button" className="feedback" aria-pressed="false" />
<IconButton id="dislike" icon={ThumbsDown} label="不喜欢 · ↓" variant="ghost" type="button" className="feedback" aria-pressed="false" />
<Toggle id="roam-immersive-privacy" size="sm" className="immersive-privacy" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={`${privacyLabel} · 空格`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle>
<IconButton id="next" icon={ArrowRight} label="下一张较新图片 · →" variant="ghost" type="button" />
</div>
<div className="image-info">
<ImageInfo />
</div>
</div>
</Card>
{"\n        "}<div className="load-more-row">
<Button id="load-more" className="quiet" hidden variant="outline" type="button">{"加载更早图片"}</Button>
</div>
{"\n      "}</section>
{"\n      "}<section id="liked-view" hidden><GeneratedResults collection="liked" /></section>
{"\n      "}<section id="jobs-view" hidden>
<div id="jobs-empty" className="empty small" hidden>
<h2>{"还没有生成任务"}</h2>

</div>
<div id="job-list" className="job-list">
</div>
<p id="jobs-page-message" className="hint" role="status" hidden />
<JobPageControls />
</section>
{"\n    "}<section id="compose" className="compose" hidden>
<div className="generation-form-panel">
{"\n      "}<div className="compose-heading">
<h2>{"图像生成"}</h2>
<HelpTip text="任务提交后由后端继续执行，关闭网页不会取消任务。" />
</div>
{"\n      "}<form id="generate-form">
{"\n        "}<Label>{"后端"}<NativeSelect id="generate-backend" required size="sm">
</NativeSelect>
</Label>
{"\n        "}<Label>{"提示词来源"}<NativeSelect id="prompt-source" size="sm">
<option value="manual">{"手动输入"}</option>
<option value="rules">{"共现候选"}</option>
</NativeSelect>
</Label>
<fieldset id="rule-section" className="rule-section" hidden disabled>
  <div className="rule-primary-fields">
    <div className="rule-field">
      <div className="rule-field-heading"><Label htmlFor="rule-config--control">生成预设</Label><IconButton id="reload-rule-configs" icon={RefreshCw} label="刷新生成预设" size="icon-xs" /></div>
      <NativeSelect id="rule-config" required aria-label="生成预设" />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-mode--control">抽取模式</Label>
      <NativeSelect id="rule-mode" aria-label="抽取模式">
        <option value="random_each_run">每次随机</option>
        <option value="fixed_seed">固定提示词种子</option>
        <option value="sequence">连续序列</option>
      </NativeSelect>
    </div>
  </div>
  <p id="rule-config-note" className="hint" role="status" hidden />
  <fieldset id="rule-seed-fields" className="rule-control-grid" hidden disabled>
    <div className="rule-field">
      <Label htmlFor="rule-seed"><span className="field-caption">提示词种子<HelpTip text="控制共现标签抽取，与图像种子独立。" /></span></Label>
      <Input id="rule-seed" type="number" min="0" max="9007199254740991" step="1" required defaultValue="0" />
    </div>
    <div className="rule-field">
      <Label htmlFor="rule-seed-control--control">种子生成后</Label>
      <NativeSelect id="rule-seed-control" aria-label="种子生成后">
        <option value="fixed">固定</option><option value="increment">递增</option><option value="decrement">递减</option><option value="randomize">随机</option>
      </NativeSelect>
    </div>
  </fieldset>
  <fieldset id="rule-sequence-fields" className="rule-control-grid" hidden disabled>
    <div className="rule-field">
      <Label htmlFor="sequence-step"><span className="field-caption">帧序号<HelpTip text="同一提示词种子下按帧衔接，0 为起始帧。" /></span></Label>
      <Input id="sequence-step" type="number" min="0" max="1000" step="1" required defaultValue="0" />
    </div>
    <div className="rule-field">
      <Label htmlFor="sequence-control--control">帧序号生成后</Label>
      <NativeSelect id="sequence-control" aria-label="帧序号生成后">
        <option value="increment">递增</option><option value="fixed">固定</option><option value="decrement">递减</option><option value="randomize">随机</option>
      </NativeSelect>
    </div>
  </fieldset>
  <details className="rule-advanced">
    <summary>搜索设置</summary>
    <div className="rule-field"><Label htmlFor="rule-max-steps"><span className="field-caption">搜索上限<HelpTip text="所有模式共用，限制寻找满足共现门槛的组合的搜索步数。" /></span></Label><Input id="rule-max-steps" type="number" min="1" max="1000000" step="1" required defaultValue="100" /></div>
  </details>
  <div className="rule-actions">
    <Label className="checkbox-label auto-prompts"><input id="auto-prompts" type="checkbox" defaultChecked />生图前自动抽取<HelpTip text="手动编辑提示词会关闭自动抽取，下次生图使用当前文本。重新勾选即可恢复。" /></Label>
    <Button id="generate-prompts" type="button" variant="secondary" size="sm"><Sparkles aria-hidden="true" />抽取提示词</Button>
  </div>
  <p id="rule-generation-note" className="hint" role="status" hidden />
  <details id="rule-report" className="rule-report" hidden><summary>抽取报告</summary><pre id="rule-report-content" /></details>
</fieldset>
{"\n        "}<Label>{"正向提示词"}<Textarea id="positive" rows={8} placeholder={"描述你想看到的画面…"} required>
</Textarea>
</Label>
{"\n        "}<Label>{"负向提示词"}<Textarea id="negative" rows={4} placeholder={"不希望出现的内容（可选）"}>
</Textarea>
<small id="negative-binding-note" hidden>{"当前后端未绑定负向输入，请保持为空，或在后端设置中绑定。"}</small>
</Label>
{"\n        "}<div className="generation-plan-fields"><Label><span className="field-caption">{"图像种子"}<HelpTip id="seed-note" text="-1 为随机，每次使用的实际种子会保留。" /></span><Input id="seed" type="number" min="-1" max="9007199254740991" step="1" defaultValue="-1" />

</Label>
<div className="form-grid">
<Label htmlFor="generation-count"><span className="field-caption">每次数量<HelpTip text="每轮执行 1–10 次工作流，同一轮共享提示词。自定义工作流可能输出多张图片，全部保留。" /></span><Input id="generation-count" type="number" min="1" max="10" step="1" defaultValue="1" required /></Label>
<Label htmlFor="generation-repetitions"><span className="field-caption">生成次数<HelpTip text="生成 1–10 轮；启用自动抽取时，每轮刷新提示词，并按生成后控制推进提示词种子和序列帧。图像种子 -1 每张随机，固定值跨轮逐张递增。整批提交后关闭网页仍会继续执行。" /></span><Input id="generation-repetitions" type="number" min="1" max="10" step="1" defaultValue="1" required /></Label>
</div></div>
{"\n        "}<div className="generation-actions"><Button id="generate" className="primary" type="submit" variant="default"><Sparkles aria-hidden="true" />{"生成图片"}</Button>
<Button id="cancel-pending" type="button" variant="outline" data-tooltip="取消生成页全部待执行任务；保留已开始的任务和漫游预取。"><CircleSlash aria-hidden="true" />取消待执行任务</Button></div>

{"\n      "}</form>
</div>
<GeneratedResults />
{"\n    "}</section>
<section id="settings-view" className="settings-view" hidden>
<nav className="settings-navigation" aria-label="设置分类">
<Button data-settings-section="general" variant="ghost" type="button"><Settings2 aria-hidden="true" />通用</Button>
<Button data-settings-section="backend" variant="ghost" type="button"><SlidersHorizontal aria-hidden="true" />后端</Button>
<Button data-settings-section="roam" variant="ghost" type="button"><Compass aria-hidden="true" />漫游</Button>
<Button data-settings-section="history" variant="ghost" type="button"><Trash2 aria-hidden="true" />历史清理</Button>
<Button data-settings-section="data" variant="ghost" type="button"><Database aria-hidden="true" />数据位置</Button>
</nav>
<div className="settings-content">
<section id="settings-general" className="settings-category"><GeneralSettings initialError={themeError} /></section>
<section id="settings-backend" className="settings-category"><form id="settings-form">
<div className="form-grid">
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="edit-backend">已有后端</Label><IconButton id="delete-backend" icon={Trash2} label="删除后端配置" size="icon-xs" disabled /></div>
<NativeSelect id="edit-backend" />
</div>
<div className="settings-field"><Label htmlFor="backend-name">后端名称</Label><Input id="backend-name" required placeholder="本机 ComfyUI" /></div>
<div className="settings-field"><Label htmlFor="backend-kind">后端类型</Label><NativeSelect id="backend-kind"><option value="comfyui">ComfyUI</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="backend-url">API 地址</Label><Input id="backend-url" type="url" required defaultValue="http://127.0.0.1:8188" /></div>
</div>
<div className="settings-field">
<Label htmlFor="backend-key"><span className="field-caption">API Key<HelpTip id="key-state" text="可选。保留遮罩不修改密钥，清空并保存可移除。" /></span></Label>
<Input id="backend-key" type="password" autoComplete="new-password" />
</div>
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="workflow-name--control">工作流</Label><div className="workflow-actions">
<IconButton id="delete-workflow" icon={Trash2} label="删除工作流" size="icon-xs" disabled />
<IconButton id="reload-workflows" icon={RefreshCw} label="刷新工作流列表" size="icon-xs" />
</div></div>
<div data-workflow-picker="">
<select id="workflow-mode" aria-hidden="true" tabIndex={-1}><option value="default">默认文生图</option><option value="custom">自定义 API 工作流</option></select>
<input id="workflow-name" aria-hidden="true" tabIndex={-1} maxLength={120} />
</div>
</div>
<section id="default-workflow">
<div className="settings-field">
<div className="settings-field-heading"><Label htmlFor="default-checkpoint"><span className="field-caption">模型<HelpTip text="从配置的 ComfyUI 读取模型，留空时自动选择第一个可用模型。" /></span></Label><IconButton id="load-models" icon={RefreshCw} label="读取后端模型" size="icon-xs" /></div>
<NativeSelect id="default-checkpoint"><option value="">自动选择第一个可用模型</option></NativeSelect>
</div>
<p id="model-note" className="hint" role="status" hidden />
<Button id="edit-default-parameters" type="button" className="quiet" variant="outline" data-tooltip="将默认工作流展开为自定义草稿，编辑采样、尺寸等节点参数"><SlidersHorizontal aria-hidden="true" />节点参数</Button>
</section>
<fieldset id="custom-workflow" hidden disabled>
<Collapsible id="node-parameters" className="node-parameters" data-editor-mode="parameters" open={nodeParametersOpen} onOpenChange={setNodeParametersOpen}>
<div className="node-parameters-heading"><h3><CollapsibleTrigger asChild><Button id="toggle-node-parameters" type="button" variant="ghost" size="sm" className="justify-start gap-2 rounded-none bg-transparent px-0 font-semibold hover:bg-transparent aria-expanded:bg-transparent dark:hover:bg-transparent"><ChevronRight className={nodeParametersOpen ? "rotate-90" : ""} aria-hidden="true" />节点参数</Button></CollapsibleTrigger></h3><div className="node-parameters-actions">
<Button id="toggle-workflow-json" type="button" variant="ghost" size="sm" aria-pressed="false" aria-controls="node-parameter-fields workflow-json-editor" aria-label="编辑 API 工作流 JSON" data-tooltip="编辑 API 工作流 JSON">JSON</Button>
<IconButton icon={Download} label="导入 ComfyUI API 工作流 JSON" onClick={() => document.getElementById("workflow-file")?.click()} />
<input id="workflow-file" type="file" accept=".json,application/json" hidden />
</div></div>
<CollapsibleContent forceMount hidden={!nodeParametersOpen}>
<div id="node-parameter-fields" />
<div id="workflow-json-editor" hidden><Label htmlFor="workflow-json" className="sr-only">API 工作流 JSON</Label><Textarea id="workflow-json" className="code-input" rows={7} placeholder={'{"6":{"class_type":"CLIPTextEncode","inputs":{"text":"…"}}}'} spellCheck={false} /></div>
</CollapsibleContent>
</Collapsible>
<div id="workflow-error" className="validation" role="status" />
<div className="form-grid workflow-bindings">
<div className="binding-inputs">
<div className="settings-field"><Label htmlFor="binding-positive">正向提示词输入</Label><NativeSelect id="binding-positive"><option value="">先导入工作流</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="binding-negative">负向提示词输入</Label><NativeSelect id="binding-negative"><option value="">选择负向 text 输入</option></NativeSelect></div>
<div className="settings-field"><Label htmlFor="binding-seed">图像种子输入（可选）</Label><NativeSelect id="binding-seed"><option value="">不绑定</option></NativeSelect></div>
</div>
<div className="settings-field"><Label htmlFor="output-nodes"><span className="field-caption">输出节点<HelpTip text="可多选；留空时使用后端返回的图像输出。" /></span></Label><select id="output-nodes" data-slot="native-select" className={nativeSelectClassName} multiple size={3} /></div>
</div>
</fieldset>
<div id="settings-result" className="notice" role="status" hidden />
<div className="dialog-footer"><Button id="test-backend" type="button" className="quiet" variant="outline">测试连接</Button><Button id="save-backend" type="submit" className="primary" variant="default">保存后端</Button></div>
</form></section>
<section id="settings-roam" className="settings-category" hidden><form id="roam-form">
<fieldset id="roam-fields">
<div className="form-grid">
<Label htmlFor="roam-prefetch-count"><span className="field-caption">预取数量<HelpTip text="保持当前图片之后有 N 张较新的图片可查看；不足时自动生成，0 关闭。仅在漫游页可见时补图，生成需要时间。" /></span><Input id="roam-prefetch-count" type="number" min="0" max="20" step="1" defaultValue="0" required /></Label>
<Label htmlFor="roam-max-history-images"><span className="field-caption">历史图片数量上限<HelpTip text="0 关闭数量清理。计算当前图片之前的所有漫游图片，超限时优先清理最早的图片：未喜欢的删除本地图片及提示词 JSON，无法撤回；喜欢的仅从漫游隐藏，喜欢页保留。当前、预取及生成页图片不计入上限。" /></span><Input id="roam-max-history-images" type="number" min="0" max="100000" step="1" defaultValue="0" required /></Label>
</div>
<div className="form-grid">
<Label htmlFor="roam-backend"><span className="field-caption h-6">生图后端</span><NativeSelect id="roam-backend"><option value="">自动选择后端</option></NativeSelect></Label>
<Label htmlFor="roam-config"><span className="field-caption">候选预设<HelpTip text="候选模块提供完整提示词组合，推荐根据有效点赞评分；模型不可用时使用默认候选。图像种子随机。" /></span><NativeSelect id="roam-config"><option value="">自动选择预设</option></NativeSelect></Label>
</div>
<div className="form-grid">
<Label htmlFor="roam-playback-interval"><span className="field-caption">自动播放间隔（秒）<HelpTip text="自动播放时每张图片的展示时间；下一张未生成完成时等待，范围 1–600 秒。" /></span><Input id="roam-playback-interval" type="number" min="1" max="600" step="1" defaultValue="5" required /></Label>
</div>
<RoamSettingsChoices />
</fieldset>
<PreferenceActions />
<div id="roam-result" className="notice" role="status" hidden />
<div className="dialog-footer"><Button id="roam-save" type="submit">保存设置</Button></div>
</form></section>
<section id="settings-history" className="settings-category" hidden><form id="history-form">
{"\n    "}<fieldset id="history-fields">
<Label><span className="field-caption">{"保留天数"}<HelpTip text="默认 1 天（24 小时）。设为 0 关闭自动清理，已喜欢的图片长期保留。" /></span><Input id="history-retention-days" type="number" min="0" max="3650" step="1" required defaultValue="1" />

</Label>
</fieldset>
{"\n    "}<p className="hint retention-warning">{"到期且未喜欢的图片及提示词将自动删除。"}<HelpTip text="从图片进入 Feed 起计时，在启动、浏览或生成时清理，生成记录保留。取消喜欢后，过期图片也会被清理。仅影响 Pictide 本地历史，ComfyUI 文件由后端管理。" /></p>
{"\n    "}
{"\n    "}<div id="history-result" className="notice" role="status" hidden>
</div>
<div className="dialog-footer">

<Button id="history-save" type="submit" className="primary" variant="default">{"保存设置"}</Button>
</div>
{"\n  "}</form></section>
<section id="settings-data" className="settings-category" hidden>
<dl className="data-locations"><dt>数据目录</dt><dd id="data-directory">读取中…</dd><dt>数据库</dt><dd id="database-path">读取中…</dd></dl>
</section>
</div>
</section>
</main>
<EditorWorkspace />
</div>
</div>; }
