import { useApplication, useModel, useUiFact } from '../shared/application-context';
import { runUiCommand } from '../shared/ui-state.mjs';
import { useErrorNotice } from "./notifications";
import { publishUiState } from "../shared/ui-state.mjs";
import { uiTarget } from "../shared/ui-targets";
import { t, tr, messageKey, locale } from "../i18n/index.mjs";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Download, Eye, EyeOff, Heart, ImageIcon, ListChecks, LoaderCircle, RotateCw, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Toggle } from "./ui/toggle";
import { Checkbox } from './ui/checkbox';
import { IconButton } from "./actions";
import { LikedTagFilter } from "./liked-tag-filter";
import { GeneratedViewer, type GeneratedArtifact } from "./generated-viewer";
import { ArtifactImage } from './artifact-image';
import { RecentUnlikes } from './recent-unlikes';
import { imageSeedLabel } from "../controllers/backend-controls.mjs";

type ResultState = { artifacts: GeneratedArtifact[]; total: number; hasMore: boolean; loading: boolean; error: string; pending: boolean; status: string; feedbackPending: boolean; mutationPending: boolean; visible: boolean; configured: boolean; tags: string[]; sort: "latest" | "score"; refreshedAt: string | null; filterVersion: number; revision: number };
const initial: ResultState = { artifacts: [], total: 0, hasMore: false, loading: true, error: "", pending: false, status: "", feedbackPending: false, mutationPending: false, visible: false, configured: false, tags: [], sort: "latest", refreshedAt: null, filterVersion: 0, revision: 0 };
const emit = (name: string, detail?: unknown) => runUiCommand(name, detail);
const seedLabel = imageSeedLabel;

