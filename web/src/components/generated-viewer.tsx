import { t } from "../i18n/index.mjs";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Download, Eye, EyeOff, Heart, Info, LoaderCircle, Maximize, Minimize, X } from "lucide-react";
import { IconButton } from "./actions";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { Toggle } from "./ui/toggle";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { ImagePromptDetails } from "./image-prompt-details";
import { createImmersiveViewer } from "../controllers/immersive-controls.mjs";
import { bindTouchNavigation } from "../controllers/touch-navigation.mjs";
import { generatedNeighbour, generatedReplacement, generatedShortcut } from "../controllers/generated-viewer-controls.mjs";
import "../styles/generated-viewer.css";
import { playImageTransition, cancelImageTransition } from "../controllers/image-transitions.mjs";
import { imageSeedLabel } from "../controllers/backend-controls.mjs";

export type GeneratedArtifact = { id: string; positive?: string; negative?: string; seed?: number; seed_applied?: boolean; backend_kind?: string; created_at: string; feedback?: number | null };
export type GeneratedViewerProps = {
  items: GeneratedArtifact[];
  activeId: string | null;
  onActiveChange: (id: string | null) => void;
  privacyBlur: boolean;
  onPrivacyChange: (value: boolean) => void;
  busy: boolean;
  onLike: (item: GeneratedArtifact, toggle?: boolean) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onMore: () => void;
  error?: string;
  imageLabel?: string;
  confirmUnlike?: boolean;
};
const artifactPath = (item: GeneratedArtifact, kind: string) => `/api/artifacts/${encodeURIComponent(item.id)}/${kind}`;

function ViewerImage({ item, privacyBlur, label, onNavigate, busy, transition }: { item: GeneratedArtifact; privacyBlur: boolean; label: string; onNavigate: (direction: string) => void; busy: boolean; transition: boolean }) {
  const [status, setStatus] = useState("loading");
  const stageRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const image = imageRef.current;
    return () => cancelImageTransition(image);
  }, []);
  const latest = useRef({ onNavigate, busy });
  latest.current = { onNavigate, busy };
  useEffect(() => {
    if (!stageRef.current) return;
    return bindTouchNavigation(stageRef.current, {
      navigate: (direction: string) => latest.current.onNavigate(direction),
      enabled: () => !latest.current.busy,
    });
  }, []);
  return <div ref={stageRef} className="generated-viewer-stage" data-privacy-blur={privacyBlur}>
    <img ref={imageRef} src={artifactPath(item, "image")} alt={label} draggable={false} onLoad={event => {
      setStatus("ready");
      if (transition) playImageTransition(event.currentTarget);
    }} onError={() => setStatus("error")} />
    {status !== "ready" && <div className="generated-viewer-loading" role="status">{status === "loading" ? <><LoaderCircle className="animate-spin" aria-hidden="true" /><span className="sr-only">{t("图片加载中")}</span></> : t("图片已清理或读取失败")}</div>}
  </div>;
}

