import { useEffect, useRef, useState, type ReactNode } from "react";
import { GripVertical, Check, ChevronsUpDown, Copy, LoaderCircle, Plus, RefreshCw, Save, Sparkles, Trash2, X } from "lucide-react";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { Label } from "./components/ui/label";
import { Badge } from "./components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/ui/select";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./components/ui/command";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "./components/ui/popover";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./components/ui/collapsible";
import { HelpTip, IconButton } from "./components/actions";
import { PreviewPrompts, type PreviewTerm } from "./components/preview-relations";
import { PageControls, DEFAULT_PAGE_SIZE } from "./components/page-controls";
import { confirmAction } from "./components/confirm-action";
import { sortFixedTags } from "./controllers/fixed-tags-sort.mjs";
import { counterAfter } from "./controllers/rule-controls.mjs";
import "./styles/theme.css";
import "./styles/editor.css";

type Tag = { id: number; name: string; post_count: number };
type TagPage = { tags: Tag[]; total: number; page: number; page_size: number };
type PresetDocument = { base_positive: string[]; base_negative: string[]; blocked_keywords: string[]; min_tags: number; max_tags: number; pmi_threshold: number; min_cooccurrence: number; change_budget: number };
type Preset = { id: string; name: string; document: PresetDocument };
type Mode = "random_each_run" | "fixed_seed" | "sequence";
type Result = { candidate_id: string; positive: string; negative: string; seed: number; selected_tags: PreviewTerm[]; sequence?: { seed?: number; step?: number; changes?: number; change_budget?: number }; report: Record<string, unknown> };
const defaults: PresetDocument = { base_positive: [], base_negative: [], blocked_keywords: [], min_tags: 5, max_tags: 20, pmi_threshold: 0, min_cooccurrence: 10, change_budget: 2 };
const stopReasons: Record<string, string> = { target_length: "达到目标长度", no_candidates: "无可用候选", budget_exhausted: "达到变化预算", max_steps: "达到搜索上限", search_limit: "已达搜索上限", no_eligible_tags: "已无可扩展标签", budget_zero: "保持上一帧", held_no_legal_change: "无合法变化，保持上一帧" };
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json" } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || `请求失败（${response.status}）`);
  return data;
}
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const normalized = (text: string) => text.trim().replaceAll("_", " ").toLowerCase();
function Choice({ label, value, onChange, options, disabled }: { label: string; value: string; onChange: (value: string) => void; options: { value: string; text: string }[]; disabled?: boolean }) {
  return <Select value={value} onValueChange={onChange} disabled={disabled}><SelectTrigger aria-label={label}><SelectValue placeholder={label} /></SelectTrigger><SelectContent>{options.map(item => <SelectItem value={item.value} key={item.value}>{item.text}</SelectItem>)}</SelectContent></Select>;
}
function Field({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return <div className="cooc-field"><Label><span>{label}</span>{help && <HelpTip text={help} />}</Label>{children}</div>;
}
function FixedTags({ label, values, onChange, disabled }: { label: string; values: string[]; onChange: (values: string[]) => void; disabled: boolean }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [matches, setMatches] = useState<Tag[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [origins, setOrigins] = useState<Map<string, boolean>>(new Map());
  const [originError, setOriginError] = useState(false);
  const originCache = useRef(new Map<string, boolean>());
  const termKey = JSON.stringify([...new Set(values.map(value => value.trim().replaceAll("_", " ")).filter(Boolean))].sort());
  useEffect(() => {
    const terms: string[] = JSON.parse(termKey);
    const missing = terms.filter(text => !originCache.current.has(text));
    setOriginError(false);
    if (!missing.length) return;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      api<{ anchor: { text: string; known: boolean }; relations: { text: string; known: boolean }[] }>("/api/candidate/relations", {
        method: "POST", body: JSON.stringify({ anchor: missing[0], terms: missing.slice(1) }), signal: abort.signal,
      }).then(data => {
        if (abort.signal.aborted) return;
        for (const term of [data.anchor, ...data.relations]) originCache.current.set(term.text, term.known);
        setOrigins(new Map(originCache.current));
      }).catch(() => { if (!abort.signal.aborted) setOriginError(true); });
    }, 250);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [termKey]);
  const list = useRef<HTMLDivElement>(null);
  const navigating = useRef(false);
  const move = (from: number, to: number) => {
    const next = [...values];
    next.splice(to, 0, next.splice(from, 1)[0]);
    onChange(next);
  };
  useEffect(() => {
    if (!list.current || disabled) return;
    return sortFixedTags(list.current, move);
  }, [values, disabled, onChange]);
  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    setLoading(true); setMatches([]); setError("");
    const timer = setTimeout(() => {
      api<TagPage>(`/api/candidate/tags?query=${encodeURIComponent(query)}&page=1&page_size=12`, { signal: abort.signal })
        .then(data => { setMatches(data.tags); setError(""); }).catch(error => { if (!abort.signal.aborted) { setMatches([]); setError(message(error)); } }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    }, 180);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [query, open]);
  const add = (text: string) => {
    const value = text.trim().replaceAll("_", " ");
    if (!value || values.some(item => normalized(item) === normalized(value))) return;
    onChange([...values, value]); setQuery(""); setOpen(false); navigating.current = false;
  };
  const options = matches.filter(item => !values.some(value => normalized(value) === normalized(item.name)));
  const custom = query.trim() && !matches.some(item => normalized(item.name) === normalized(query)) && !values.some(item => normalized(item) === normalized(query));
  return <section className="cooc-fixed">
    <div className="cooc-section-heading"><h2>{label}</h2><HelpTip text="输入完整提示词，回车直接添加；也可点击或用方向键选择词库匹配项。自由文本会保留，未匹配的正向词不参与共现计算。拖动手柄调整输出顺序，保存配置后生效。" /></div>
    <Command shouldFilter={false} className="h-auto overflow-visible bg-transparent p-0"><Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverAnchor asChild><div className="cooc-fixed-picker"><span aria-hidden="true" /><div className="min-w-0"><CommandInput disabled={disabled} value={query} placeholder="输入提示词，回车添加" aria-label={`添加${label}`} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onValueChange={(value: string) => { setQuery(value); setOpen(true); navigating.current = false; }} onKeyDown={event => {
        if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) { if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); } return; }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") navigating.current = true;
        if (event.key === "Enter" && query.trim() && (!navigating.current || !options.length)) { event.preventDefault(); event.stopPropagation(); add(query); }
      }} /></div><PopoverTrigger asChild><IconButton disabled={disabled} icon={ChevronsUpDown} label={`展开${label}匹配项`} /></PopoverTrigger></div></PopoverAnchor>
      <PopoverContent className="min-w-72 p-0" align="start" onOpenAutoFocus={event => event.preventDefault()}><CommandList aria-label={`${label}匹配项`}>
        <CommandEmpty>{error ? "词库暂不可用，仍可输入提示词并回车添加" : loading ? "搜索中…" : "输入完整提示词并回车添加"}</CommandEmpty>
        <CommandGroup>{custom && <CommandItem value="__custom" onSelect={() => add(query)}>添加：{query}</CommandItem>}
          {options.map(tag => <CommandItem key={tag.id} value={String(tag.id)} onSelect={() => add(tag.name)}><span className="break-words">{tag.name}</span></CommandItem>)}</CommandGroup>
      </CommandList></PopoverContent>
    </Popover></Command>
    <div className="cooc-fixed-list" ref={list}>{values.map((value, index) => <div className="cooc-fixed-row" key={index}>
      <IconButton className="cooc-fixed-handle" icon={GripVertical} label={`拖拽排序${label}第 ${index + 1} 项（↑/↓）`} disabled={disabled} onKeyDown={event => {
        const to = index + (event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0);
        if (to === index) return;
        event.preventDefault(); event.stopPropagation();
        if (to >= 0 && to < values.length) { move(index, to); (list.current?.children[to]?.querySelector(".cooc-fixed-handle") as HTMLButtonElement)?.focus(); }
      }} />
      <div className="cooc-fixed-value">
        <Input aria-label={`${label}第 ${index + 1} 项`} value={value} disabled={disabled} onChange={event => onChange(values.map((item, position) => position === index ? event.target.value : item))} />
        <Badge className="cooc-fixed-origin" variant={origins.get(value.trim().replaceAll("_", " ")) === true ? "secondary" : "outline"} data-tooltip={
          !value.trim() ? "输入完整提示词后识别来源" : origins.get(value.trim().replaceAll("_", " ")) === true ? "完整文本匹配词库；固定正向词参与共现比较，固定负向词仅输出" : origins.get(value.trim().replaceAll("_", " ")) === false ? "完整文本未匹配词库；保留输出，不参与共现比较" : originError ? "词库识别暂不可用，尚未确定来源；编辑词项可重试" : "正在匹配词库"
        }>{!value.trim() ? "待输入" : origins.get(value.trim().replaceAll("_", " ")) === true ? "词库词" : origins.get(value.trim().replaceAll("_", " ")) === false ? "自定义" : originError ? "未识别" : "识别中"}</Badge>
      </div>
      <IconButton icon={X} label={`移除${label}第 ${index + 1} 项`} disabled={disabled} onClick={() => onChange(values.filter((_, position) => position !== index))} />
    </div>)}</div>
  </section>;
}

