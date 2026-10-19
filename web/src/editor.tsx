import { useEffect, useRef, useState, type ReactNode } from "react";
import { GripVertical, Check, ChevronRight, Settings2, ChevronsUpDown, Copy, LoaderCircle, Plus, RefreshCw, Save, Sparkles, Trash2, Upload, X } from "lucide-react";
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
import { t, tr, locale } from "./i18n/index.mjs";
import "./styles/theme.css";
import "./styles/editor.css";

type Tag = { id: number; name: string; post_count: number };
type Library = { filename: string; tag_count: number; relation_count: number; bytes: number };
type LibraryListing = { selected: string; libraries: Library[] };
type TagPage = { tags: Tag[]; total: number; page: number; page_size: number };
type PresetDocument = { base_positive: string[]; base_negative: string[]; blocked_keywords: string[]; min_tags: number; max_tags: number; pmi_threshold: number; min_cooccurrence: number; change_budget: number };
type Preset = { id: string; name: string; document: PresetDocument };
type Mode = "random_each_run" | "fixed_seed" | "sequence";
type Result = { candidate_id: string; positive: string; negative: string; seed: number; selected_tags: PreviewTerm[]; sequence?: { seed?: number; step?: number; changes?: number; change_budget?: number }; report: Record<string, unknown> };
const defaults: PresetDocument = { base_positive: [], base_negative: [], blocked_keywords: [], min_tags: 10, max_tags: 30, pmi_threshold: 0, min_cooccurrence: 10, change_budget: 2 };
function withCooccurrenceFloor(preset: Preset, floor: number): Preset {
  const value = preset.document.min_cooccurrence;
  if (Number.isFinite(value) && value >= floor) return preset;
  return { ...preset, document: { ...preset.document, min_cooccurrence: floor } };
}
const stopReasons: Record<string, string> = { target_length: "达到目标长度", no_candidates: "无可用候选", budget_exhausted: "达到变化预算", max_steps: "达到搜索上限", search_limit: "已达搜索上限", no_eligible_tags: "已无可扩展标签", budget_zero: "保持上一帧", held_no_legal_change: "无合法变化，保持上一帧" };
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json" } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || tr`请求失败（${response.status}）`);
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
function FixedTags({ label, values, onChange, disabled, positive = false }: { label: string; values: string[]; onChange: (values: string[]) => void; disabled: boolean; positive?: boolean }) {
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
    <div className="cooc-section-heading"><h2>{label}</h2><HelpTip text={t("每次生成均保留这些词，按列表顺序输出。")} /></div>
    <Command shouldFilter={false} className="h-auto overflow-visible bg-transparent p-0"><Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverAnchor asChild><div className="cooc-fixed-picker"><span aria-hidden="true" /><div className="min-w-0"><CommandInput disabled={disabled} value={query} placeholder={t("输入提示词，回车添加")} aria-label={tr`添加${label}`} data-tooltip={t("输入完整提示词并回车添加，也可选择词库匹配项。")} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onValueChange={(value: string) => { setQuery(value); setOpen(true); navigating.current = false; }} onKeyDown={event => {
        if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) { if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); } return; }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") navigating.current = true;
        if (event.key === "Enter" && query.trim() && (!navigating.current || !options.length)) { event.preventDefault(); event.stopPropagation(); add(query); }
      }} /></div><PopoverTrigger asChild><IconButton disabled={disabled} icon={ChevronsUpDown} label={tr`展开${label}匹配项；点击或用方向键选择后回车添加`} /></PopoverTrigger></div></PopoverAnchor>
      <PopoverContent className="min-w-72 p-0" align="start" onOpenAutoFocus={event => event.preventDefault()}><CommandList aria-label={tr`${label}匹配项`}>
        <CommandEmpty>{error ? t("词库暂不可用，仍可输入提示词并回车添加") : loading ? t("搜索中…") : t("输入完整提示词并回车添加")}</CommandEmpty>
        <CommandGroup>{custom && <CommandItem value="__custom" onSelect={() => add(query)}>{tr`添加：${query}`}</CommandItem>}
          {options.map(tag => <CommandItem key={tag.id} value={String(tag.id)} onSelect={() => add(tag.name)}><span className="break-words">{tag.name}</span></CommandItem>)}</CommandGroup>
      </CommandList></PopoverContent>
    </Popover></Command>
    <div className="cooc-fixed-list" ref={list}>{values.map((value, index) => <div className="cooc-fixed-row" key={index}>
      <IconButton className="cooc-fixed-handle" icon={GripVertical} label={tr`拖动调整${label}第 ${index + 1} 项的输出顺序，也可按 ↑/↓ 排序`} disabled={disabled} onKeyDown={event => {
        const to = index + (event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0);
        if (to === index) return;
        event.preventDefault(); event.stopPropagation();
        if (to >= 0 && to < values.length) { move(index, to); (list.current?.children[to]?.querySelector(".cooc-fixed-handle") as HTMLButtonElement)?.focus(); }
      }} />
      <div className="cooc-fixed-value">
        <Input aria-label={tr`${label}第 ${index + 1} 项`} value={value} disabled={disabled} onChange={event => onChange(values.map((item, position) => position === index ? event.target.value : item))} />
        <Badge className="cooc-fixed-origin" variant={origins.get(value.trim().replaceAll("_", " ")) === true ? "secondary" : "outline"} data-tooltip={
          !value.trim() ? t("输入完整提示词后识别来源") : origins.get(value.trim().replaceAll("_", " ")) === true ? (positive ? t("匹配词库，作为共现扩展的正向锚点。") : t("匹配词库，输出为负向提示词；共现扩展跳过同名词。")) : origins.get(value.trim().replaceAll("_", " ")) === false ? t("未匹配词库，保留完整文本输出，不参与 PMI 比较。") : originError ? t("词库识别暂不可用，尚未确定来源；编辑词项可重试") : t("正在匹配词库")
        }>{!value.trim() ? t("待输入") : origins.get(value.trim().replaceAll("_", " ")) === true ? t("词库词") : origins.get(value.trim().replaceAll("_", " ")) === false ? t("自定义") : originError ? t("未识别") : t("识别中")}</Badge>
      </div>
      <IconButton icon={X} label={tr`移除${label}第 ${index + 1} 项`} disabled={disabled} onClick={() => onChange(values.filter((_, position) => position !== index))} />
    </div>)}</div>
  </section>;
}