function ViewerContent(props: GeneratedViewerProps & { item: GeneratedArtifact }) {
  const { item, items, onActiveChange, privacyBlur, onPrivacyChange, busy, onLike, hasMore, loadingMore, onMore, error } = props;
  const imageChange = useRef({ id: item.id, transition: false });
  if (imageChange.current.id !== item.id) imageChange.current = { id: item.id, transition: true };
  const [cardElement, setCardElement] = useState<HTMLDivElement | null>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const entryRef = useRef<HTMLButtonElement>(null);
  const exitRef = useRef<HTMLButtonElement>(null);
  const viewerRef = useRef<ReturnType<typeof createImmersiveViewer> | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [immersive, setImmersive] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [waitingOlder, setWaitingOlder] = useState<string | null>(null);
  const pendingOlder = useRef<string | null>(null);
  const older = generatedNeighbour(items, item.id, "older");
  const newer = generatedNeighbour(items, item.id, "newer");

  const navigate = (direction: string) => {
    const current = latest.current;
    if (current.busy) return;
    const neighbour = generatedNeighbour(current.items, current.item.id, direction);
    pendingOlder.current = null; setWaitingOlder(null);
    if (neighbour) current.onActiveChange(neighbour);
    else if (direction === "older" && current.hasMore) {
      pendingOlder.current = current.item.id; setWaitingOlder(current.item.id);
      if (!current.loadingMore) current.onMore();
    }
  };
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  useEffect(() => {
    const anchor = pendingOlder.current;
    if (!anchor) return;
    if (item.id !== anchor || error) { pendingOlder.current = null; setWaitingOlder(null); return; }
    const next = generatedNeighbour(items, anchor, "older");
    if (next) {
      pendingOlder.current = null; setWaitingOlder(null); onActiveChange(next);
    } else if (!loadingMore && !hasMore) { pendingOlder.current = null; setWaitingOlder(null); }
  }, [items, item.id, loadingMore, hasMore, error, onActiveChange]);

  useEffect(() => {
    const card = cardElement, toolbar = toolbarRef.current, entry = entryRef.current;
    if (!card || !toolbar || !entry) return;
    const viewer = createImmersiveViewer({ card, toolbar, entry, exit: exitRef.current,
      eligible: () => !!latest.current.activeId && !!latest.current.items.length,
      changed: (...args: boolean[]) => { setImmersive(args[0]); setInfoOpen(false); },
    });
    viewerRef.current = viewer;
    const closeInfo = () => setInfoOpen(false);
    const keyboard = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey) return;
      const target = event.target instanceof Element ? event.target : null;
      const dialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][data-state="open"],[role="alertdialog"]'));
      const top = dialogs.at(-1);
      const blocked = !!target?.closest('input,textarea,select,[contenteditable="true"],[role="menu"],[role="listbox"],[data-slot="popover-content"],[role="alertdialog"]') || !!(top && top !== card && !card.contains(top));
      const current = latest.current;
      const action = generatedShortcut(event.key, { blocked, busy: current.busy, repeat: event.repeat });
      if (!action) return;
      event.preventDefault();
      if (action === "older" || action === "newer") navigateRef.current(action);
      if (action === "like") current.onLike(current.item, false);
      if (action === "privacy") current.onPrivacyChange(!current.privacyBlur);
    };
    document.addEventListener("keydown", keyboard);
    document.addEventListener("pictide:close-image-info", closeInfo);
    return () => {
      viewer.leave(); viewerRef.current = null;
      document.removeEventListener("keydown", keyboard);
      document.removeEventListener("pictide:close-image-info", closeInfo);
    };
  }, [cardElement]);

  useEffect(() => { setInfoOpen(false); }, [item.id]);

  return <DialogContent ref={setCardElement} className="generated-viewer image-card" showCloseButton={false} aria-describedby={undefined} tabIndex={-1}
    onEscapeKeyDown={event => { if (event.defaultPrevented || viewerRef.current?.active) { event.preventDefault(); viewerRef.current?.leave(); } }}>
    <DialogTitle className="sr-only">{props.imageLabel ?? t("生成的图片")}</DialogTitle>
    <div className="generated-viewer-heading">
      <IconButton ref={entryRef} icon={Maximize} label={t("沉浸模式")} aria-pressed={immersive} disabled={busy} />
      <IconButton icon={privacyBlur ? EyeOff : Eye} label={privacyBlur ? t("关闭毛玻璃 · 空格") : t("开启毛玻璃 · 空格")} aria-pressed={privacyBlur} onClick={() => onPrivacyChange(!privacyBlur)} />
      <IconButton icon={X} label={t("关闭图片")} onClick={() => onActiveChange(null)} />
    </div>
    <div className="immersive-actions" role="toolbar" aria-label={t("沉浸模式设置")}>
      <Toggle size="sm" className="size-8 p-0" pressed={privacyBlur} onPressedChange={onPrivacyChange} aria-label={privacyBlur ? t("关闭毛玻璃 · 空格") : t("开启毛玻璃 · 空格")} aria-keyshortcuts="Space" data-tooltip={privacyBlur ? t("关闭毛玻璃 · 空格") : t("开启毛玻璃 · 空格")}>
        {privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
      </Toggle>
      <IconButton ref={exitRef} icon={Minimize} label={t("退出沉浸模式")} hidden={!immersive} />
    </div>
    <ViewerImage key={item.id} item={item} transition={imageChange.current.transition} privacyBlur={privacyBlur} label={props.imageLabel ?? t("生成的图片")} onNavigate={navigate} busy={busy || infoOpen} />
    {waitingOlder && loadingMore && <div className="generated-viewer-paging" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" /><span className="sr-only">{t("正在加载更早图片")}</span></div>}
    {error && <div className="generated-viewer-error" role="alert">{error}</div>}
    <div ref={toolbarRef} className="generated-viewer-toolbar" aria-label={t("图片操作")}>
      <div className="generated-viewer-details" hidden={immersive}>
        <Popover open={infoOpen && !immersive} onOpenChange={setInfoOpen}>
          <PopoverTrigger asChild><IconButton icon={Info} label={t("图片信息")} /></PopoverTrigger>
          <PopoverContent className="generated-viewer-info image-details-popover" align="start" side="top" aria-label={t("图片信息")}>
            <ImagePromptDetails key={item.id} imageId={item.id} active={infoOpen && !immersive} seed={item.seed_applied === false ? imageSeedLabel(item) : item.seed ?? "—"} positive={item.positive || ""} negative={item.negative || ""}
              actions={<Button asChild variant="ghost" size="icon-sm"><a href={artifactPath(item, "prompts")} download aria-label={t("下载提示词 JSON")} data-tooltip={t("下载提示词 JSON")}><Download aria-hidden="true" /></a></Button>} />
          </PopoverContent>
        </Popover>
      </div>
      <div className="generated-viewer-navigation">
      <IconButton icon={ArrowLeft} label={t("上一张 · ←")} disabled={busy || (!older && !hasMore) || !!waitingOlder} onClick={() => navigate("older")} />
      <IconButton icon={Heart} label={item.feedback === 1 ? t("撤回喜欢") : t("喜欢图片 · ↑")} className={item.feedback === 1 ? "generated-viewer-liked" : ""} aria-pressed={item.feedback === 1} disabled={busy} onClick={async () => { if (props.confirmUnlike && item.feedback === 1) await viewerRef.current?.leave(); onLike(item); }} />
      <IconButton icon={ArrowRight} label={t("下一张 · →")} disabled={busy || !newer} onClick={() => navigate("newer")} />
      </div>

    </div>
  </DialogContent>;
}

export function GeneratedViewer(props: GeneratedViewerProps) {
  const previousIndex = useRef(0);
  const previousItems = useRef(props.items);
  // A cleanup revision temporarily empties the paging cache while it reloads.
  // Keep the mounted image/fullscreen session until the new list is authoritative.
  const items = !props.items.length && props.loadingMore ? previousItems.current : props.items;
  if (props.items.length) previousItems.current = props.items;
  const matching = items.find(item => item.id === props.activeId);
  const fallback = props.activeId ? generatedReplacement(items, previousIndex.current) : null;
  const item = matching ?? items.find(candidate => candidate.id === fallback);
  useEffect(() => {
    if (!props.activeId) return;
    if (matching) previousIndex.current = items.indexOf(matching);
    else if (props.loadingMore) return;
    else props.onActiveChange(fallback);
  }, [items, props.activeId, props.loadingMore, matching, fallback, props.onActiveChange]);
  return <Dialog open={!!props.activeId && !!item} onOpenChange={open => { if (!open) props.onActiveChange(null); }}>
    {props.activeId && item && <ViewerContent {...props} items={items} item={item} />}
  </Dialog>;
}