export function EditorWorkspace() {
  const [tab, setTab] = useState("library");
  const [presets, setPresets] = useState<{ id: string; name: string }[]>([]);
  const [preset, setPreset] = useState<Preset>({ id: "", name: "新预设", document: { ...defaults } });
  const [saved, setSaved] = useState("");
  const [blockedText, setBlockedText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [notice, setNotice] = useState("");
  const [success, setSuccess] = useState(false);
  const [dataset, setDataset] = useState<Record<string, unknown>>({});
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [tags, setTags] = useState<TagPage>({ tags: [], total: 0, page: 1, page_size: DEFAULT_PAGE_SIZE });
  const [tagLoading, setTagLoading] = useState(false);
  const [tagError, setTagError] = useState("");
  const [mode, setMode] = useState<Mode>("random_each_run");
  const [seed, setSeed] = useState(0);
  const [step, setStep] = useState(0);
  const [seedControl, setSeedControl] = useState("fixed");
  const [stepControl, setStepControl] = useState("increment");
  const [maxSteps, setMaxSteps] = useState(100);
  const [result, setResult] = useState<Result | null>(null);
  const [refresh, setRefresh] = useState(0);
  const dirty = JSON.stringify(preset) !== saved;
  const loadPreset = (next: Preset) => {
    const loaded = { ...next, document: { ...next.document, blocked_keywords: next.document.blocked_keywords ?? [] } };
    setPreset(loaded); setBlockedText(loaded.document.blocked_keywords.join("\n")); setSaved(JSON.stringify(loaded));
  };
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty && loaded) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, loaded]);
  useEffect(() => {
    let active = true;
    Promise.all([api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"), api<Record<string, unknown>>("/api/candidate/dataset")]).then(async ([listing, info]) => {
      if (!active) return;
      setPresets(listing.presets); setDataset(info);
      const initial = listing.presets[0] ? await api<Preset>(`/api/candidate/presets/${encodeURIComponent(listing.presets[0].id)}`) : { id: "", name: "新预设", document: { ...defaults } };
      if (active) { loadPreset(initial); setLoaded(true); }
    }).catch(error => { if (active) setNotice(message(error)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    setTagLoading(true);
    const timer = setTimeout(() => api<TagPage>(`/api/candidate/tags?query=${encodeURIComponent(query)}&page=${page}&page_size=${DEFAULT_PAGE_SIZE}`, { signal: abort.signal })
      .then(data => { setTags(data); setTagError(""); }).catch(error => { if (!abort.signal.aborted) setTagError(message(error)); }).finally(() => { if (!abort.signal.aborted) setTagLoading(false); }), 180);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [query, page, refresh]);
  const update = <K extends keyof PresetDocument>(key: K, value: PresetDocument[K]) => { setPreset(current => ({ ...current, document: { ...current.document, [key]: value } })); setSuccess(false); };
  const discard = async () => !dirty || await confirmAction("当前预设有未保存的修改，继续会放弃这些修改。");
  const selectPreset = async (id: string) => {
    if (id === preset.id || !(await discard())) return;
    setBusy(true); setNotice("");
    try { const next = await api<Preset>(`/api/candidate/presets/${encodeURIComponent(id)}`); loadPreset(next); setResult(null); setSuccess(false); setLoaded(true); }
    catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const create = async (copy = false) => {
    if (!copy && !(await discard())) return;
    const next = copy ? { ...preset, id: "", name: `${preset.name} 副本`, document: structuredClone(preset.document) } : { id: "", name: "新预设", document: { ...defaults } };
    setPreset(next); setBlockedText(next.document.blocked_keywords.join("\n"));
    setSaved(""); setResult(null); setSuccess(false); setLoaded(true); setTab("settings");
  };
  const validate = () => {
    if (!preset.name.trim()) throw new Error("请输入预设名称。");
    for (const [key, value] of Object.entries(preset.document)) {
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error(`${key} 需要有效数值。`);
    }
    if ([...preset.document.base_positive, ...preset.document.base_negative].some(text => !text.trim())) throw new Error("固定提示词不能为空，请填写或移除空项。");
    if (!Number.isInteger(preset.document.min_tags) || preset.document.min_tags < 1) throw new Error("标签数量下限须为至少 1 的整数。");
    if (preset.document.min_tags > preset.document.max_tags) throw new Error("标签数量下限不能大于上限。");
    if (preset.document.base_positive.length > preset.document.max_tags) throw new Error("固定正向词数量超过标签上限。");
  };
  const save = async () => {
    setBusy(true); setNotice(""); setSuccess(false);
    try {
      validate();
      const next = await api<Preset>("/api/candidate/presets", { method: "POST", body: JSON.stringify({ ...preset, id: preset.id || undefined }) });
      loadPreset(next); setSuccess(true); setLoaded(true);
      const listing = await api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"); setPresets(listing.presets);
      document.dispatchEvent(new Event("pictide:candidate-presets-changed"));
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!preset.id || !(await confirmAction(`删除预设“${preset.name}”？此操作无法撤销。`))) return;
    setBusy(true); setNotice("");
    try {
      await api(`/api/candidate/presets/${encodeURIComponent(preset.id)}`, { method: "DELETE", body: "{}" });
      const listing = await api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"); setPresets(listing.presets);
      const next = listing.presets[0] ? await api<Preset>(`/api/candidate/presets/${encodeURIComponent(listing.presets[0].id)}`) : { id: "", name: "新预设", document: { ...defaults } };
      loadPreset(next); setResult(null); setSuccess(false);
      document.dispatchEvent(new Event("pictide:candidate-presets-changed"));
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const preview = async () => {
    setBusy(true); setNotice("");
    try {
      validate();
      const next = await api<Result>("/api/candidate/generate", { method: "POST", body: JSON.stringify({ preset_id: preset.id || "draft", document: preset.document, mode, seed, sequence_step: mode === "sequence" ? step : 0, max_steps: maxSteps }) });
      setResult(next);
      if (mode !== "random_each_run") setSeed(counterAfter(mode === "sequence" ? next.sequence?.seed ?? seed : next.seed, seedControl, Number.MAX_SAFE_INTEGER));
      if (mode === "sequence") setStep(counterAfter(step, stepControl, 1000));
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const controlOptions = [{ value: "fixed", text: "固定" }, { value: "increment", text: "递增" }, { value: "decrement", text: "递减" }, { value: "randomize", text: "随机" }];
  const numberField = (key: keyof Omit<PresetDocument, "base_positive" | "base_negative" | "blocked_keywords">, label: string, help: string, min?: number, max?: number, increment: number | "any" = 1) => <Field label={label} help={help}><Input aria-label={label} type="number" min={min} max={max} step={increment} value={Number.isNaN(preset.document[key]) ? "" : preset.document[key]} required disabled={busy} onChange={event => update(key, event.target.valueAsNumber)} /></Field>;
  const pages = Math.max(1, Math.ceil(tags.total / tags.page_size));
  return <section id="prompts-view" className="editor-page workspace-content" aria-label="提示词" hidden>
    <header className="editor-toolbar"><h1>提示词</h1><span className="spacer" /><Badge variant="secondary" data-tooltip={`数据来源：${String(dataset.source || "尚未导入")}`}>{dataset.status === "ready" ? "词库就绪" : "词库未就绪"}</Badge></header>
    <Tabs value={tab} onValueChange={setTab}><nav className="editor-tabs" aria-label="提示词栏目"><TabsList><TabsTrigger value="library">词库</TabsTrigger><TabsTrigger value="settings">生成设置</TabsTrigger><TabsTrigger value="preview">预览</TabsTrigger></TabsList></nav></Tabs>
    {notice && <div className="notice error" role="alert">{notice}</div>}
    <main>
      {tab === "library" ? <section className="cooc-library">
        <div className="cooc-library-filters"><Input aria-label="搜索词库标签" placeholder="搜索标签" value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} /><IconButton icon={RefreshCw} label="刷新词库" onClick={() => setRefresh(value => value + 1)} disabled={tagLoading} /><span className="text-xs text-muted-foreground">只读</span></div>
        {tagError && <p className="cooc-error" role="alert">{tagError}</p>}
        <div className="cooc-tags" aria-busy={tagLoading}>{tagLoading ? <div className="cooc-empty" role="status"><LoaderCircle className="size-4 animate-spin" />加载中</div> : tags.tags.length ? tags.tags.map(tag => <div className="cooc-tag" key={tag.id}><span className="min-w-0 break-words">{tag.name}</span><span className="cooc-frequency" data-tooltip="数据集中包含此标签的图片数量">{tag.post_count.toLocaleString()}</span></div>) : <p className="cooc-empty">{query ? "没有匹配标签" : "词库尚无标签，请先导入数据。"}</p>}</div>
        <PageControls label="词库" page={page} totalPages={pages} loading={tagLoading} onPageChange={setPage} />
      </section> : <>
        <div className="cooc-preset-toolbar"><Choice label="生成预设" value={preset.id || "__new"} onChange={selectPreset} disabled={busy} options={[...presets.map(item => ({ value: item.id, text: item.name })), ...(!preset.id ? [{ value: "__new", text: "未保存预设" }] : [])]} /><IconButton icon={Plus} label="新建预设" disabled={busy} onClick={() => create()} /><IconButton icon={Copy} label="复制预设" disabled={busy || !loaded} onClick={() => create(true)} /><IconButton icon={Trash2} label="删除预设" disabled={busy || !preset.id} onClick={remove} /><span className="spacer" /><span className="text-xs text-muted-foreground" role="status">{loaded && dirty ? "未保存" : ""}</span><Button disabled={busy || !dirty} onClick={save}>{busy ? <LoaderCircle className="animate-spin" /> : success ? <Check /> : <Save />}{success ? "已保存" : "保存"}</Button></div>
        {tab === "settings" ? <form className="cooc-settings" onSubmit={event => { event.preventDefault(); save(); }}>
          <Field label="预设名称"><Input aria-label="预设名称" value={preset.name} disabled={busy} required onChange={event => { setPreset(current => ({ ...current, name: event.target.value })); setSuccess(false); }} /></Field>
          <div className="cooc-fixed-grid"><FixedTags label="固定正向词" values={preset.document.base_positive} disabled={busy} onChange={values => update("base_positive", values)} /><FixedTags label="固定负向词" values={preset.document.base_negative} disabled={busy} onChange={values => update("base_negative", values)} /></div>
          <div className="cooc-section-heading"><h2>共现扩展</h2><HelpTip text="每个新标签必须同时满足与所有已有统计标签的 PMI 阈值及最低共现次数。词库包含出现至少 100 次的普通标签及 general / sensitive / questionable / explicit 评级；仅保留共现至少 10 次的关系。" /></div>
          <div className="cooc-number-grid">
            {numberField("min_tags", "标签数量下限", "包含固定正向词；每次在下限和上限之间等概率抽取目标数量，无法达到时使用当前已生成的数量。", 1, 1000)}
            {numberField("max_tags", "标签数量上限", "包含固定正向词；上下限均可被抽中。固定词超过下限时，以固定词数量作为实际下限。", 1, 1000)}
            {numberField("pmi_threshold", "PMI 阈值", "PMI = log₂(共同次数 × 总图片数 ÷ 两个标签各自次数之积)。0 表示独立，正数表示更常共同出现，负数表示更少共同出现；可填写任意有限数。", undefined, undefined, "any")}
            {numberField("min_cooccurrence", "最低共现次数", "每对标签必须共同出现至少此次数；词库仅保留至少 10 次的关系，设为更小的值也不会恢复已裁剪关系。", 1, Number.MAX_SAFE_INTEGER)}
            {numberField("change_budget", "连续变化预算", "仅连续模式生效。相邻帧标签增删的总数上限；替换一个标签计 2，固定词保留。在预算可达的数量区间内均匀抽取目标，无法合法变化时保持上一帧。", 0, 1000)}
          </div>
          <Field label="屏蔽关键词" help="每行一个关键词，跳过包含任一关键词的共现抽取标签；忽略大小写，空格与下划线等价。仅影响后续新抽取的正向标签，固定正负词不受影响；驻足保持的提示词不重新过滤。">
            <Textarea aria-label="屏蔽关键词" placeholder={"每行一个关键词，例如：\nhair\nblack socks"} rows={3} disabled={busy} value={blockedText} onChange={event => {
              const text = event.target.value;
              setBlockedText(text);
              update("blocked_keywords", [...new Set(text.split(/\r?\n/).map(item => item.trim()).filter(Boolean))]);
            }} />
          </Field><button type="submit" hidden />
        </form> : <section className="cooc-preview">
          <div className="cooc-preview-controls"><Field label="生成模式"><Choice label="预览生成模式" value={mode} onChange={value => setMode(value as Mode)} options={[{ value: "random_each_run", text: "每次随机" }, { value: "fixed_seed", text: "固定种子" }, { value: "sequence", text: "连续序列" }]} disabled={busy} /></Field>
            {mode !== "random_each_run" && <><Field label="提示词种子"><Input aria-label="预览提示词种子" type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} value={seed} disabled={busy} onChange={event => setSeed(event.target.valueAsNumber)} /></Field><Field label="种子生成后"><Choice label="预览种子生成后" value={seedControl} onChange={setSeedControl} options={controlOptions} disabled={busy} /></Field></>}
            {mode === "sequence" && <><Field label="帧序号"><Input aria-label="预览帧序号" type="number" min={0} max={1000} step={1} value={step} disabled={busy} onChange={event => setStep(event.target.valueAsNumber)} /></Field><Field label="帧序号生成后"><Choice label="预览帧序号生成后" value={stepControl} onChange={setStepControl} options={controlOptions} disabled={busy} /></Field></>}
            <Button variant="secondary" disabled={busy || !loaded} onClick={preview}>{busy ? <LoaderCircle className="animate-spin" /> : <Sparkles />}预览</Button>
          </div>
          <Collapsible><CollapsibleTrigger asChild><Button variant="ghost" size="sm">搜索设置</Button></CollapsibleTrigger><CollapsibleContent><Field label="搜索上限" help="限制寻找合法组合的搜索步数，所有模式共用。"><Input className="max-w-48" aria-label="预览搜索上限" type="number" min={1} max={1000000} value={maxSteps} step={1} onChange={event => setMaxSteps(event.target.valueAsNumber)} /></Field></CollapsibleContent></Collapsible>
          {result ? <><PreviewPrompts key={result.candidate_id} terms={result.selected_tags} positive={result.positive} negative={result.negative} /><div className="cooc-result-summary"><Badge variant="secondary">{stopReasons[String(result.report.stop_reason)] || String(result.report.stop_reason || "已生成")}</Badge><span>种子 {result.seed}</span>{result.sequence && <span>帧 {result.sequence.step ?? step} · 变化 {result.sequence.changes ?? 0} / {result.sequence.change_budget ?? preset.document.change_budget}</span>}</div>{Array.isArray(result.report.unrecognized_fixed) && result.report.unrecognized_fixed.length > 0 && <p className="text-xs text-muted-foreground" role="status">未参与共现计算：{result.report.unrecognized_fixed.join(", ")}</p>}<Collapsible><CollapsibleTrigger asChild><Button variant="ghost" size="sm">生成报告</Button></CollapsibleTrigger><CollapsibleContent><pre className="cooc-report">{JSON.stringify({ selected_tags: result.selected_tags, sequence: result.sequence, ...result.report }, null, 2)}</pre></CollapsibleContent></Collapsible></> : <p className="cooc-empty">预览当前预设，不生成图片。</p>}
        </section>}
      </>}
    </main>
  </section>;
}
