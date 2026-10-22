import { onSignal, offSignal } from '../shared/signals.mjs';
import { useUiFact } from '../shared/application-context';
import { runUiCommand } from '../shared/ui-state.mjs';
import { useErrorNotice } from "./notifications";
import { t } from "../i18n/index.mjs";
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
function usePlaybackState(): PlaybackState {
  return useUiFact('playback', { playing: false, canPlay: false, startedAt: null, durationMs: 8000, cycle: 0, waiting: false });
}
export function RoamPlaybackButton({ immersive = false }: { immersive?: boolean }) {
  const state = usePlaybackState();
  const label = state.playing ? t("暂停播放") : t("自动播放");
  const delay = useMemo(() => state.startedAt === null ? 0 : -Math.max(0, performance.now() - state.startedAt), [state.startedAt, state.cycle]);
  return <Button id={immersive ? "roam-immersive-playback" : "roam-playback"} type="button" variant="ghost" size="icon-sm" className="relative" aria-label={label} data-tooltip={label} aria-pressed={state.playing} disabled={!state.canPlay} onClick={() => runUiCommand("roam-playback-toggle")}>
    {state.playing && <svg className="playback-progress absolute left-1/2 top-1/2 size-8 -translate-x-1/2 -translate-y-1/2 -rotate-90" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="1.5" opacity="0.15" />
      <circle key={state.cycle} className="playback-progress-value" cx="16" cy="16" r="13" pathLength="1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" style={{ strokeDashoffset: state.waiting ? 0 : 1, animation: state.startedAt === null ? "none" : `playback-progress ${state.durationMs}ms linear ${delay}ms forwards` }} />
    </svg>}
    {state.playing ? <Pause className="size-3.5" aria-hidden="true" /> : <Play aria-hidden="true" />}
  </Button>;
}

