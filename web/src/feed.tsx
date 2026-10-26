import { GenerationForm } from './features/generation-form';
import { PromptSettings } from './features/prompt-settings';
import { ApiSettings } from './features/api-settings';
import { RoamSettings } from './features/roam-settings';
import { HistorySettings } from './features/history-settings';
import { ImageToolbar } from "./components/image-toolbar";
import { SettingsRow } from "./components/settings-row";
import { t, tr } from './i18n/index.mjs';
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { publishUiState } from "./shared/ui-state.mjs";
import { uiTarget } from "./shared/ui-targets";
import { EditorWorkspace } from "./editor";
import { GeneratedResults } from "./components/generated-results";
import { Tabs, TabsList, TabsTrigger } from './components/ui/tabs';
import { useApplication, useModel } from './shared/application-context';
import { emitSignal } from './shared/signals.mjs';
import { GeneralSettings } from "./components/general-settings";
import { ImageInfo } from "./components/image-info";
import { RoamImmersiveLoading } from "./components/immersive-loading";
import { RoamAnchors } from "./components/roam-anchors";
import { RoamPlaybackButton, RoamOptions } from "./components/roam-playback";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Heart, Image, ListFilter, LoaderCircle, Maximize, Minimize, Settings, Compass, Sparkles, CircleSlash, ThumbsDown } from "lucide-react";
import { IconButton } from "./components/actions";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Toggle } from "./components/ui/toggle";
import "./styles/theme.css";
import "./styles/feed.css";

