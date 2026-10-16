import { useEffect, useState } from "react";
import { LoaderCircle, Moon, Sun } from "lucide-react";
import { Toggle } from "./ui/toggle";
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
  const change = async (dark: boolean) => {
    const previous = theme;
    const next = dark ? "dark" : "light";
    setSaving(true); setError(""); applyTheme(next);
    try { await saveTheme(next); }
    catch (failure) { applyTheme(previous); setError(`主题保存失败：${failure instanceof Error ? failure.message : String(failure)}`); }
    finally { setSaving(false); }
  };
  return <div className="max-w-md space-y-3">
    <div className="flex items-center justify-between gap-4">
      <Label htmlFor="theme-toggle" className="mb-0!">深色主题</Label>
      <Toggle id="theme-toggle" variant="outline" pressed={theme === "dark"} onPressedChange={change} disabled={saving} aria-label="深色主题" data-tooltip={theme === "dark" ? "切换为浅色主题" : "切换为深色主题"}>
        {saving ? <LoaderCircle className="animate-spin" /> : theme === "dark" ? <Moon /> : <Sun />}
      </Toggle>
    </div>
    {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
  </div>;
}
