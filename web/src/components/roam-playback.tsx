import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, LoaderCircle, Pause, Play, Save, Settings2 } from "lucide-react";
import { IconButton } from "./actions";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Checkbox } from "./ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { playbackInterval } from "../controllers/roam-playback.mjs";

type PlaybackState = { playing: boolean; canPlay: boolean };
function usePlaybackState() {
  const [state, setState] = useState<PlaybackState>({ playing: false, canPlay: false });
  useEffect(() => {
    const receive = (event: Event) => setState((event as CustomEvent<PlaybackState>).detail);
    document.addEventListener("pictide:roam-playback-state", receive);
    return () => document.removeEventListener("pictide:roam-playback-state", receive);
  }, []);
  return state;
}
export function RoamPlaybackButton({ menu = false }: { menu?: boolean }) {
  const state = usePlaybackState();
  const label = state.playing ? "暂停播放" : "自动播放";
  return <IconButton id={menu ? "roam-options-playback" : "roam-playback"} icon={state.playing ? Pause : Play} label={label} aria-pressed={state.playing} disabled={!state.canPlay} onClick={() => document.dispatchEvent(new Event("pictide:roam-playback-toggle"))} />;
}

type RoamSettings = { playback_interval_seconds: number; liked_tags_only: boolean };
export function RoamOptions({ privacy, immersive }: { privacy: ReactNode; immersive: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<RoamSettings>({ playback_interval_seconds: 5, liked_tags_only: false });
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("5");
  const [saving, setSaving] = useState<"interval" | "liked" | null>(null);
  const [saved, setSaved] = useState(false);
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
  const save = async (kind: "interval" | "liked", liked?: boolean) => {
    setError("");
    try {
      const patch = kind === "interval" ? { playback_interval_seconds: playbackInterval(draft) } : { liked_tags_only: liked };
      setSaving(kind);
      const response = await fetch("/api/settings/roam", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
      if (kind === "interval") { dirty.current = false; setDraft(String(data.playback_interval_seconds)); setSaved(true); }
      document.dispatchEvent(new CustomEvent("pictide:roam-settings-saved", { detail: { settings: data, fields: Object.keys(patch) } }));
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setSaving(null); }
  };
  return <Popover open={open} onOpenChange={next => {
    setOpen(next);
    if (next) { dirty.current = false; setDraft(String(settings.playback_interval_seconds)); setError(""); setSaved(false); }
  }}>
    <PopoverTrigger asChild><IconButton id="roam-options" icon={Settings2} label="漫游选项" /></PopoverTrigger>
    <PopoverContent forceMount hidden={!open} align="end" className="w-64 max-w-[calc(100vw-24px)] gap-1 p-3" aria-label="漫游选项" onOpenAutoFocus={event => { if (!open) event.preventDefault(); }} onCloseAutoFocus={event => { if (document.querySelector(".image-card.immersive")) event.preventDefault(); }}>
      <div className="grid grid-cols-[minmax(0,1fr)_4.5rem_2rem] items-center gap-x-2 gap-y-1">
        <span className="col-span-2">自动播放</span><RoamPlaybackButton menu />
        <form className="col-span-3 grid grid-cols-subgrid items-center" onSubmit={event => { event.preventDefault(); void save("interval"); }}>
          <Label htmlFor="roam-playback-seconds" className="mb-0! font-normal">间隔（秒）</Label>
          <Input id="roam-playback-seconds" className="h-8 px-3 text-center tabular-nums" type="number" min={1} max={600} step={1} value={draft} disabled={!ready || saving !== null} onChange={event => { dirty.current = true; setDraft(event.target.value); setSaved(false); }} />
          <IconButton icon={saving === "interval" ? LoaderCircle : saved ? Check : Save} label={saved ? "已保存播放间隔" : "保存播放间隔"} type="submit" disabled={!ready || saving !== null || Number(draft) === settings.playback_interval_seconds} />
        </form>
        <Label htmlFor="roam-options-liked-tags" className="col-span-3 mb-0! grid grid-cols-subgrid items-center font-normal">
          <span className="col-span-2" data-tooltip="仅从喜欢图片中抽取标签；固定词保持不变。">仅用喜欢标签</span>
          <span className="flex size-8 items-center justify-center"><Checkbox id="roam-options-liked-tags" checked={settings.liked_tags_only} disabled={!ready || saving !== null} onCheckedChange={value => void save("liked", value === true)} /></span>
        </Label>
        <span className="col-span-2">毛玻璃</span>{privacy}
        <span className="col-span-2">沉浸模式</span>{immersive}
      </div>
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
    </PopoverContent>
  </Popover>;
}