export function EditorWorkspace() {
  const [tab, setTab] = useState("library");
  const [presets, setPresets] = useState<{ id: string; name: string }[]>([]);
  const [preset, setPreset] = useState<Preset>({ id: "", name: t("新预设"), document: { ...defaults } });
  const [saved, setSaved] = useState("");
  const [blockedText, setBlockedText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [notice, setNotice] = useState("");
  const [success, setSuccess] = useState(false);
  const [library, setLibrary] = useState<LibraryListing>({ selected: "", libraries: [] });
  const [libraryAction, setLibraryAction] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [libraryRevision, setLibraryRevision] = useState(0);
  const libraryInput = useRef<HTMLInputElement>(null);
  const libraryRequest = useRef(0);
  const presetRequest = useRef(0);
  const cooccurrenceFloor = useRef(defaults.min_cooccurrence);
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
  const minCooccurrence = typeof dataset.min_cooccurrence === "number" ? dataset.min_cooccurrence : defaults.min_cooccurrence;
  const updateDataset = (info: Record<string, unknown>) => {
    const floor = typeof info.min_cooccurrence === "number" ? info.min_cooccurrence : defaults.min_cooccurrence;
    cooccurrenceFloor.current = floor; setDataset(info);
    setPreset(current => withCooccurrenceFloor(current, floor));
    setSuccess(false);
  };
  const loadPreset = (next: Preset) => {
    const loaded = { ...next, document: { ...next.document, blocked_keywords: next.document.blocked_keywords ?? [] } };
    setPreset(withCooccurrenceFloor(loaded, cooccurrenceFloor.current)); setBlockedText(loaded.document.blocked_keywords.join("\n")); setSaved(JSON.stringify(loaded));
  };
  const activatePreset = (id: string) => new Promise((resolve, reject) => document.dispatchEvent(new CustomEvent("pictide:roam-settings-save", {
    detail: { patch: { preset_id: id }, resolve, reject },
  })));
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty && loaded) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, loaded]);
  useEffect(() => {
    let active = true;
    const libraryLoad = ++libraryRequest.current;
    const presetLoad = ++presetRequest.current;
    Promise.all([api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"), api<Record<string, unknown>>("/api/candidate/dataset"), api<{ preset_id: string }>("/api/settings/roam")]).then(async ([listing, info, settings]) => {
      if (!active) return;
      setPresets(listing.presets);
      if (libraryLoad === libraryRequest.current) updateDataset(info);
      const selected = listing.presets.find(item => item.id === settings.preset_id) ?? listing.presets[0];
      const initial = selected ? await api<Preset>(`/api/candidate/presets/${encodeURIComponent(selected.id)}`) : { id: "", name: t("新预设"), document: { ...defaults } };
      if (active && presetLoad === presetRequest.current) { loadPreset(initial); setLoaded(true); }
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
  useEffect(() => {
    const abort = new AbortController();
    api<LibraryListing>("/api/candidate/library", { signal: abort.signal }).then(setLibrary)
      .catch(error => { if (!abort.signal.aborted) setLibraryError(message(error)); });
    return () => abort.abort();
  }, []);
  const refreshLibrary = async () => {
    const request = ++libraryRequest.current;
    const listing = await api<LibraryListing>("/api/candidate/library");
    const info = await api<Record<string, unknown>>("/api/candidate/dataset");
    if (request !== libraryRequest.current) return;
    setLibrary(listing); updateDataset(info); setPage(1); setTags({ tags: [], total: 0, page: 1, page_size: DEFAULT_PAGE_SIZE });
    setRefresh(value => value + 1); setLibraryRevision(value => value + 1); setResult(null);
  };
  useEffect(() => {
    const changed = () => { refreshLibrary().catch(error => setLibraryError(message(error))); };
    document.addEventListener("pictide:candidate-library-changed", changed);
    return () => { document.removeEventListener("pictide:candidate-library-changed", changed); libraryRequest.current++; };
  }, []);
  const libraryOperation = async (action: string, filename?: string, file?: File) => {
    setBusy(true); setLibraryAction(action); setLibraryError("");
    try {
      if (file) {
        const body = new FormData(); body.append("file", file);
        const response = await fetch("/api/candidate/library", { method: "POST", body });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || tr`请求失败（${response.status}）`);
        filename = (data as Library).filename;
      }
      if (filename) await api("/api/candidate/library", { method: "PUT", body: JSON.stringify({ filename }) });
      await refreshLibrary();
    } catch (error) { setLibraryError(message(error)); }
    finally { setBusy(false); setLibraryAction(""); }
  };
  const update = <K extends keyof PresetDocument>(key: K, value: PresetDocument[K]) => { setPreset(current => ({ ...current, document: { ...current.document, [key]: value } })); setSuccess(false); };
  const discard = async () => !dirty || await confirmAction(t("当前预设有未保存的修改，继续会放弃这些修改。"));
  const selectPreset = async (id: string) => {
    if (id === preset.id || !(await discard())) return;
    const request = ++presetRequest.current;
    setBusy(true); setNotice("");
    try {
      const next = await api<Preset>(`/api/candidate/presets/${encodeURIComponent(id)}`);
      if (request !== presetRequest.current) return;
      await activatePreset(id);
      loadPreset(next); setResult(null); setSuccess(false); setLoaded(true);
    } catch (error) { if (request === presetRequest.current) setNotice(message(error)); }
    finally { if (request === presetRequest.current) setBusy(false); }
  };
  const create = async (copy = false) => {
    if (!copy && !(await discard())) return;
    presetRequest.current++;
    const source = copy ? { ...preset, id: "", name: tr`${preset.name} 副本`, document: structuredClone(preset.document) } : { id: "", name: t("新预设"), document: { ...defaults } };
    const next = withCooccurrenceFloor(source, cooccurrenceFloor.current);
    setPreset(next); setBlockedText(next.document.blocked_keywords.join("\n"));
    setSaved(""); setResult(null); setSuccess(false); setLoaded(true); setTab("settings");
  };
  const validate = (preset: Preset) => {
    if (!preset.name.trim()) throw new Error(t("请输入预设名称。"));
    for (const [key, value] of Object.entries(preset.document)) {
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error(tr`${key} 需要有效数值。`);
    }
    if ([...preset.document.base_positive, ...preset.document.base_negative].some(text => !text.trim())) throw new Error(t("固定提示词不能为空，请填写或移除空项。"));
    if (!Number.isInteger(preset.document.min_tags) || preset.document.min_tags < 1) throw new Error(t("标签数量下限须为至少 1 的整数。"));
    if (preset.document.min_tags > preset.document.max_tags) throw new Error(t("标签数量下限不能大于上限。"));
    if (preset.document.base_positive.length > preset.document.max_tags) throw new Error(t("固定正向词数量超过标签上限。"));
  };
  const save = async () => {
    setBusy(true); setNotice(""); setSuccess(false);
    try {
      const draft = withCooccurrenceFloor(preset, cooccurrenceFloor.current);
      setPreset(draft); validate(draft);
      const next = await api<Preset>("/api/candidate/presets", { method: "POST", body: JSON.stringify({ ...draft, id: draft.id || undefined }) });
      loadPreset(next); setLoaded(true);
      const listing = await api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"); setPresets(listing.presets);
      document.dispatchEvent(new Event("pictide:candidate-presets-changed"));
      await activatePreset(next.id);
      setSuccess(next.document.min_cooccurrence >= cooccurrenceFloor.current);
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!preset.id || !(await confirmAction(tr`删除预设“${preset.name}”？此操作无法撤销。`))) return;
    setBusy(true); setNotice("");
    try {
      await api(`/api/candidate/presets/${encodeURIComponent(preset.id)}`, { method: "DELETE", body: "{}" });
      const listing = await api<{ presets: { id: string; name: string }[] }>("/api/candidate/presets"); setPresets(listing.presets);
      const next = listing.presets[0] ? await api<Preset>(`/api/candidate/presets/${encodeURIComponent(listing.presets[0].id)}`) : { id: "", name: t("新预设"), document: { ...defaults } };
      loadPreset(next); setResult(null); setSuccess(false);
      document.dispatchEvent(new Event("pictide:candidate-presets-changed"));
      await activatePreset(next.id);
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const preview = async () => {
    setBusy(true); setNotice("");
    try {
      const draft = withCooccurrenceFloor(preset, cooccurrenceFloor.current);
      setPreset(draft); validate(draft);
      const next = await api<Result>("/api/candidate/generate", { method: "POST", body: JSON.stringify({ preset_id: draft.id || "draft", document: draft.document, mode, seed, sequence_step: mode === "sequence" ? step : 0, max_steps: maxSteps }) });
      setResult(next);
      if (mode !== "random_each_run") setSeed(counterAfter(mode === "sequence" ? next.sequence?.seed ?? seed : next.seed, seedControl, Number.MAX_SAFE_INTEGER));
      if (mode === "sequence") setStep(counterAfter(step, stepControl, 1000));
    } catch (error) { setNotice(message(error)); } finally { setBusy(false); }
  };
  const controlOptions = [{ value: "fixed", text: t("固定") }, { value: "increment", text: t("递增") }, { value: "decrement", text: t("递减") }, { value: "randomize", text: t("随机") }];
  const numberField = (key: keyof Omit<PresetDocument, "base_positive" | "base_negative" | "blocked_keywords">, label: string, help: string, min?: number, max?: number, increment: number | "any" = 1) => <Field label={label} help={help}><Input aria-label={label} type="number" min={min} max={max} step={increment} value={Number.isNaN(preset.document[key]) ? "" : preset.document[key]} required disabled={busy} onChange={event => update(key, event.target.valueAsNumber)} onBlur={key === "min_cooccurrence" ? () => setPreset(current => withCooccurrenceFloor(current, cooccurrenceFloor.current)) : undefined} /></Field>;
  const pages = Math.max(1, Math.ceil(tags.total / tags.page_size));
  return <section id="prompts-view" className="editor-page workspace-content" aria-label={t("提示词")} hidden>
    <header className="editor-toolbar"><h1>{t("提示词")}</h1><span className="spacer" /><Badge variant="secondary" data-tooltip={tr`数据来源：${String(dataset.source || t("尚未导入"))}`}>{dataset.status === "ready" ? t("词库就绪") : t("词库未就绪")}</Badge></header>
    <Tabs value={tab} onValueChange={setTab}><nav className="editor-tabs" aria-label={t("提示词栏目")}><TabsList><TabsTrigger value="library">{t("词库")}</TabsTrigger><TabsTrigger value="settings">{t("编排")}</TabsTrigger><TabsTrigger value="preview">{t("预览")}</TabsTrigger></TabsList></nav></Tabs>
    {notice && <div className="notice error" role="alert">{notice}</div>}
    <main>
      {tab === "library" ? <section className="cooc-library">
        <div className="cooc-library-filters">
          <div className="cooc-library-toolbar">
            <div className="cooc-library-selection">
              <Select value={library.selected || undefined} onValueChange={filename => void libraryOperation("select", filename)} disabled={busy || !library.libraries.length}>
                <SelectTrigger aria-label={t("当前词库")}><SelectValue placeholder={t("选择词库")} /></SelectTrigger>
                <SelectContent>{library.libraries.map(item => <SelectItem key={item.filename} value={item.filename}>{item.filename}</SelectItem>)}</SelectContent>
              </Select>
              <HelpTip text={t("上传词库文件，或放入 data/libraries/ 后刷新选择。支持 .sqlite3 和 .sqlite3.gz，选中立即生效。")} />
            </div>
            <div className="cooc-library-actions">
              <input ref={libraryInput} type="file" hidden accept=".sqlite3,.sqlite3.gz" aria-label={t("选择词库文件")} onChange={event => {
                const file = event.target.files?.[0]; event.target.value = "";
                if (file) void libraryOperation("upload", undefined, file);
              }} />
              <IconButton icon={libraryAction === "upload" ? LoaderCircle : Upload} className={libraryAction === "upload" ? "[&>svg]:animate-spin" : ""} label={libraryAction === "upload" ? t("正在上传词库") : t("上传词库")} onClick={() => libraryInput.current?.click()} disabled={busy} />
              <IconButton icon={libraryAction === "refresh" ? LoaderCircle : RefreshCw} className={libraryAction === "refresh" ? "[&>svg]:animate-spin" : ""} label={t("刷新词库")} onClick={() => void libraryOperation("refresh")} disabled={busy || tagLoading} />
            </div>
          </div>
          <Input className="cooc-library-search" aria-label={t("搜索词库标签")} placeholder={t("搜索标签")} value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} />
        </div>
        {libraryAction === "select" && <p className="text-xs text-muted-foreground" role="status">{t("正在切换词库…")}</p>}
        {libraryError && <p className="cooc-error" role="alert">{libraryError}</p>}
        {tagError && <p className="cooc-error" role="alert">{tagError}</p>}
        <div className="cooc-tags" aria-busy={tagLoading}>{tagLoading ? <div className="cooc-empty" role="status"><LoaderCircle className="size-4 animate-spin" />{t("加载中")}</div> : tags.tags.length ? tags.tags.map(tag => <div className="cooc-tag" key={tag.id}><span className="min-w-0 break-words" data-tooltip={["general", "sensitive", "questionable", "explicit"].includes(tag.name) ? t("图片评级标签，可添加为固定正向词以参与共现筛选。") : undefined}>{tag.name}</span><span className="cooc-frequency" data-tooltip={t("数据集中包含此标签的图片数量")}>{tag.post_count.toLocaleString(locale())}</span></div>) : <p className="cooc-empty">{query ? t("没有匹配标签") : t("上传或选择词库，开始浏览标签。")}</p>}</div>
        <PageControls label={t("词库")} page={page} totalPages={pages} loading={tagLoading} onPageChange={setPage} />
      </section> : <>
        <div className="cooc-preset-toolbar"><Choice label={t("生成预设")} value={preset.id || "__new"} onChange={selectPreset} disabled={busy} options={[...presets.map(item => ({ value: item.id, text: item.name })), ...(!preset.id ? [{ value: "__new", text: t("未保存预设") }] : [])]} /><HelpTip text={t("切换预设后用于漫游和生成；编辑内容保存后生效，预览可使用未保存的草稿。")} /><IconButton icon={Plus} label={t("新建预设")} disabled={busy} onClick={() => create()} /><IconButton icon={Copy} label={t("复制预设")} disabled={busy || !loaded} onClick={() => create(true)} /><IconButton icon={Trash2} label={t("删除预设")} disabled={busy || !preset.id} onClick={remove} /><span className="spacer" /><span className="text-xs text-muted-foreground" role="status">{loaded && dirty ? t("未保存") : ""}</span><Button disabled={busy || !dirty} onClick={save} data-tooltip={t("保存当前预设，包括固定词、输出顺序和共现扩展设置。")}>{busy ? <LoaderCircle className="animate-spin" /> : success ? <Check /> : <Save />}{success ? t("已保存") : t("保存")}</Button></div>
        {tab === "settings" ? <form className="cooc-settings" onSubmit={event => { event.preventDefault(); save(); }}>
          <Field label={t("预设名称")}><Input aria-label={t("预设名称")} value={preset.name} disabled={busy} required onChange={event => { setPreset(current => ({ ...current, name: event.target.value })); setSuccess(false); }} /></Field>
          <section className="cooc-positive-settings" aria-label={t("正向生成")}>
            <FixedTags key={`positive:${libraryRevision}`} positive label={t("固定正向词")} values={preset.document.base_positive} disabled={busy} onChange={values => update("base_positive", values)} />
            <div className="cooc-section-heading"><h2>{t("共现扩展")}</h2><HelpTip text={t("根据标签共同出现的情况扩展正向提示词。统计相关不保证画面协调。")} /></div>
            <div className="cooc-number-grid">
              {numberField("min_tags", t("标签数量下限"), t("在上下限之间等概率抽取目标数量；无法达到时返回已生成的内容。"), 1, 1000)}
              {numberField("max_tags", t("标签数量上限"), t("数量包含固定正向词。固定词超过下限时，以固定词数作为有效下限。"), 1, 1000)}
              {numberField("pmi_threshold", t("PMI 阈值"), t("新标签与每个已有可统计正向标签的 PMI 都须达到此值。0 为独立预期，正数更常共同出现，负数更少。"), undefined, undefined, "any")}
              {numberField("min_cooccurrence", t("最低共现次数"), tr`每对标签须共同出现至少此次数，并且关系已收录于当前词库。当前词库下限为 ${minCooccurrence} 次。`, minCooccurrence, Number.MAX_SAFE_INTEGER)}
              {numberField("change_budget", t("连续变化预算"), t("限制连续序列和顺流漫游每帧的标签增删数，替换计 2 次。固定词保留；无合法变化时保持上一帧，预算 0 不变。"), 0, 1000)}
            </div>
            <Field label={t("屏蔽关键词")} help={t("跳过包含关键词的新抽取标签。固定正负词与停泊保持的提示词不重新过滤。")}>
              <Textarea aria-label={t("屏蔽关键词")} data-tooltip={t("每行一个关键词；忽略大小写，空格与下划线等价。")} placeholder={t("每行一个关键词，例如：\nhair\nblack socks")} rows={3} disabled={busy} value={blockedText} onChange={event => {
                const text = event.target.value;
                setBlockedText(text);
                update("blocked_keywords", [...new Set(text.split(/\r?\n/).map(item => item.trim()).filter(Boolean))]);
              }} />
            </Field>
          </section>
          <Collapsible className="cooc-negative-settings">
            <div className="cooc-section-heading">
              <CollapsibleTrigger asChild><Button variant="ghost" size="sm" className="group px-0 font-semibold hover:bg-transparent" aria-label={t("负向提示词")}><ChevronRight className="size-4 transition-transform group-data-[state=open]:rotate-90" />{t("负向提示词")}{preset.document.base_negative.length > 0 && <Badge variant="secondary">{preset.document.base_negative.length}</Badge>}</Button></CollapsibleTrigger>
              <HelpTip text={t("用于生图；共现扩展跳过同名词，不参与 PMI 计算。")} />
            </div>
            <CollapsibleContent forceMount className="data-[state=closed]:hidden">
              <FixedTags key={`negative:${libraryRevision}`} label={t("固定负向词")} values={preset.document.base_negative} disabled={busy} onChange={values => update("base_negative", values)} />
            </CollapsibleContent>
          </Collapsible>
          <button type="submit" hidden />
        </form> : <section className="cooc-preview">
          <Collapsible className="cooc-preview-options">
            <div className="cooc-preview-toolbar">
              <Field label={t("生成模式")}>
                <Choice label={t("预览生成模式")} value={mode} onChange={value => setMode(value as Mode)} options={[{ value: "random_each_run", text: t("每次随机") }, { value: "fixed_seed", text: t("固定种子") }, { value: "sequence", text: t("连续序列") }]} disabled={busy} />
              </Field>
              <div className="cooc-preview-actions">
                <CollapsibleTrigger asChild><Button variant="ghost" size="sm"><Settings2 />{t("搜索设置")}</Button></CollapsibleTrigger>
                <Button variant="secondary" disabled={busy || !loaded} onClick={preview} data-tooltip={t("使用当前预设草稿生成提示词，不生成图片，也不保存修改。")}>{busy ? <LoaderCircle className="animate-spin" /> : <Sparkles />}{t("预览")}</Button>
              </div>
            </div>
            {mode !== "random_each_run" && <div className="cooc-preview-parameters">
              <div className="cooc-preview-parameter-group">
                <Field label={t("提示词种子")}><Input aria-label={t("预览提示词种子")} type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} value={seed} disabled={busy} onChange={event => setSeed(event.target.valueAsNumber)} /></Field>
                <Field label={t("种子生成后")}><Choice label={t("预览种子生成后")} value={seedControl} onChange={setSeedControl} options={controlOptions} disabled={busy} /></Field>
              </div>
              {mode === "sequence" && <div className="cooc-preview-parameter-group">
                <Field label={t("帧序号")}><Input aria-label={t("预览帧序号")} type="number" min={0} max={1000} step={1} value={step} disabled={busy} onChange={event => setStep(event.target.valueAsNumber)} /></Field>
                <Field label={t("帧序号生成后")}><Choice label={t("预览帧序号生成后")} value={stepControl} onChange={setStepControl} options={controlOptions} disabled={busy} /></Field>
              </div>}
            </div>}
            <CollapsibleContent>
              <div className="cooc-preview-search"><Field label={t("搜索上限")} help={t("所有模式共用的搜索步数上限。达到上限时返回已生成的提示词。") }><Input aria-label={t("预览搜索上限")} type="number" min={1} max={1000000} value={maxSteps} step={1} disabled={busy} onChange={event => setMaxSteps(event.target.valueAsNumber)} /></Field></div>
            </CollapsibleContent>
          </Collapsible>
          {result ? <section className="cooc-preview-results" aria-label={t("预览结果")}>
            <div className="cooc-result-summary">
              <Badge variant="secondary">{t(stopReasons[String(result.report.stop_reason)] || String(result.report.stop_reason || "已生成"))}</Badge>
              <span className="cooc-preview-meta">{tr`种子 ${result.seed}`}</span>
              {result.sequence && <span className="cooc-preview-meta">{tr`帧 ${result.sequence.step ?? step} · 变化 ${result.sequence.changes ?? 0} / ${result.sequence.change_budget ?? preset.document.change_budget}`}</span>}
            </div>
            {Array.isArray(result.report.unrecognized_fixed) && result.report.unrecognized_fixed.length > 0 && <p className="text-xs text-muted-foreground" role="status">{tr`未参与共现计算：${result.report.unrecognized_fixed.join(", ")}`}</p>}
            <PreviewPrompts key={result.candidate_id} terms={result.selected_tags} positive={result.positive} negative={result.negative} />
            <Collapsible className="cooc-preview-report">
              <CollapsibleTrigger asChild><Button variant="ghost" size="sm" className="group"><ChevronRight className="size-4 transition-transform group-data-[state=open]:rotate-90" />{t("生成报告")}</Button></CollapsibleTrigger>
              <CollapsibleContent><pre className="cooc-report">{JSON.stringify({ selected_tags: result.selected_tags, sequence: result.sequence, ...result.report }, null, 2)}</pre></CollapsibleContent>
            </Collapsible>
          </section> : <p className="cooc-empty">{t("预览当前预设，不生成图片。")}</p>}
        </section>}
      </>}
    </main>
  </section>;
}