// Views stay mounted so navigation preserves local drafts and disclosure state.
export function FeedShell({ themeError = "" }: { themeError?: string }) {
  const targets = useMemo(() => Object.fromEntries([
    "app.navigation", "nav.liked", "roam.pending", "roam.privacy", "roam.privacy.immersive", "roam.start", "roam.image", "roam.like", "roam.next",
  ].map(name => [name, uiTarget(name === "roam.privacy.immersive" ? "roam.privacy" : name)])), []);
  const app = useApplication();
  const state = useModel(app.model);
  const privacyBlur = state.privacy.feed;
  const setPrivacyBlur = (value: boolean) => app.setPrivacy("feed", value);
  useEffect(() => publishUiState({ roamPrivacy: privacyBlur }), [privacyBlur]);
  const refs = useRef<Record<string, any>>({});
  const ref = useMemo(() => Object.fromEntries(['image', 'card', 'stage', 'toolbar', 'immersiveEntry', 'immersiveExit', 'options', 'privacy', 'immersivePrivacy', 'liked', 'likedPrivacy', 'feedback'].map(key => [key, (node: HTMLElement | null) => { refs.current[key] = node; }])), []);
  useLayoutEffect(() => app.mount(refs.current), [app]);
  useEffect(() => {
    if (!state.feedbackNotice || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const animation = refs.current.feedback?.animate([
      { opacity: 0, transform: 'translateY(12px) scale(.86)', offset: 0 },
      { opacity: 1, transform: 'translateY(0) scale(1.06)', offset: .18 },
      { opacity: 1, transform: 'translateY(0) scale(1)', offset: .3 },
      { opacity: 1, transform: 'translateY(0) scale(1)', offset: .7 },
      { opacity: 0, transform: 'translateY(-8px) scale(.98)', offset: 1 },
    ], { duration: 900, easing: 'ease-out', fill: 'both' });
    return () => animation?.cancel();
  }, [state.feedbackNotice]);
  const artifact = state.gallery.artifact, waiting = state.gallery.waiting;
  const titles: Record<string, string> = { feed: '漫游', generate: '生成', liked: '喜欢', prompts: '提示词', settings: '设置' };
  const availabilityLabel = state.availability === 'pending' ? t('检查中') : state.availability === 'available' ? t('可用') : state.backends.length ? t('不可用') : t('未配置');
  const privacyLabel = privacyBlur ? t("关闭毛玻璃，显示图片") : t("开启毛玻璃，模糊图片");
  return <div className={`feed-page${privacyBlur ? " privacy-blurred" : ""}`}>
{"\n  "}<header className="topbar">
<a className="brand" href="/" aria-label={t("Pictide 图片漫游")}>
<span className="brand-mark" aria-hidden="true"><img src={`${import.meta.env.BASE_URL}icons/pictide.svg?v=wave-v1`} alt="" /></span>
<div>
<strong>Pictide</strong>

</div>
</a>
<div className="top-actions">
<span id="backend-status" className={`status${state.availability === "available" ? " connected" : ""}`} data-availability={state.availability} role="status">{availabilityLabel}</span>
</div>
</header>
{"\n  "}<div id="app-workspace" className={`workspace compose-hidden${state.view === "prompts" ? " editor-active" : ""}${state.view === "feed" ? " roam-active" : ""}`}>
{"\n    "}<nav ref={targets["app.navigation"]} className="sidebar" aria-label={t("视图")}>
<Button className={`nav${state.view === "feed" ? " active" : ""}`} data-view="feed" aria-current={state.view === "feed" ? "page" : undefined} onClick={() => app.setView("feed")} variant="ghost" type="button"><Compass aria-hidden="true" />{t("漫游")}</Button>
<Button className={`nav${state.view === "generate" ? " active" : ""}`} data-view="generate" aria-current={state.view === "generate" ? "page" : undefined} onClick={() => app.setView("generate")} variant="ghost" type="button"><Sparkles aria-hidden="true" />{t("生成")}</Button>
<Button className={`nav${state.view === "liked" ? " active" : ""}`} data-view="liked" aria-current={state.view === "liked" ? "page" : undefined} onClick={() => app.setView("liked")} ref={targets["nav.liked"]} variant="ghost" type="button"><Heart aria-hidden="true" />{t("喜欢")}</Button>
<Button className={`nav${state.view === "prompts" ? " active" : ""}`} data-view="prompts" aria-current={state.view === "prompts" ? "page" : undefined} onClick={() => app.setView("prompts")} variant="ghost" type="button"><ListFilter aria-hidden="true" />{t("提示词")}</Button>
<div className="sidebar-foot">
<Button className={`nav${state.view === "settings" ? " active" : ""}`} data-view="settings" aria-current={state.view === "settings" ? "page" : undefined} onClick={() => app.setView("settings")} variant="ghost" type="button"><Settings aria-hidden="true" />{t("设置")}</Button>
</div>
</nav>
{"\n    "}<main id="feed-main" className="main workspace-content" hidden={state.view === "prompts"}>
{"\n      "}<div className="section-heading">
<div className="view-heading">
<h1 id="view-title">{t(titles[state.view])}</h1>
<span id="roam-loading" ref={targets["roam.pending"]} className="roam-loading" role="status" hidden={state.view !== "feed" || !waiting}><LoaderCircle aria-hidden="true" /><span id="roam-loading-label" className="sr-only">{t(state.preparingPrompt ? "正在准备提示词…" : "正在生成漫游图片")}</span></span>
</div>
<div className="roam-heading-actions">
<span id="liked-privacy-controls" hidden={state.view !== "liked"} ref={ref.likedPrivacy} />
<span id="roam-options-controls" className="inline-flex items-center gap-1" hidden={state.view !== "feed"}><RoamPlaybackButton /><Toggle id="roam-privacy" ref={node => { ref.privacy(node); targets["roam.privacy"](node); }} size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={tr`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={tr`${privacyLabel} · 空格。刷新页面后默认开启。`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle><IconButton id="roam-immersive" icon={Maximize} label={t("进入沉浸模式")} aria-controls="image-card" onClick={() => emitSignal("roam-options-close")} ref={ref.immersiveEntry} disabled={!artifact} aria-pressed={!!state.immersive} /><RoamOptions buttonRef={ref.options} /></span>
</div>
</div>
{"\n      "}<section id="gallery-view" className="gallery-view" hidden={state.view !== "feed"}>
{"\n        "}<div id="empty-state" className="empty" hidden={!!artifact}>
<div className="empty-mark"><Image aria-hidden="true" /></div>
<h2 id="empty-title" hidden={state.gallery.loading}>{t("从第一张图片开始")}</h2>
<p id="empty-description">{state.gallery.loading ? t("正在读取图片…") : waiting ? t("正在准备漫游图片…") : state.backends.length ? t("开始漫游，发现下一张图片。") : t("连接生图 API，开始生成。")}</p>
<Button id="empty-settings" className="primary" variant="default" type="button" hidden={state.gallery.loading || !!state.backends.length} onClick={app.openSettings}>{t("配置生图 API")}</Button>
<Button id="empty-generate" ref={targets["roam.start"]} variant="default" type="button" hidden={state.gallery.loading || !state.backends.length || waiting} onClick={app.requestNextRoamImage}>{t("开始漫游")}</Button>
</div>
{"\n        "}<RoamAnchors>{(anchorTrigger, anchorPanel) => <Card id="image-card" className={`image-card roam-image-card gap-0 py-0${state.immersive ? " immersive" : ""}`}  tabIndex={-1} aria-label={t("图片浏览")} ref={ref.card} hidden={!artifact} aria-busy={!!waiting}>
<RoamImmersiveLoading />
<div className="immersive-actions" role="toolbar" aria-label={t("沉浸模式设置")}>
<RoamPlaybackButton immersive />
<Toggle id="roam-immersive-privacy" ref={node => { ref.immersivePrivacy(node); targets["roam.privacy.immersive"](node); }} size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={tr`${privacyLabel} · 空格`} aria-keyshortcuts="Space" aria-controls="image-card" data-tooltip={tr`${privacyLabel} · 空格`}>
{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
</Toggle>
<IconButton id="roam-immersive-exit" icon={Minimize} label={t("退出沉浸模式")} ref={ref.immersiveExit} hidden={!state.immersive} />
</div>
<div className="image-stage" ref={node => { ref.stage(node); targets["roam.image"](node); }}>
<img id="main-image" alt={t("生成的图片")} draggable={false} ref={ref.image} src={artifact ? `/api/artifacts/${encodeURIComponent(artifact.id)}/image` : undefined} onLoad={app.imageLoaded} onError={app.imageFailed} />

<div id="immersive-feedback" className="immersive-feedback" role="status" aria-live="polite" aria-atomic="true" hidden={!state.feedbackNotice} data-value={state.feedbackNotice?.value === null ? "clear" : String(state.feedbackNotice?.value)}>
<div ref={ref.feedback} className="immersive-feedback-content">
<Heart data-feedback-icon="like" aria-hidden="true" />
<ThumbsDown data-feedback-icon="dislike" aria-hidden="true" />
<CircleSlash data-feedback-icon="clear" aria-hidden="true" />
<span id="immersive-feedback-label">{state.feedbackNotice?.value === 1 ? t("已喜欢") : state.feedbackNotice?.value === -1 ? t("已不喜欢") : state.feedbackNotice?.previous === 1 ? t("已取消喜欢") : t("已取消不喜欢")}</span>
</div>
</div>
</div>
<ImageToolbar ref={ref.toolbar} information={<ImageInfo />} trailing={anchorTrigger} navigation={<>
<IconButton id="previous" icon={ArrowLeft} label={t("上一张较旧图片 · ←")} variant="ghost" type="button" disabled={state.gallery.previousDisabled} onClick={() => app.moveImage("older")} />
<IconButton id="like" ref={targets["roam.like"]} icon={Heart} label={artifact?.feedback === 1 ? t("已喜欢，点击撤回") : t("喜欢 · ↑")} variant="ghost" type="button" className="feedback" disabled={state.feedbackPending} aria-pressed={artifact?.feedback === 1} onClick={() => app.feedback(1)} />
<IconButton id="dislike" icon={ThumbsDown} label={artifact?.feedback === -1 ? t("已不喜欢，点击撤回") : t("不喜欢 · ↓")} variant="ghost" type="button" className="feedback" disabled={state.feedbackPending} aria-pressed={artifact?.feedback === -1} onClick={() => app.feedback(-1)} />
<IconButton id="next" ref={targets["roam.next"]} icon={ArrowRight} label={t("下一张较新图片 · →")} variant="ghost" type="button" disabled={state.gallery.nextDisabled} onClick={() => app.moveImage("newer")} />
</>} />
{anchorPanel}
</Card>}</RoamAnchors>

{"\n      "}</section>
{"\n      "}<section id="liked-view" hidden={state.view !== "liked"} ref={ref.liked}><GeneratedResults collection="liked" privacyHost={refs.current.likedPrivacy} /></section>

{"\n    "}<section id="compose" className="compose" hidden={state.view !== "generate"}>
<GenerationForm />
<GeneratedResults />
{"\n    "}</section>
<section id="settings-view" className="settings-view" hidden={state.view !== "settings"}>
<Tabs value={state.settingsSection} onValueChange={app.setSettingsSection}><TabsList className="settings-navigation" aria-label={t('设置分类')}>{[['general', '通用'], ['roam', '漫游'], ['backend', '生图 API'], ['llm', 'LLM API'], ['history', '历史']].map(([key, label]) => <TabsTrigger key={key} value={key} data-settings-section={key}>{t(label)}</TabsTrigger>)}</TabsList></Tabs>
<div className="settings-content">
<section id="settings-general" className="settings-category" hidden={state.settingsSection !== "general"}><GeneralSettings initialError={themeError} />
<SettingsRow className="settings-data-location" label={t("数据位置")} stackOnMobile><code id="data-directory">{state.dataDirectory || t("读取中…")}</code></SettingsRow>
</section>
<section id="settings-backend" className="settings-category" hidden={state.settingsSection !== "backend"}><ApiSettings /></section>
<section id="settings-llm" className="settings-category" hidden={state.settingsSection !== "llm"}><PromptSettings /></section>
<section id="settings-roam" className="settings-category" hidden={state.settingsSection !== "roam"}><RoamSettings /></section>
<section id="settings-history" className="settings-category space-y-6" hidden={state.settingsSection !== "history"}>
<HistorySettings />
</section>

</div>
</section>
</main>
<div hidden={state.view !== "prompts"} className="contents"><EditorWorkspace /></div>
</div>
</div>; }
