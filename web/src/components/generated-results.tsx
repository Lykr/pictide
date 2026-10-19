import { t, tr, messageKey, locale } from "../i18n/index.mjs";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, EyeOff, Heart, ImageIcon, LoaderCircle, RotateCw, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Toggle } from "./ui/toggle";
import { IconButton } from "./actions";
import { LikedTagFilter } from "./liked-tag-filter";
import { GeneratedViewer, type GeneratedArtifact } from "./generated-viewer";
import { imageSeedLabel } from "../controllers/backend-controls.mjs";

type ResultState = { artifacts: GeneratedArtifact[]; total: number; hasMore: boolean; loading: boolean; error: string; pending: boolean; status: string; feedbackPending: boolean; mutationPending: boolean; visible: boolean; configured: boolean; tags: string[]; sort: "latest" | "score"; refreshedAt: string | null; filterVersion: number; revision: number };
const initial: ResultState = { artifacts: [], total: 0, hasMore: false, loading: true, error: "", pending: false, status: "", feedbackPending: false, mutationPending: false, visible: false, configured: false, tags: [], sort: "latest", refreshedAt: null, filterVersion: 0, revision: 0 };
const emit = (name: string, detail?: unknown) => document.dispatchEvent(new CustomEvent(`pictide:${name}`, { detail }));
const imagePath = (item: GeneratedArtifact) => `/api/artifacts/${encodeURIComponent(item.id)}/image`;
const seedLabel = imageSeedLabel;

