import { useErrorNotice } from "./notifications";
import { ApplicationUpdates } from "./application-updates";
import { requestUiAction } from "../shared/ui-state.mjs";
import { Button } from "./ui/button";
import { useEffect, useState } from "react";
import { Compass, LoaderCircle, Monitor, Moon, Sun } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Label } from "./ui/label";
import { Checkbox } from "./ui/checkbox";
import { HelpTip } from "./actions";
import { imageTransitionsEnabled, applyImageTransitions } from "../controllers/image-transitions.mjs";
import { applyTheme, currentTheme, saveTheme, saveLanguage, saveImageTransitions } from "../controllers/theme.mjs";
import { applyLanguage, language, languages, t, tr, subscribe } from "../i18n/index.mjs";

export function GeneralSettings({ initialError = "" }: { initialError?: string }) {
  const [theme, setTheme] = useState(currentTheme);
  const [selectedLanguage, setSelectedLanguage] = useState(language);
  const [effects, setEffects] = useState(imageTransitionsEnabled);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState(initialError);
  useErrorNotice(error, { id: "general-settings" });
  useEffect(() => {
    const sync = () => { setTheme(currentTheme()); setError(""); };
    const failed = (event: Event) => setError((event as CustomEvent<string>).detail);
    const unsubscribe = subscribe(() => setSelectedLanguage(language()));
    const syncEffects = () => setEffects(imageTransitionsEnabled());
    document.addEventListener("pictide:image-transitions-changed", syncEffects);
    document.addEventListener("pictide:theme-changed", sync);
    document.addEventListener("pictide:theme-error", failed);
    return () => { document.removeEventListener("pictide:image-transitions-changed", syncEffects); unsubscribe(); document.removeEventListener("pictide:theme-changed", sync); document.removeEventListener("pictide:theme-error", failed); };
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
  const changeEffects = async (next: boolean) => {
    if (saving || next === effects) return;
    const previous = effects;
    setSaving("effects"); setError(""); applyImageTransitions(next);
    try { await saveImageTransitions(next); }
    catch (failure) { applyImageTransitions(previous); setError(t("效果保存失败：{error}", { error: failure instanceof Error ? failure.message : String(failure) })); }
    finally { setSaving(""); }
  };
  return <div className="general-settings">
    <div className="general-setting-row general-setting-options">
      <Label id="language-label">{t("语言")}</Label>
      <ToggleGroup className="general-setting-control flex-wrap" type="single" size="sm" value={selectedLanguage} onValueChange={changeLanguage} disabled={!!saving} aria-labelledby="language-label" aria-busy={saving === "language"}>
        {languages.map(({ value, label }) => <ToggleGroupItem key={value} value={value} aria-label={t(label)}>{saving === "language" && selectedLanguage === value && <LoaderCircle className="animate-spin" aria-hidden="true" />}{t(label)}</ToggleGroupItem>)}
      </ToggleGroup>
    </div>
    <div className="general-setting-row general-setting-options">
      <Label id="theme-label">{t("主题")}</Label>
      <ToggleGroup className="general-setting-control flex-wrap" type="single" size="sm" value={theme} onValueChange={change} disabled={!!saving} aria-labelledby="theme-label" aria-busy={saving === "theme"}>
        {([{ value: "system", label: "跟随系统", icon: Monitor }, { value: "dark", label: "黑色", icon: Moon }, { value: "light", label: "白色", icon: Sun }] as const).map(({ value, label, icon: Icon }) =>
          <ToggleGroupItem key={value} value={value} aria-label={t(label)}>
            {saving === "theme" && theme === value ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Icon aria-hidden="true" />}{t(label)}
          </ToggleGroupItem>
        )}
      </ToggleGroup>
    </div>
    <div className="general-setting-row">
      <div className="general-setting-caption">
        <Label htmlFor="image-transitions">{t("图片切换动效")}</Label>
        {saving === "effects" ? <LoaderCircle className="size-3.5 animate-spin" aria-label={t("正在保存")} /> : <HelpTip text={t("切换图片时淡入；系统启用减少动态效果时不播放。")} />}
      </div>
      <div className="general-setting-control general-setting-checkbox"><Checkbox id="image-transitions" aria-label={t("图片切换动效")} checked={effects} disabled={!!saving} onCheckedChange={next => changeEffects(next === true)} /></div>
    </div>
    <div className="general-setting-row general-setting-tour"><span>{t("新手引导")}</span><Button variant="outline" type="button" className="general-setting-control" onClick={() => requestUiAction("onboarding.restart")}><Compass aria-hidden="true" />{t("开始引导")}</Button></div>
    <ApplicationUpdates />
  </div>;
}