// Both collections use the same grid/viewer; only their data and actions differ.
export function GeneratedResults({ collection = "generate", privacyHost }: { collection?: "generate" | "liked"; privacyHost?: HTMLElement | null }) {
  const targets = useMemo(() => ({ privacy: uiTarget("liked.privacy"), collection: uiTarget("liked.collection") }), []);
  const liked = collection === "liked";
  const prefix = liked ? "liked" : "generated";
  const label = liked ? t("喜欢图片") : t("生成的图片");
  const state: ResultState = { ...initial, ...useUiFact(liked ? "likedResults" : "generatedResults", initial) };
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const app = useApplication(), application = useModel(app.model);
  const privacyBlur = application.privacy[collection];
  const setPrivacyBlur = (value: boolean) => app.setPrivacy(collection, value);
  useEffect(() => { if (liked) publishUiState({ likedPrivacy: privacyBlur, likedLoading: state.loading, likedTotal: state.total }); }, [liked, privacyBlur, state.loading, state.total]);
  useEffect(() => { if (!state.visible) setSelectedId(null); }, [state.visible]);
  useEffect(() => { if (liked) setSelectedId(null); }, [liked, state.filterVersion]);
  useEffect(() => { setSelecting(false); setSelection([]); }, [state.visible, state.filterVersion]);
  useEffect(() => {
    if (state.loading) return;
    const available = new Set(state.artifacts.map(item => item.id));
    setSelection(previous => previous.every(id => available.has(id)) ? previous : previous.filter(id => available.has(id)));
  }, [state.artifacts, state.loading]);
  useErrorNotice(t(messageKey(state.error)), { id: `${prefix}-results`, visible: state.visible, retry: () => emit(`${prefix}-refresh`) });
  useErrorNotice(t(messageKey(exportError)), { id: `${prefix}-export`, visible: state.visible });
  const busy = exporting || state.feedbackPending || state.mutationPending || liked && state.loading;
  const select = (id: string) => setSelection(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id]);
  const exportSelection = async () => {
    setExporting(true); setExportError('');
    try {
      const response = await fetch('/api/liked/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: selection }) });
      if (!response.ok) { const failure = await response.json(); throw new Error(failure.error || t('图片导出失败')); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'pictide-liked.zip'; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (failure) { setExportError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setExporting(false); }
  };
  const like = (item: GeneratedArtifact, toggle = true) => emit(`${prefix}-feedback`, { id: item.id, toggle });
  const privacyLabel = privacyBlur ? t("关闭毛玻璃 · 空格") : t("开启毛玻璃 · 空格");
  const exportLabel = t(selecting ? '退出选择' : '多选导出');
  const privacyControl = <Toggle ref={liked ? targets.privacy : undefined} size="sm" className="generated-privacy-toggle" data-collection={collection} pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={privacyLabel} aria-keyshortcuts="Space" data-tooltip={privacyLabel}>{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</Toggle>;
  const refreshTooltip = state.refreshedAt
    ? t("刷新偏好评分 · 上次刷新：{time}", { time: new Date(state.refreshedAt).toLocaleString(locale()) })
    : t("刷新偏好评分 · 尚未刷新");
  return <section className="generated-results" aria-label={liked ? t("喜欢的图片") : t("生成结果")}>
    {liked && privacyHost && createPortal(<span className="inline-flex items-center gap-1">
      {state.sort === "score" && <IconButton icon={state.loading ? LoaderCircle : RotateCw} className={`generated-privacy-toggle rounded-3xl border-0 ${state.loading ? "[&_svg]:animate-spin" : ""}`} label={state.loading ? t("正在计算偏好评分") : t("刷新偏好评分")} tooltip={refreshTooltip} disabled={busy} onClick={() => emit("liked-refresh")} />}
      {privacyControl}
      <Toggle size="sm" className="generated-privacy-toggle" pressed={selecting} aria-label={exportLabel} data-tooltip={exportLabel}
        disabled={busy || !state.artifacts.length} onPressedChange={value => { setSelecting(value); setSelection([]); setExportError(''); }}>
        <ListChecks aria-hidden="true" />
      </Toggle>
      <RecentUnlikes visible={state.visible} busy={state.feedbackPending || state.mutationPending} privacyBlur={privacyBlur} onPrivacyChange={setPrivacyBlur} />
    </span>, privacyHost)}
    {liked && selecting && <div className="mb-4 flex flex-wrap items-center gap-2" aria-label={t('收藏导出')}>
        <IconButton icon={ListChecks} label={t('全选已加载')} disabled={busy} onClick={() => setSelection(state.artifacts.map(item => item.id))} />
        <span className="text-sm text-muted-foreground" role="status">{t('已选 {count} 张', { count: selection.length })}</span>
        <IconButton className={exporting ? '[&_svg]:animate-spin' : ''} icon={exporting ? LoaderCircle : Download} label={t('导出 ZIP')} disabled={busy || !selection.length || selection.length > 1000} onClick={() => void exportSelection()} />
        {selection.length > 1000 && <span className="text-sm text-muted-foreground">{t('单次最多导出 1000 张图片')}</span>}
    </div>}
    {liked && <LikedTagFilter visible={state.visible} revision={state.revision} disabled={busy} sort={state.sort} />}
    {liked && state.loading && !state.artifacts.length && <div className="hint" role="status">{t("加载中…")}</div>}
    {!liked && <div className="generated-results-heading">
      <h2>{t("生成结果")}</h2>
      <div className="generated-results-actions">
        <span className="hint" role="status">{state.pending && <LoaderCircle className="animate-spin" aria-hidden="true" />}{t(messageKey(state.status)) || (state.loading && !state.artifacts.length ? t("加载中…") : "")}</span>
        {privacyControl}
        {!liked && <IconButton icon={Trash2} label={t("清空生成结果：删除未喜欢图片，喜欢图片保留在喜欢页")} disabled={busy || state.loading || !state.total} onClick={() => emit("generated-clear")} />}
      </div>
    </div>}
    {!state.artifacts.length && !state.loading && !state.error && <div className="empty small"><ImageIcon aria-hidden="true" /><p>{liked ? state.tags.length ? t("没有同时包含所选标签的喜欢图片。") : t("喜欢的图片会保存在这里。") : state.pending ? t("正在生成，完成后会显示在这里。") : state.configured ? t("生成图片后，在这里查看结果。") : t("先配置生图 API。")}</p>{!liked && !state.configured && <Button variant="outline" type="button" onClick={() => emit("generated-configure")}>{t("配置生图 API")}</Button>}</div>}
    <div ref={liked ? targets.collection : undefined} className={`generated-grid${privacyBlur ? " generated-privacy-blurred" : ""}`} aria-busy={state.loading || state.mutationPending}>{state.artifacts.map(item => <Card key={item.id} className="generated-card gap-0 overflow-hidden py-0">
      <Button type="button" variant="ghost" className="generated-image-button" aria-label={tr`查看${label} · ${seedLabel(item)}`} aria-pressed={selecting ? selection.includes(item.id) : undefined} disabled={exporting} onClick={() => selecting ? select(item.id) : setSelectedId(item.id)}><ArtifactImage item={item} label={label} /></Button>
      {liked && selecting && <Checkbox className="generated-card-select absolute top-3 left-3 z-10" aria-label={t('选择图片 {id}', { id: item.id })} checked={selection.includes(item.id)} disabled={busy} onCheckedChange={() => select(item.id)} />}
      <IconButton icon={Heart} className="generated-card-like image-like" label={item.feedback === 1 ? t("已喜欢，点击撤回") : t("喜欢图片")} aria-pressed={item.feedback === 1} disabled={busy} onClick={() => like(item)} />
    </Card>)}</div>
    {state.hasMore && <div className="load-more-row"><Button variant="outline" type="button" disabled={state.loading || busy} onClick={() => emit(`${prefix}-more`)} data-tooltip={tr`已加载 ${state.artifacts.length} / ${state.total} 张图片`}>{state.loading ? t("加载中…") : liked && state.sort === "score" ? t("加载更多") : t("更早图片")}</Button></div>}
    <GeneratedViewer imageLabel={label} confirmUnlike={liked} allowDownload={liked} onRoam={liked ? item => app.startRoamFromLiked(item.id) : undefined} items={state.artifacts} activeId={state.visible ? selectedId : null} onActiveChange={setSelectedId} privacyBlur={privacyBlur} onPrivacyChange={setPrivacyBlur} busy={busy} onLike={like} hasMore={state.hasMore} loadingMore={state.loading} onMore={() => emit(`${prefix}-more`)} error={state.error} />
  </section>;
}
