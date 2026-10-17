import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Settings2 } from "lucide-react";
import { Button } from "./ui/button";
import { IconButton, HelpTip } from "./actions";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./ui/input-group";
import { Label } from "./ui/label";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { playbackInterval } from "../controllers/roam-playback.mjs";

type PlaybackState = { playing: boolean; canPlay: boolean; startedAt: number | null; durationMs: number; cycle: number; waiting: boolean };
function usePlaybackState() {
  const [state, setState] = useState<PlaybackState>({ playing: false, canPlay: false, startedAt: null, durationMs: 5000, cycle: 0, waiting: false });
  useEffect(() => {
    const receive = (event: Event) => setState((event as CustomEvent<PlaybackState>).detail);
    document.addEventListener("pictide:roam-playback-state", receive);
    return () => document.removeEventListener("pictide:roam-playback-state", receive);
  }, []);
  return state;
}
export function RoamPlaybackButton({ menu = false, visible = true }: { menu?: boolean; visible?: boolean }) {
  const state = usePlaybackState();
  const label = state.playing ? "暂停播放" : "自动播放";
  const delay = useMemo(() => state.startedAt === null ? 0 : -Math.max(0, performance.now() - state.startedAt), [state.startedAt, state.cycle, visible]);
  return <Button id={menu ? "roam-options-playback" : "roam-playback"} type="button" variant="ghost" size="icon-sm" className="relative" aria-label={label} data-tooltip={label} aria-pressed={state.playing} disabled={!state.canPlay} onClick={() => document.dispatchEvent(new Event("pictide:roam-playback-toggle"))}>
    {state.playing && <svg className="playback-progress absolute left-1/2 top-1/2 size-8 -translate-x-1/2 -translate-y-1/2 -rotate-90" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="1.5" opacity="0.15" />
      <circle key={`${state.cycle}-${visible}`} className="playback-progress-value" cx="16" cy="16" r="13" pathLength="1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={{ strokeDashoffset: state.waiting ? 0 : 1, animation: state.startedAt === null ? "none" : `playback-progress ${state.durationMs}ms linear ${delay}ms forwards` }} />
    </svg>}
    {state.playing ? <Pause className="size-3.5" aria-hidden="true" /> : <Play aria-hidden="true" />}
  </Button>;
}

