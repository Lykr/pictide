import { useEffect, useRef, useState, type ReactElement, type ReactNode } from "react";
import { LoaderCircle, LockKeyhole, Pin, Plus, Trash2, X } from "lucide-react";
import { t } from "../i18n/index.mjs";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Input } from "./ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { HelpTip } from "./actions";
import { anchorTerms } from "../controllers/roam-anchors.mjs";

type AnchorSettings = { pinned_positive: string[]; preset_base_positive: string[]; prompt_mode: string };
const normalize = (text: string) => text.trim().replaceAll("_", " ");

export function RoamAnchors({ children }: { children: (trigger: ReactNode, panel: ReactNode) => ReactElement }) {
  const [settings, setSettings] = useState<AnchorSettings>({ pinned_positive: [], preset_base_positive: [], prompt_mode: "random" });
  const [positive, setPositive] = useState("");
  const [query, setQuery] = useState("");
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const receive = (event: Event) => {
      const value = (event as CustomEvent<AnchorSettings>).detail;
      setSettings({ pinned_positive: value.pinned_positive ?? [], preset_base_positive: value.preset_base_positive ?? [], prompt_mode: value.prompt_mode });
      setReady(true);
    };
    const image = (event: Event) => setPositive((event as CustomEvent<{ positive: string } | null>).detail?.positive ?? "");
    document.addEventListener("pictide:roam-options-settings", receive);
    document.addEventListener("pictide:image-info", image);
    return () => {
      document.removeEventListener("pictide:roam-options-settings", receive);
      document.removeEventListener("pictide:image-info", image);
    };
  }, []);
  const fixed = new Set(settings.preset_base_positive.map(normalize));
  const pins = settings.pinned_positive.map(normalize).filter(text => !fixed.has(text));
  const pinned = new Set(pins);
  const terms: string[] = anchorTerms(positive, pins, settings.preset_base_positive);
  const locked = settings.prompt_mode === "stay";
  const save = async (text: string | null, addOnly = false) => {
    if (!ready || locked || pending !== null) return false;
    if (addOnly && text !== null && (fixed.has(text) || pinned.has(text))) return true;
    const next = text === null ? [] : pinned.has(text) ? pins.filter(value => value !== text) : [...pins, text];
    setPending(text ?? ""); setError("");
    try {
      await new Promise((resolve, reject) => document.dispatchEvent(new CustomEvent("pictide:roam-settings-save", {
        detail: { patch: { pinned_positive: next }, resolve, reject },
      })));
      return true;
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); return false; }
    finally { setPending(null); }
  };
  const add = async () => {
    const text = normalize(query);
    if (text && await save(text, true)) setQuery("");
  };
  const trigger = <CollapsibleTrigger asChild>
    <Button ref={triggerRef} variant={open ? "secondary" : "ghost"} size="sm" className="roam-anchor-trigger" aria-label={t("锚点")} aria-pressed={open} data-tooltip={t("锚点")}>
      <Pin aria-hidden="true" /><span className="roam-anchor-count">{pins.length}</span>
    </Button>
  </CollapsibleTrigger>;
  const panel = <CollapsibleContent className="roam-anchors" role="region" aria-label={t("锚点")}>
    <div className="roam-anchor-heading">
      <span className="font-medium">{t("锚点")}</span><Badge variant="secondary">{pins.length}</Badge>
      <HelpTip text={locked ? t("停泊保持整组提示词，切换漫游方式后可编辑锚点。") : t("点选正向词，让后续图片保留这个元素；修改后清空旧预取。")} />
      <div className="ml-auto flex items-center gap-1">
        {pins.length > 0 && <Button variant="ghost" size="icon-sm" aria-label={t("清空锚点")} data-tooltip={t("清空锚点")} disabled={!ready || locked || pending !== null} onClick={() => save(null)}>
          {pending === "" ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
        </Button>}
        <Button variant="ghost" size="icon-sm" aria-label={t("收起锚点")} data-tooltip={t("收起锚点")} onClick={() => { setOpen(false); triggerRef.current?.focus({ preventScroll: true }); }}><X aria-hidden="true" /></Button>
      </div>
    </div>
    <div className="flex items-center gap-2 px-2 pt-2">
      <Input className="min-w-0 flex-1" value={query} onChange={event => setQuery(event.target.value)}
        aria-label={t("添加锚点")} placeholder={t("输入提示词，回车添加")}
        data-tooltip={t("输入完整提示词并回车添加；自定义词不参与 PMI 计算。")}
        disabled={!ready || locked || pending !== null} onKeyDown={event => {
          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
            event.preventDefault(); event.stopPropagation(); void add();
          }
        }} />
      <Button variant="ghost" size="icon-sm" aria-label={t("添加锚点")} data-tooltip={t("添加锚点")}
        disabled={!ready || locked || pending !== null || !query.trim()} onClick={() => void add()}>
        {pending !== null && pending === normalize(query) ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
      </Button>
    </div>
    <div className="roam-anchor-terms">
      {terms.map(text => {
        const fromPreset = fixed.has(text), selected = pinned.has(text);
        const label = fromPreset ? t("来自预设") : selected ? t("取消锚点") : t("设为锚点");
        return <Button key={text} variant={selected ? "secondary" : "outline"} size="sm" className="roam-anchor-term" aria-label={text + " · " + label} aria-pressed={selected} data-tooltip={label} disabled={!ready || locked || fromPreset || pending !== null} onClick={() => save(text)}>
          {pending === text ? <LoaderCircle className="size-3 animate-spin" /> : fromPreset ? <LockKeyhole className="size-3" /> : selected ? <Pin className="size-3" /> : null}
          <span>{text}</span>
          {fromPreset && <span className="text-xs text-muted-foreground">{t("来自预设")}</span>}
        </Button>;
      })}
    </div>
    {error && <p role="alert" className="px-2 pb-2 text-sm text-destructive">{error}</p>}
  </CollapsibleContent>;
  return <Collapsible open={open} onOpenChange={setOpen} asChild>{children(trigger, panel)}</Collapsible>;
}
