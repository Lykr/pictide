import { useEffect, useState } from "react";
import { LoaderCircle, Monitor, Moon, Sun } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Label } from "./ui/label";
import { applyTheme, currentTheme, saveTheme, saveLanguage } from "../controllers/theme.mjs";
import { applyLanguage, language, languages, t, tr, subscribe } from "../i18n/index.mjs";

export function GeneralSettings({ initialError = "" }: { initialError?: string }) {
  const [theme, setTheme] = useState(currentTheme);
  const [selectedLanguage, setSelectedLanguage] = useState(language);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState(initialError);
  useEffect(() => {
    const sync = () => { setTheme(currentTheme()); setError(""); };
    const failed = (event: Event) => setError((event as CustomEvent<string>).detail);
    const unsubscribe = subscribe(() => setSelectedLanguage(language()));
    document.addEventListener("pictide:theme-changed", sync);
    document.addEventListener("pictide:theme-error", failed);
    return () => { unsubscribe(); document.removeEventListener("pictide:theme-changed", sync); document.removeEventListener("pictide:theme-error", failed); };
  }, []);
  const change = async (next: string) => {
    if (!next || saving || next === theme) return;
    const previous = theme;
    setSaving("theme"); setError(""); applyTheme(next);
    try { await saveTheme(next); }
    catch (failure) { applyTheme(previous); setError(tr`主题保存失败：${failure instanceof Error ? failure.message : String(failure)}`); }
    finally { setSaving(""); }
  };
  const changeLanguage = async (next: string) => {
    if (!next || saving || next === selectedLanguage) return;
    const previous = selectedLanguage;
    setSaving("language"); setError(""); applyLanguage(next);
    try { await saveLanguage(next); }
    catch (failure) { applyLanguage(previous); setError(tr`语言保存失败：${failure instanceof Error ? failure.message : String(failure)}`); }
    finally { setSaving(""); }
  };
  return <div className="space-y-5">
    <div className="settings-field">
      <Label id="language-label">{t("语言")}</Label>
      <ToggleGroup className="justify-self-start flex-wrap" type="single" size="sm" value={selectedLanguage} onValueChange={changeLanguage} disabled={!!saving} aria-labelledby="language-label" aria-busy={saving === "language"}>
        {languages.map(({ value, label }) => <ToggleGroupItem key={value} value={value} aria-label={t(label)}>{saving === "language" && selectedLanguage === value && <LoaderCircle className="animate-spin" aria-hidden="true" />}{t(label)}</ToggleGroupItem>)}
      </ToggleGroup>
    </div>
    <div className="settings-field">
      <Label id="theme-label">{t("主题")}</Label>
      <ToggleGroup className="justify-self-start" type="single" size="sm" value={theme} onValueChange={change} disabled={!!saving} aria-labelledby="theme-label" aria-busy={saving === "theme"}>
        {([{ value: "system", label: "跟随系统", icon: Monitor }, { value: "dark", label: "黑色", icon: Moon }, { value: "light", label: "白色", icon: Sun }] as const).map(({ value, label, icon: Icon }) =>
          <ToggleGroupItem key={value} value={value} aria-label={t(label)}>
            {saving === "theme" && theme === value ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Icon aria-hidden="true" />}{t(label)}
          </ToggleGroupItem>
        )}
      </ToggleGroup>
    </div>
    {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
  </div>;
}