type PromptMode = "random" | "along" | "stay";
type RecommendationStrength = "standard" | "strong";
type ModeChoices = { liked_tags_only: boolean; prompt_mode: PromptMode; recommendation_strength: RecommendationStrength };
type RoamSettings = ModeChoices & { playback_interval_seconds: number };
function RoamChoices({ value, disabled = false, onChange, compact = false }: {
  value: ModeChoices; disabled?: boolean; onChange: (patch: Partial<ModeChoices>) => void; compact?: boolean;
}) {
  return <div className={compact ? "grid gap-1" : "form-grid"}>
    <div className={compact ? "roam-choice flex min-h-8 flex-wrap items-center justify-between gap-2" : "settings-field"}>
      <span className="field-caption whitespace-nowrap">{t("偏好范围")}<HelpTip text={t("选择从哪些标签中寻找画面灵感。")} /></span>
      <ToggleGroup type="single" size="sm" value={value.liked_tags_only ? "liked" : "all"} disabled={disabled || value.prompt_mode === "stay"} aria-label={t("偏好范围")} onValueChange={next => { if (next) onChange({ liked_tags_only: next === "liked" }); }}>
        <ToggleGroupItem value="all" aria-label={t("全部")} data-tooltip={t("从完整词库探索更多画面。")}>{t("全部")}</ToggleGroupItem>
        <ToggleGroupItem value="liked" aria-label={t("喜欢")} data-tooltip={t("围绕喜欢过的图片元素继续探索。")}>{t("喜欢")}</ToggleGroupItem>
      </ToggleGroup>
    </div>
    <div className={compact ? "roam-choice flex min-h-8 flex-wrap items-center justify-between gap-2" : "settings-field"}>
      <span className="field-caption whitespace-nowrap">{t("漫游方式")}<HelpTip text={t("选择画面之间如何延续或变化。")} /></span>
      <ToggleGroup type="single" size="sm" value={value.prompt_mode} disabled={disabled} aria-label={t("漫游方式")} onValueChange={next => { if (next) onChange({ prompt_mode: next as PromptMode }); }}>
        <ToggleGroupItem value="random" aria-label={t("漂流")} data-tooltip={t("每张探索新的画面组合。")}>{t("漂流")}</ToggleGroupItem>
        <ToggleGroupItem value="along" aria-label={t("顺流")} data-tooltip={t("沿着当前画面逐步变化。")}>{t("顺流")}</ToggleGroupItem>
        <ToggleGroupItem value="stay" aria-label={t("停泊")} data-tooltip={t("保持提示词，探索同一描述的不同画面。")}>{t("停泊")}</ToggleGroupItem>
      </ToggleGroup>
    </div>
    <div className={compact ? "roam-choice flex min-h-8 flex-wrap items-center justify-between gap-2" : "settings-field"}>
      <span className="field-caption whitespace-nowrap">{t("推荐力度")}<HelpTip text={t("调整漫游贴近个人喜好的程度。")} /></span>
      <ToggleGroup type="single" size="sm" value={value.recommendation_strength} disabled={disabled} aria-label={t("推荐力度")} onValueChange={next => { if (next) onChange({ recommendation_strength: next as RecommendationStrength }); }}>
        <ToggleGroupItem value="standard" aria-label={t("标准")} data-tooltip={t("兼顾个人喜好与新鲜感。")}>{t("标准")}</ToggleGroupItem>
        <ToggleGroupItem value="strong" aria-label={t("强力")} data-tooltip={t("更集中地寻找符合个人喜好的画面。")}>{t("强力")}</ToggleGroupItem>
      </ToggleGroup>
    </div>
  </div>;
}
export function RoamSettingsChoices({ value, onChange }: { value: ModeChoices; onChange: (patch: Partial<ModeChoices>) => void }) {
  return <RoamChoices value={value} onChange={onChange} />;
}
export function RoamOptions({ buttonRef }: { buttonRef?: React.Ref<HTMLButtonElement> }) {
  const [open, setOpen] = useState(false);
  const current = useUiFact("roamOptions");
  const settings: RoamSettings = current ?? { playback_interval_seconds: 8, liked_tags_only: false, prompt_mode: "random", recommendation_strength: "standard" };
  const ready = !!current;
  const [draft, setDraft] = useState("8");
  const [saving, setSaving] = useState({ interval: false, choices: false });
  const intervalPending = useRef(false);
  const [error, setError] = useState("");
  useErrorNotice(error, { id: "roam-options" });
  const dirty = useRef(false);
  useEffect(() => {
    const close = () => setOpen(false);
    onSignal("roam-options-close", close);
    return () => {
        offSignal("roam-options-close", close);
    };
  }, []);
  useEffect(() => { if (!dirty.current) setDraft(String(settings.playback_interval_seconds)); }, [settings.playback_interval_seconds]);
  const save = async (kind: "interval" | "choices", choices?: Partial<ModeChoices>) => {
    if (kind === "interval" && (!ready || !dirty.current || intervalPending.current)) return;
    setError("");
    try {
      const patch = kind === "interval" ? { playback_interval_seconds: playbackInterval(draft) } : choices;
      if (kind === "interval") intervalPending.current = true;
      setSaving(value => ({ ...value, [kind]: true }));
      const data = await runUiCommand("roam-settings-save", patch);
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
    <PopoverTrigger asChild><IconButton ref={buttonRef} id="roam-options" icon={Settings2} label={t("漫游选项")} /></PopoverTrigger>
    <PopoverContent forceMount hidden={!open} align="end" collisionPadding={12} className="roam-options-panel w-max gap-1 p-3" aria-label={t("漫游选项")} onOpenAutoFocus={event => { if (!open) event.preventDefault(); }} onCloseAutoFocus={event => { if (document.querySelector(".image-card.immersive")) event.preventDefault(); }}>
      <div className="grid gap-1">
        <form className="grid grid-cols-[minmax(0,1fr)_6rem] items-center gap-3" onSubmit={event => { event.preventDefault(); void save("interval"); }}>
          <Label htmlFor="roam-playback-seconds" className="mb-0! whitespace-nowrap font-normal">{t("展示时间")}</Label>
          <InputGroup className="h-8" data-disabled={!ready || saving.interval}>
          <InputGroupInput id="roam-playback-seconds" aria-label={t("展示时间（秒）")} aria-busy={saving.interval} className="h-8 min-w-0 pl-3 text-right tabular-nums" type="number" min={1} max={600} step={1} value={draft} disabled={!ready || saving.interval} onChange={event => { dirty.current = true; setDraft(event.target.value); }} onBlur={() => void save("interval")} />
          <InputGroupAddon align="inline-end" className="py-0 text-xs" aria-hidden="true">{t("秒")}</InputGroupAddon>
          </InputGroup>
        </form>
        <RoamChoices compact value={settings} disabled={!ready || saving.choices} onChange={patch => void save("choices", patch)} />
      </div>
    </PopoverContent>
  </Popover>;
}
