import { useEffect, useRef, useState } from "react";
import { Check, LoaderCircle, Pause, Play, Save, Timer } from "lucide-react";
import { IconButton } from "./actions";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { playbackInterval } from "../controllers/roam-playback.mjs";

type PlaybackState = { playing: boolean; canPlay: boolean };
export function RoamPlaybackButton() {
  const [state, setState] = useState<PlaybackState>({ playing: false, canPlay: false });
  useEffect(() => {
    const receive = (event: Event) => setState((event as CustomEvent<PlaybackState>).detail);
    document.addEventListener("pictide:roam-playback-state", receive);
    return () => document.removeEventListener("pictide:roam-playback-state", receive);
  }, []);
  return <IconButton id="roam-playback" icon={state.playing ? Pause : Play} label={state.playing ? "暂停播放" : "自动播放"} aria-pressed={state.playing} disabled={!state.canPlay} onClick={() => document.dispatchEvent(new Event("pictide:roam-playback-toggle"))} />;
}

export function RoamPlaybackSettings() {
  const [seconds, setSeconds] = useState(5);
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("5");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const dirty = useRef(false);
  useEffect(() => {
    const receive = (event: Event) => {
      const value = (event as CustomEvent<number>).detail;
      setSeconds(value); setReady(true);
      if (!dirty.current) setDraft(String(value));
    };
    document.addEventListener("pictide:roam-playback-interval", receive);
    return () => document.removeEventListener("pictide:roam-playback-interval", receive);
  }, []);
  const save = async () => {
    setError("");
    try {
      const value = playbackInterval(draft);
      setSaving(true);
      const response = await fetch("/api/settings/roam", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ playback_interval_seconds: value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
      dirty.current = false; setDraft(String(data.playback_interval_seconds)); setSaved(true);
      document.dispatchEvent(new CustomEvent("pictide:roam-playback-interval", { detail: data.playback_interval_seconds }));
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setSaving(false); }
  };
  return <Popover onOpenChange={open => { if (open) { dirty.current = false; setDraft(String(seconds)); setError(""); setSaved(false); } }}>
    <PopoverTrigger asChild><IconButton icon={Timer} label={`播放间隔 · ${seconds} 秒`} disabled={!ready} /></PopoverTrigger>
    <PopoverContent align="end" className="w-64" aria-label="播放间隔">
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); void save(); }}>
        <Label htmlFor="roam-playback-seconds" className="mb-0!">每张展示（秒）</Label>
        <div className="flex items-center gap-2">
          <Input id="roam-playback-seconds" type="number" min={1} max={600} step={1} value={draft} disabled={saving} onChange={event => { dirty.current = true; setDraft(event.target.value); setSaved(false); }} />
          <IconButton icon={saving ? LoaderCircle : saved ? Check : Save} label={saved ? "已保存播放间隔" : "保存播放间隔"} type="submit" disabled={saving || Number(draft) === seconds} className={saving ? "animate-pulse" : ""} />
        </div>
        {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
      </form>
    </PopoverContent>
  </Popover>;
}
