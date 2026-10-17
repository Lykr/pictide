import { useEffect, useState } from "react";
import { LoaderCircle, Monitor, Moon, Sun } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Label } from "./ui/label";
import { applyTheme, currentTheme, saveTheme } from "../controllers/theme.mjs";

export function GeneralSettings({ initialError = "" }: { initialError?: string }) {
  const [theme, setTheme] = useState(currentTheme);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(initialError);
  useEffect(() => {
    const sync = () => { setTheme(currentTheme()); setError(""); };
    const failed = (event: Event) => setError((event as CustomEvent<string>).detail);
    document.addEventListener("pictide:theme-changed", sync);
    document.addEventListener("pictide:theme-error", failed);
    return () => { document.removeEventListener("pictide:theme-changed", sync); document.removeEventListener("pictide:theme-error", failed); };
  }, []);
  const change = async (next: string) => {
    if (!next || saving || next === theme) return;
    const previous = theme;
    setSaving(true); setError(""); applyTheme(next);
    try { await saveTheme(next); }
    catch (failure) { applyTheme(previous); setError(`主题保存失败：${failure instanceof Error ? failure.message : String(failure)}`); }
    finally { setSaving(false); }
  };
  return <div className="space-y-3">
    <div className="settings-field">
      <Label id="theme-label" >主题</Label>
      <ToggleGroup className="justify-self-start" type="single" size="sm" value={theme} onValueChange={change} disabled={saving} aria-labelledby="theme-label" aria-busy={saving}>
        {([{ value: "system", label: "跟随系统", icon: Monitor }, { value: "dark", label: "黑色", icon: Moon }, { value: "light", label: "白色", icon: Sun }] as const).map(({ value, label, icon: Icon }) =>
          <ToggleGroupItem key={value} value={value} aria-label={label}>
            {saving && theme === value ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Icon aria-hidden="true" />}{label}
          </ToggleGroupItem>
        )}
      </ToggleGroup>
    </div>
    {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
  </div>;
}
