import { emitSignal } from '../shared/signals.mjs';
import { useUiFact } from '../shared/application-context';
import { useVocabularySearch } from '../shared/use-vocabulary-search';
import { runUiCommand } from '../shared/ui-state.mjs';
import { useErrorNotice } from "./notifications";
import { getUiState, publishUiState, subscribeUiState } from "../shared/ui-state.mjs";
import { uiTarget } from "../shared/ui-targets";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactElement, type ReactNode } from "react";
import { Anchor, LoaderCircle, LockKeyhole, Plus, Trash2, X } from "lucide-react";
import { t, tr } from "../i18n/index.mjs";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "./ui/popover";
import { ImageToolbarPopover } from "./image-toolbar-popover";
import { HelpTip } from "./actions";
import { RoamCanvas } from "./roam-canvas";
import { anchorTerms } from "../controllers/roam-anchors.mjs";

type AnchorSettings = { pinned_positive: string[]; preset_base_positive: string[]; prompt_mode: string };
const normalize = (text: string) => text.trim().replaceAll("_", " ");

export function RoamAnchors({ children }: { children: (trigger: ReactNode, panel: ReactNode) => ReactElement }) {
  const facts = useSyncExternalStore(subscribeUiState, getUiState) as Record<string, unknown>;
  const immersive = facts.roamImmersive === true;
  const value = useUiFact("roamOptions");
  const settings: AnchorSettings = { pinned_positive: value?.pinned_positive ?? [], preset_base_positive: value?.preset_base_positive ?? [], prompt_mode: value?.prompt_mode ?? "random" };
  const positive = useUiFact("imageInfo")?.sourcePositive ?? "";
  const [query, setQuery] = useState("");
  const ready = !!value;
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const navigating = useRef(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  useErrorNotice(error, { id: "roam-anchors" });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const targets = useMemo(() => ({ trigger: uiTarget("anchors.trigger"), terms: uiTarget("anchors.terms"), clear: uiTarget("anchors.clear"), mobileClear: uiTarget("anchors.clear") }), []);
  const triggerTarget = useCallback((element: HTMLButtonElement | null) => { triggerRef.current = element; targets.trigger(element); }, [targets]);
  const previousPins = useRef<string | null>(null);
  const anchorRevision = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (adding && open) inputRef.current?.focus(); }, [adding, open]);
  const fixed = new Set(settings.preset_base_positive.map(normalize));
  const pins = settings.pinned_positive.map(normalize).filter(text => !fixed.has(text));
  const pinned = new Set(pins);
  const terms: string[] = anchorTerms(positive, pins, settings.preset_base_positive);
  const locked = settings.prompt_mode === "stay";
  const disabled = !ready || locked || pending !== null;
  const suggestionsOpen = searchOpen && open && !disabled && facts.route === "feed";
  const { matches, error: searchError, loading } = useVocabularySearch(query, suggestionsOpen);
  useErrorNotice(searchError ? `${t("词库暂不可用，仍可输入提示词并回车添加")} · ${searchError}` : "", { id: "anchor-tag-search", visible: suggestionsOpen });
  const excluded = new Set([...settings.preset_base_positive, ...pins].map(text => normalize(text).toLowerCase()));
  const options = matches.filter(tag => !excluded.has(normalize(tag.name).toLowerCase()));
  const custom = query.trim() && !excluded.has(normalize(query).toLowerCase()) && !matches.some(tag => normalize(tag.name).toLowerCase() === normalize(query).toLowerCase());
  useEffect(() => { setSearchOpen(false); navigating.current = false; }, [open, immersive]);
  const signature = JSON.stringify(pins);
  useEffect(() => {
    if (ready && previousPins.current !== signature) {
      if (previousPins.current !== null) anchorRevision.current++;
      previousPins.current = signature;
    }
    publishUiState({ anchorOpen: open, anchorCount: pins.length, anchorsEditable: ready && !locked && pending === null, anchorRevision: anchorRevision.current });
  }, [open, ready, locked, pending, signature]);
  const save = async (text: string | null, addOnly = false) => {
    if (!ready || locked || pending !== null) return false;
    if (addOnly && text !== null && excluded.has(normalize(text).toLowerCase())) return true;
    const next = text === null ? [] : pinned.has(text) ? pins.filter(value => value !== text) : [...pins, text];
    setPending(text ?? ""); setError("");
    try {
      await runUiCommand('roam-settings-save', { pinned_positive: next });
      return true;
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); return false; }
    finally { setPending(null); }
  };
  const add = async (value = query) => {
    const text = normalize(value);
    if (text && await save(text, true)) { setQuery(""); setAdding(false); setSearchOpen(false); navigating.current = false; }
  };
  const triggerButton = <Button ref={triggerTarget} variant={open ? "secondary" : "ghost"} size="icon-sm" className="roam-anchor-trigger" aria-label={t("锚点")} aria-pressed={open} data-tooltip={t("锚点")} onClick={() => { if (!open) emitSignal("close-image-info"); }}>
      <Anchor aria-hidden="true" />{pins.length > 0 && <span className="roam-anchor-count">{pins.length}</span>}
    </Button>;
  const trigger = immersive ? <PopoverTrigger asChild>{triggerButton}</PopoverTrigger> : <CollapsibleTrigger asChild>{triggerButton}</CollapsibleTrigger>;
  const content = <>
    <div className="roam-anchor-heading">
      <span className="font-medium">{t("锚点")}</span><Badge variant="secondary">{pins.length}</Badge>
      <HelpTip text={locked ? t("停泊保持整组提示词，切换漫游方式后可编辑锚点。") : t("点选正向词，让后续图片保留这个元素；修改后清空旧预取。")} />
      <div className="ml-auto flex items-center gap-1">
        {pins.length > 0 && <Button variant="ghost" size="icon-sm" ref={targets.clear} aria-label={t("清空锚点")} data-tooltip={t("清空锚点")} disabled={!ready || locked || pending !== null} onClick={() => save(null)}>
          {pending === "" ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
        </Button>}
        <Button variant="ghost" size="icon-sm" aria-label={t("收起锚点")} data-tooltip={t("收起锚点")} onClick={() => { setOpen(false); triggerRef.current?.focus({ preventScroll: true }); }}><X aria-hidden="true" /></Button>
      </div>
    </div>
    <Command shouldFilter={false} loop className="roam-anchor-add h-auto w-auto overflow-visible bg-transparent p-0" data-open={adding}>
      <Popover open={suggestionsOpen} onOpenChange={setSearchOpen}>
        <PopoverAnchor asChild><div className="roam-anchor-entry">
          <div className="roam-anchor-query min-w-0 flex-1"><CommandInput ref={inputRef} value={query}
            onValueChange={text => { setQuery(text); setSearchOpen(true); navigating.current = false; }}
            onFocus={() => setSearchOpen(true)} onClick={() => setSearchOpen(true)} aria-expanded={suggestionsOpen}
            aria-label={t("添加锚点")} placeholder={t("输入提示词，回车添加")}
            data-tooltip={t("输入完整提示词并回车添加，也可选择词库匹配项。")}
            disabled={disabled} onKeyDown={event => {
              if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
                if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); }
                return;
              }
              if (event.key === "ArrowDown" || event.key === "ArrowUp") { navigating.current = true; setSearchOpen(true); }
              if (event.key === "Enter" && query.trim() && (!navigating.current || !suggestionsOpen || !options.length)) {
                event.preventDefault(); event.stopPropagation(); void add();
              }
            }} /></div>
          <Button variant="ghost" size="icon-sm" aria-label={t("添加锚点")} data-tooltip={t("添加锚点")}
            disabled={disabled} onClick={() => { if (query.trim()) void add(); else { setAdding(true); inputRef.current?.focus(); } }}>
            {pending !== null && pending === normalize(query) ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
          </Button>
          {pins.length > 0 && <Button ref={targets.mobileClear} className="roam-anchor-mobile-clear" variant="ghost" size="icon-sm" aria-label={t("清空锚点")} data-tooltip={t("清空锚点")} disabled={disabled} onClick={() => save(null)}>
            {pending === "" ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
          </Button>}
        </div></PopoverAnchor>
        <PopoverContent className="roam-anchor-suggestions gap-0 p-0" align="start" side={immersive ? "top" : "bottom"} collisionPadding={12}
          container={immersive ? inputRef.current?.closest<HTMLElement>(".image-card") : undefined}
          onOpenAutoFocus={event => event.preventDefault()} onCloseAutoFocus={event => event.preventDefault()}
          onInteractOutside={event => { if (event.target instanceof Element && event.target.closest(".roam-anchor-entry")) event.preventDefault(); }}
          onEscapeKeyDown={event => { event.preventDefault(); event.stopPropagation(); setSearchOpen(false); }}
          onMouseDown={event => event.preventDefault()}>
          <CommandList label={t("锚点匹配项")}>
            {loading ? <div role="status" className="px-3 py-2 text-sm text-muted-foreground">{t("搜索中…")}</div> : <CommandEmpty>{t("没有匹配标签")}</CommandEmpty>}
            <CommandGroup>
              {custom && <CommandItem value="__custom" onSelect={() => void add()}><span className="min-w-0 flex-1 break-words">{tr`添加：${query}`}</span></CommandItem>}
              {options.map(tag => <CommandItem key={tag.id} value={String(tag.id)} onSelect={() => void add(tag.name)}><span className="min-w-0 flex-1 break-words">{tag.name}</span></CommandItem>)}
            </CommandGroup>
          </CommandList>
        </PopoverContent>
      </Popover>
    </Command>
    <div ref={targets.terms} className="roam-anchor-terms">
      {terms.map(text => {
        const fromPreset = fixed.has(text), selected = pinned.has(text);
        const label = fromPreset ? t("来自预设") : selected ? t("取消锚点") : t("设为锚点");
        return <Button key={text} variant={selected ? "secondary" : "outline"} size="sm" className="roam-anchor-term" aria-label={text + " · " + label} aria-pressed={selected} data-tooltip={label} disabled={!ready || locked || fromPreset || pending !== null} onClick={() => save(text)}>
          {pending === text ? <LoaderCircle className="size-3 animate-spin" /> : fromPreset ? <LockKeyhole className="size-3" /> : selected ? <Anchor className="size-3" /> : null}
          <span>{text}</span>
        </Button>;
      })}
    </div>
    <RoamCanvas />
  </>;
  const panel = immersive ? <ImageToolbarPopover immersive triggerRef={triggerRef}
    className="roam-anchors roam-anchor-popover" aria-label={t("锚点")}
    onInteractOutside={event => {
      const target = event.target instanceof Element ? event.target : null;
      // Keep editing while navigating/rating images from the same toolbar.
      if (target?.closest(".roam-anchor-suggestions, .roam-canvas-options") || (target?.closest(".image-toolbar") && !target.closest(".image-info"))) event.preventDefault();
    }}>{content}</ImageToolbarPopover> : <>
    {open && <AnchorDivider />}
    <CollapsibleContent className="roam-anchors" role="region" aria-label={t("锚点")}>{content}</CollapsibleContent>
  </>;
  return <Popover open={immersive && open} onOpenChange={next => { if (immersive) setOpen(next); }}>
    <Collapsible open={!immersive && open} onOpenChange={setOpen} asChild>{children(trigger, panel)}</Collapsible>
  </Popover>;
}

function AnchorDivider() {
  const ref = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(30);
  const apply = (value: number, persist = false) => {
    const next = Math.max(20, Math.min(50, value));
    ref.current?.closest<HTMLElement>(".roam-image-card")?.style.setProperty("--anchor-panel-ratio", `${next}%`);
    setRatio(next);
    if (persist) { try { localStorage.setItem("pictide:anchor-panel-ratio", String(next)); } catch {} }
  };
  useEffect(() => {
    try { const saved = Number(localStorage.getItem("pictide:anchor-panel-ratio")); if (saved >= 20 && saved <= 50) apply(saved); } catch {}
  }, []);
  return <div ref={ref} className="roam-anchor-divider" role="separator" tabIndex={0} aria-label={t("调整锚点区域宽度")} aria-orientation="vertical" aria-valuemin={20} aria-valuemax={50} aria-valuenow={Math.round(ratio)}
    onPointerDown={event => { if (event.button === 0) { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); } }}
    onPointerMove={event => {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      const bounds = event.currentTarget.closest(".roam-image-card")!.getBoundingClientRect();
      apply((bounds.right - event.clientX) / bounds.width * 100);
    }}
    onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) { event.currentTarget.releasePointerCapture(event.pointerId); apply(ratio, true); } }}
    onKeyDown={event => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault(); event.stopPropagation();
        apply(event.key === "Home" ? 20 : event.key === "End" ? 50 : ratio + (event.key === "ArrowLeft" ? 2 : -2), true);
      }
    }} />;
}