function ArtifactImage({ item, label }: { item: GeneratedArtifact; label: string }) {
  const [status, setStatus] = useState("loading");
  return <div className="generated-thumbnail">
    <img src={imagePath(item)} alt={`${label} · ${seedLabel(item)}`} loading="lazy" onLoad={() => setStatus("ready")} onError={() => setStatus("error")} />
    {status === "loading" && <span className="generated-image-state" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" /><span className="sr-only">{t("图片加载中")}</span></span>}
    {status === "error" && <span className="generated-image-state" role="status">{t("图片已清理或读取失败")}</span>}
  </div>;
}

// Both collections use the same grid/viewer; only their data and actions differ.
export function GeneratedResults({ collection = "generate" }: { collection?: "generate" | "liked" }) {
  const liked = collection === "liked";
  const prefix = liked ? "liked" : "generated";
  const label = liked ? t("喜欢图片") : t("生成的图片");
  const [state, setState] = useState(initial);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [privacyBlur, setPrivacyBlur] = useState(true);
  useEffect(() => {
    const receive = (event: Event) => setState({ ...initial, ...(event as CustomEvent<ResultState>).detail });
    document.addEventListener(`pictide:${prefix}-results`, receive);
    return () => document.removeEventListener(`pictide:${prefix}-results`, receive);
  }, [prefix]);
  useEffect(() => { if (!state.visible) setSelectedId(null); }, [state.visible]);
  useEffect(() => { if (liked) setSelectedId(null); }, [liked, state.filterVersion]);
  const busy = state.feedbackPending || state.mutationPending || liked && state.loading;
  const like = (item: GeneratedArtifact, toggle = true) => emit(`${prefix}-feedback`, { id: item.id, toggle });
  const privacyLabel = privacyBlur ? t("关闭毛玻璃 · 空格") : t("开启毛玻璃 · 空格");
  const privacyControl = <Toggle size="sm" className="generated-privacy-toggle" data-collection={collection} pressed={privacyBlur} onPressedChange={setPrivacyBlur} aria-label={privacyLabel} aria-keyshortcuts="Space" data-tooltip={privacyLabel}>{privacyBlur ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}</Toggle>;
  const refreshTooltip = state.refreshedAt
    ? t("刷新偏好评分 · 上次刷新：{time}", { time: new Date(state.refreshedAt).toLocaleString(locale()) })
    : t("刷新偏好评分 · 尚未刷新");
  const privacyHost = liked ? document.getElementById("liked-privacy-controls") : null;
  return <section className="generated-results" aria-label={liked ? t("喜欢的图片") : t("生成结果")}>
    {liked && privacyHost && createPortal(<span className="inline-flex items-center gap-1">
      {state.sort === "score" && <IconButton icon={state.loading ? LoaderCircle : RotateCw} className={`generated-privacy-toggle rounded-3xl border-0 ${state.loading ? "[&_svg]:animate-spin" : ""}`} label={state.loading ? t("正在计算偏好评分") : t("刷新偏好评分")} tooltip={refreshTooltip} disabled={busy} onClick={() => emit("liked-refresh")} />}
      {privacyControl}
    </span>, privacyHost)}
    {liked && <LikedTagFilter visible={state.visible} revision={state.revision} disabled={state.feedbackPending || state.mutationPending} sort={state.sort} />}
    {liked && state.loading && !state.artifacts.length && <div className="hint" role="status">{t("加载中…")}</div>}
    {!liked && <div className="generated-results-heading">
      <h2>{t("生成结果")}</h2>
      <div className="generated-results-actions">
        <span className="hint" role="status">{state.pending && <LoaderCircle className="animate-spin" aria-hidden="true" />}{t(messageKey(state.status)) || (state.loading && !state.artifacts.length ? t("加载中…") : "")}</span>
        {privacyControl}
        {!liked && <IconButton icon={Trash2} label={t("清空生成结果：删除未喜欢图片，喜欢图片保留在喜欢页")} disabled={busy || state.loading || !state.total} onClick={() => emit("generated-clear")} />}
      </div>
    </div>}
    {state.error && <div className="notice error" role="status">{t(messageKey(state.error))}<Button variant="ghost" size="sm" type="button" disabled={busy || state.loading} onClick={() => emit(`${prefix}-refresh`)}>{t("重试")}</Button></div>}
    {!state.artifacts.length && !state.loading && !state.error && <div className="empty small"><ImageIcon aria-hidden="true" /><p>{liked ? state.tags.length ? t("没有同时包含所选标签的喜欢图片。") : t("喜欢的图片会保存在这里。") : state.pending ? t("正在生成，完成后会显示在这里。") : state.configured ? t("生成图片后，在这里查看结果。") : t("先配置生图 API。")}</p>{!liked && !state.configured && <Button variant="outline" type="button" onClick={() => emit("generated-configure")}>{t("配置生图 API")}</Button>}</div>}
    <div className={`generated-grid${privacyBlur ? " generated-privacy-blurred" : ""}`} aria-busy={state.loading || state.mutationPending}>{state.artifacts.map(item => <Card key={item.id} className="generated-card gap-0 overflow-hidden py-0">
      <Button type="button" variant="ghost" className="generated-image-button" aria-label={tr`查看${label} · ${seedLabel(item)}`} onClick={() => setSelectedId(item.id)}><ArtifactImage item={item} label={label} /></Button>
      <IconButton icon={Heart} className="generated-card-like" label={item.feedback === 1 ? t("已喜欢，点击撤回") : t("喜欢图片")} aria-pressed={item.feedback === 1} disabled={busy} onClick={() => like(item)} />
    </Card>)}</div>
    {state.hasMore && <div className="load-more-row"><Button variant="outline" type="button" disabled={state.loading || busy} onClick={() => emit(`${prefix}-more`)} data-tooltip={tr`已加载 ${state.artifacts.length} / ${state.total} 张图片`}>{state.loading ? t("加载中…") : liked && state.sort === "score" ? t("加载更多") : t("更早图片")}</Button></div>}
    <GeneratedViewer imageLabel={label} confirmUnlike={liked} items={state.artifacts} activeId={state.visible ? selectedId : null} onActiveChange={setSelectedId} privacyBlur={privacyBlur} onPrivacyChange={setPrivacyBlur} busy={busy} onLike={like} hasMore={state.hasMore} loadingMore={state.loading} onMore={() => emit(`${prefix}-more`)} error={state.error} />
  </section>;
}