type PromptMode = "random" | "along" | "stay";
type RoamSettings = { playback_interval_seconds: number; liked_tags_only: boolean; prompt_mode: PromptMode };
type ModeChoices = { liked_tags_only: boolean; prompt_mode: PromptMode };
function RoamChoices({ value, disabled = false, onChange, compact = false }: {
  value: ModeChoices; disabled?: boolean; onChange: (patch: Partial<ModeChoices>) => void; compact?: boolean;
}) {
  return <div className={compact ? "grid gap-1" : "form-grid"}>
    <div className={compact ? "flex min-h-8 items-center justify-between gap-2" : "settings-field"}>
      <span className="field-caption whitespace-nowrap">偏好范围<HelpTip text={value.prompt_mode === "stay" ? "停泊不重新抽取，暂不能切换范围；原选择会保留。" : "切换后保留当前图，清空旧预取并重新准备后续图片。"} /></span>
      <ToggleGroup type="single" size="sm" value={value.liked_tags_only ? "liked" : "all"} disabled={disabled || value.prompt_mode === "stay"} aria-label="偏好范围" onValueChange={next => { if (next) onChange({ liked_tags_only: next === "liked" }); }}>
        <ToggleGroupItem value="all" aria-label="全部" data-tooltip="从完整词库抽取；固定词和 PMI 条件保持。">全部</ToggleGroupItem>
        <ToggleGroupItem value="liked" aria-label="喜欢" data-tooltip="仅从喜欢图片的标签中抽取；固定词和 PMI 条件保持。">喜欢</ToggleGroupItem>
      </ToggleGroup>
    </div>
    <div className={compact ? "flex min-h-8 items-center justify-between gap-2" : "settings-field"}>
      <span className="field-caption whitespace-nowrap">漫游方式<HelpTip text="切换后保留当前图，清空旧预取并重新准备后续图片。" /></span>
      <ToggleGroup type="single" size="sm" value={value.prompt_mode} disabled={disabled} aria-label="漫游方式" onValueChange={next => { if (next) onChange({ prompt_mode: next as PromptMode }); }}>
        <ToggleGroupItem value="random" aria-label="漂流" data-tooltip="每张重新随机抽取提示词组合。">漂流</ToggleGroupItem>
        <ToggleGroupItem value="along" aria-label="顺流" data-tooltip="从当前组合逐步变化；变化预算取自所选候选预设。">顺流</ToggleGroupItem>
        <ToggleGroupItem value="stay" aria-label="停泊" data-tooltip="保持整组正负提示词，图像种子仍随机。">停泊</ToggleGroupItem>
      </ToggleGroup>
    </div>
  </div>;
}
export function RoamSettingsChoices() {
  const [value, setValue] = useState<ModeChoices>({ liked_tags_only: false, prompt_mode: "random" });
  useEffect(() => {
    const receive = (event: Event) => setValue((event as CustomEvent<ModeChoices>).detail);
    document.addEventListener("pictide:roam-settings-draft", receive);
    return () => document.removeEventListener("pictide:roam-settings-draft", receive);
  }, []);
  return <>
    <input id="roam-liked-tags-only" type="checkbox" aria-hidden="true" hidden checked={value.liked_tags_only} readOnly />
    <input id="roam-prompt-mode" type="hidden" value={value.prompt_mode} readOnly />
    <RoamChoices value={value} onChange={patch => {
      const next = { ...value, ...patch }; setValue(next);
      (document.getElementById("roam-liked-tags-only") as HTMLInputElement).checked = next.liked_tags_only;
      const mode = document.getElementById("roam-prompt-mode") as HTMLInputElement; mode.value = next.prompt_mode;
      mode.dispatchEvent(new Event("change", { bubbles: true }));
    }} />
  </>;
}
export function RoamOptions() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<RoamSettings>({ playback_interval_seconds: 5, liked_tags_only: false, prompt_mode: "random" });
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("5");
  const [saving, setSaving] = useState({ interval: false, choices: false });
  const intervalPending = useRef(false);
  const [error, setError] = useState("");
  const dirty = useRef(false);
  useEffect(() => {
    const receive = (event: Event) => {
      const value = (event as CustomEvent<RoamSettings>).detail;
      setSettings(value); setReady(true);
      if (!dirty.current) setDraft(String(value.playback_interval_seconds));
    };
    const close = () => setOpen(false);
    document.addEventListener("pictide:roam-options-settings", receive);
    document.addEventListener("pictide:roam-options-close", close);
    return () => {
      document.removeEventListener("pictide:roam-options-settings", receive);
      document.removeEventListener("pictide:roam-options-close", close);
    };
  }, []);
  const save = async (kind: "interval" | "choices", choices?: Partial<ModeChoices>) => {
    if (kind === "interval" && (!ready || !dirty.current || intervalPending.current)) return;
    setError("");
    try {
      const patch = kind === "interval" ? { playback_interval_seconds: playbackInterval(draft) } : choices;
      if (kind === "interval") intervalPending.current = true;
      setSaving(value => ({ ...value, [kind]: true }));
      const data = await new Promise<RoamSettings>((resolve, reject) => document.dispatchEvent(new CustomEvent("pictide:roam-settings-save", { detail: { patch, resolve, reject } })));
      if (kind === "interval") { dirty.current = false; setDraft(String(data.playback_interval_seconds)); }
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally {
      if (kind === "interval") intervalPending.current = false;
      setSaving(value => ({ ...value, [kind]: false }));
    }
  };
  return <Popover open={open} onOpenChange={next => {
    setOpen(next);
    if (next) { dirty.current = false; setDraft(String(settings.playback_interval_seconds)); setError(""); }
  }}>
    <PopoverTrigger asChild><IconButton id="roam-options" icon={Settings2} label="漫游选项" /></PopoverTrigger>
    <PopoverContent forceMount hidden={!open} align="end" className="w-72 max-w-[calc(100vw-24px)] gap-1 p-3" aria-label="漫游选项" onOpenAutoFocus={event => { if (!open) event.preventDefault(); }} onCloseAutoFocus={event => { if (document.querySelector(".image-card.immersive")) event.preventDefault(); }}>
      <div className="grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-x-2 gap-y-1">
        <form className="col-span-2 grid grid-cols-[minmax(0,1fr)_5.5rem_2rem] items-center gap-2" onSubmit={event => { event.preventDefault(); void save("interval"); }}>
          <Label htmlFor="roam-playback-seconds" className="mb-0! whitespace-nowrap font-normal">自动播放</Label>
          <InputGroup className="h-8" data-disabled={!ready || saving.interval}>
          <InputGroupInput id="roam-playback-seconds" aria-label="自动播放间隔（秒）" aria-busy={saving.interval} className="h-8 min-w-0 pl-3 text-right tabular-nums" type="number" min={1} max={600} step={1} value={draft} disabled={!ready || saving.interval} onChange={event => { dirty.current = true; setDraft(event.target.value); }} onBlur={() => void save("interval")} />
          <InputGroupAddon align="inline-end" className="py-0 text-xs" aria-hidden="true">秒</InputGroupAddon>
          </InputGroup>
          <RoamPlaybackButton menu visible={open} />
        </form>
        <div className="col-span-2"><RoamChoices compact value={settings} disabled={!ready || saving.choices} onChange={patch => void save("choices", patch)} /></div>
      </div>
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
    </PopoverContent>
  </Popover>;
}
