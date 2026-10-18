import { t, tr, locale, messageKey } from "../i18n/index.mjs";
import { useEffect, useRef, useState } from "react";
import { Check, Download, Eye, LoaderCircle, RefreshCw, RotateCcw } from "lucide-react";
import { HelpTip, IconButton } from "./actions";
import { PageControls } from "./page-controls";
import { Badge } from "./ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "./ui/alert-dialog";

type PreferenceTerm = { text: string; channel: "positive" | "negative"; weight: number; evidence_count: number };
type PreferencesResult = {
  available: boolean; error: string | null; feature_version: string | null;
  state_revision: number; reset_revision: number; reset_at: string | null;
  evidence_count: number; term_count: number; page: number; page_size: number;
  total_pages: number; terms: PreferenceTerm[];
};
type ResetRequest = { request_id: string; expected_reset_revision: number };
type ResetResult = { request_id: string; reset_revision: number; reset_at: string };

class PreferenceRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new PreferenceRequestError(typeof body?.error === "string" ? body.error : tr`请求失败（${response.status}）`, response.status);
  if (!body) throw new Error(t("响应不完整，请重试。"));
  return body as T;
}

const timeLabel = (value: string | null) => {
  if (!value) return t("尚未重置");
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale(), { hour12: false });
};

export function PreferenceActions() {
  const [viewOpen, setViewOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [result, setResult] = useState<PreferencesResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const readAbort = useRef<AbortController | null>(null);
  // Keep the same id after an uncertain response, including closing/reopening.
  const pendingReset = useRef<ResetRequest | null>(null);
  const mounted = useRef(true);
  const posting = useRef(false);
  const viewEntry = useRef<HTMLButtonElement>(null);
  const resetEntry = useRef<HTMLButtonElement>(null);

  const cancelRead = () => {
    generation.current += 1;
    readAbort.current?.abort();
    readAbort.current = null;
    setLoading(false);
  };

  useEffect(() => {
    mounted.current = true;
    const navigate = () => {
      generation.current += 1;
      readAbort.current?.abort();
      setLoading(false); setViewOpen(false); setResetOpen(false);
      setExporting(false); setExported(false);
      setError(""); setMessage("");
    };
    window.addEventListener("hashchange", navigate);
    return () => {
      mounted.current = false;
      generation.current += 1;
      readAbort.current?.abort();
      window.removeEventListener("hashchange", navigate);
    };
  }, []);

  const load = async (page: number, reset = false) => {
    readAbort.current?.abort();
    const abort = new AbortController();
    readAbort.current = abort;
    const current = ++generation.current;
    setLoading(true); setError("");
    try {
      const data = await request<PreferencesResult>(`/api/recommendation/preferences?page=${page}`, { signal: abort.signal });
      if (!mounted.current || current !== generation.current) return;
      setResult(data);
      if (reset) setResetOpen(true);
    } catch (cause) {
      if (!mounted.current || current !== generation.current || abort.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : t("读取偏好失败，请重试。"));
    } finally {
      if (mounted.current && current === generation.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!exported) return;
    const timer = setTimeout(() => setExported(false), 2000);
    return () => clearTimeout(timer);
  }, [exported]);

  const exportPreferences = async () => {
    readAbort.current?.abort();
    const abort = new AbortController();
    readAbort.current = abort;
    const current = ++generation.current;
    setExporting(true); setExported(false); setError(""); setMessage("");
    try {
      const data = await request<PreferencesResult>("/api/recommendation/preferences?all=1", { signal: abort.signal });
      if (!mounted.current || current !== generation.current) return;
      if (!data.available) throw new Error(data.error || t("暂无法导出用户偏好，请稍后重试。"));
      const now = new Date();
      const report = {
        exported_at: now.toISOString(), feature_version: data.feature_version,
        state_revision: data.state_revision, reset_revision: data.reset_revision, reset_at: data.reset_at,
        evidence_count: data.evidence_count, term_count: data.term_count, terms: data.terms,
      };
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json;charset=utf-8" }));
      const stamp = [now.getFullYear(), now.getMonth() + 1, now.getDate()].map(value => String(value).padStart(2, "0")).join("")
        + "-" + [now.getHours(), now.getMinutes(), now.getSeconds()].map(value => String(value).padStart(2, "0")).join("");
      const link = document.createElement("a");
      link.href = url; link.download = `pictide-preferences-${stamp}.json`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExported(true);
    } catch (cause) {
      if (!mounted.current || current !== generation.current || abort.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : t("导出用户偏好失败，请重试。"));
    } finally {
      if (mounted.current && current === generation.current) setExporting(false);
    }
  };

  const showPreferences = () => {
    setMessage(""); setResult(null); setViewOpen(true);
    void load(1);
  };
  const askReset = () => {
    setMessage("");
    // A previous uncertain POST must be retried with its original revision.
    void load(1, true);
  };

  const resetPreferences = async () => {
    if (posting.current || !result) return;
    const payload = pendingReset.current ?? {
      request_id: crypto.randomUUID(), expected_reset_revision: result.reset_revision,
    };
    pendingReset.current = payload;
    posting.current = true;
    setResetting(true); setError("");
    const current = generation.current;
    try {
      const data = await request<ResetResult>("/api/recommendation/preferences/reset", { method: "POST", body: JSON.stringify(payload) });
      if (data.request_id !== payload.request_id) throw new Error(t("重置响应不匹配，请重试确认结果。"));
      pendingReset.current = null;
      if (!mounted.current || current !== generation.current) return;
      setResetOpen(false);
      setMessage(t("用户偏好已重置"));
      setResult(null);
    } catch (cause) {
      const conflict = cause instanceof PreferenceRequestError && cause.status === 409;
      // Definite validation failures did not reset anything. Transport/5xx
      // failures retain the id because the server may already have committed.
      const rejected = cause instanceof PreferenceRequestError && cause.status >= 400 && cause.status < 500;
      if (rejected) pendingReset.current = null;
      if (!mounted.current || current !== generation.current) return;
      if (conflict) {
        setResetOpen(false);
        setError(t("偏好已在其他操作中重置，请重新确认。"));
        void load(1).then(() => {
          if (mounted.current && current + 1 === generation.current) setError(t("偏好已在其他操作中重置，请重新确认。"));
        });
      } else {
        setError(cause instanceof Error ? cause.message : t("重置结果未确认，请重试。"));
      }
    } finally {
      posting.current = false;
      if (mounted.current) setResetting(false);
    }
  };

  const busy = loading || resetting || exporting;
  return <div className="settings-preferences flex flex-col gap-2">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium">{t("用户偏好")}</span>
      <div className="flex items-center gap-1">
        <IconButton ref={viewEntry} type="button" icon={Eye} label={t("查看用户偏好")} disabled={busy} onClick={showPreferences} />
        <IconButton type="button" icon={exporting ? LoaderCircle : exported ? Check : Download} className={exporting ? "[&_svg]:animate-spin" : ""} label={exporting ? t("正在导出用户偏好") : exported ? t("用户偏好已导出") : t("导出用户偏好")} disabled={busy} onClick={exportPreferences} />
        <IconButton ref={resetEntry} type="button" icon={RotateCcw} label={t("重置用户偏好")} disabled={busy} onClick={askReset} />
        {loading && !viewOpen && <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-label={t("读取用户偏好")} />}
      </div>
    </div>
    {!viewOpen && !resetOpen && error && <p role="alert" className="text-sm text-destructive">{t(messageKey(error))}</p>}
    {message && <p role="status" className="text-xs text-muted-foreground">{t(messageKey(message))}</p>}

    <Dialog open={viewOpen} onOpenChange={(open) => { setViewOpen(open); if (!open) { cancelRead(); setError(""); } }}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl" onCloseAutoFocus={(event) => { event.preventDefault(); if (!viewEntry.current?.closest("[hidden],[inert]")) viewEntry.current?.focus(); }}>
        <DialogHeader>
          <DialogTitle>{t("用户偏好")}</DialogTitle>
          <DialogDescription className="sr-only">{t("查看喜欢与不喜欢反馈形成的标签关联权重。")}</DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-col gap-4" aria-busy={loading}>
          {result && <>
            <dl className="flex flex-wrap gap-x-6 gap-y-2 text-xs">
              <div><dt className="text-muted-foreground inline-flex items-center gap-1">{t("有效学习反馈")}<HelpTip text={t("当前参与偏好学习的图片反馈数量。")} /></dt><dd className="mt-1 text-sm font-medium">{result.evidence_count.toLocaleString(locale())}</dd></div>
              <div><dt className="text-muted-foreground">{t("学习标签")}</dt><dd className="mt-1 text-sm font-medium">{result.term_count.toLocaleString(locale())}</dd></div>
              <div><dt className="text-muted-foreground">{t("上次重置")}</dt><dd className="mt-1">{timeLabel(result.reset_at)}</dd></div>
            </dl>
            {!result.available && <p role="status" className="text-sm text-muted-foreground">{result.error || t("推荐模型暂不可用，仍可重置偏好。")}</p>}
            {result.terms.length > 0 ? <div className="min-w-0 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border text-muted-foreground"><tr>
                  <th className="py-2 pr-3 font-normal">{t("标签")}</th>
                  <th className="px-2 py-2 font-normal">{t("方向")}</th>
                  <th className="px-2 py-2 text-right font-normal"><span className="inline-flex items-center gap-1">{t("关联权重")}<HelpTip text={t("反馈形成的偏好参数中心值，不是喜欢概率。")} /></span></th>
                  <th className="py-2 pl-3 text-right font-normal"><span className="inline-flex items-center gap-1">{t("证据次数")}<HelpTip text={t("包含该标签的有效学习反馈数量。")} /></span></th>
                </tr></thead>
                <tbody>{result.terms.map((term) => <tr key={`${term.channel}:${term.text}`} className="border-b border-border/60 last:border-0">
                  <td className="max-w-64 break-words py-2 pr-3">{term.text}</td>
                  <td className="px-2 py-2"><Badge variant="outline">{term.channel === "positive" ? t("正向") : t("负向")}</Badge></td>
                  <td className="px-2 py-2 text-right tabular-nums"><span tabIndex={0} data-tooltip={term.weight > 0 ? t("正值倾向提高组合评分。") : term.weight < 0 ? t("负值倾向降低组合评分，不会永久屏蔽标签。") : t("零值不提高或降低组合评分。")}>{term.weight.toLocaleString(locale(), { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</span></td>
                  <td className="py-2 pl-3 text-right tabular-nums">{term.evidence_count.toLocaleString(locale())}</td>
                </tr>)}</tbody>
              </table>
            </div> : result.available && <p className="py-6 text-center text-sm text-muted-foreground">{t("暂无学习记录")}</p>}
          </>}
          {error && <p role="alert" className="text-sm text-destructive">{t(messageKey(error))}</p>}
          {loading && <div role="status" className="flex items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />{t("读取中")}</div>}
          {error && <div className="flex justify-end"><IconButton type="button" icon={RefreshCw} label={t("重试读取用户偏好")} disabled={busy} onClick={() => void load(result?.page ?? 1)} /></div>}
          {result && result.term_count > 0 && <PageControls label={t("偏好")} page={result.page} totalPages={result.total_pages} loading={busy} onPageChange={page => void load(page)} />}
        </div>
      </DialogContent>
    </Dialog>

    <AlertDialog open={resetOpen} onOpenChange={(open) => { if (!resetting) { setResetOpen(open); if (!open) setError(""); } }}>
      <AlertDialogContent onCloseAutoFocus={(event) => { event.preventDefault(); if (!resetEntry.current?.closest("[hidden],[inert]")) resetEntry.current?.focus(); }}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("重置用户偏好？")}</AlertDialogTitle>
          <AlertDialogDescription>{t("清空喜欢与不喜欢反馈形成的偏好，保留图片的评价。从此后的新反馈重新学习。")}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <p role="alert" className="text-sm text-destructive">{t(messageKey(error))}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel type="button" disabled={resetting}>{t("取消")}</AlertDialogCancel>
          <AlertDialogAction type="button" variant="destructive" disabled={busy || !result} onClick={(event) => { event.preventDefault(); void resetPreferences(); }}>
            {resetting && <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />}{resetting ? t("重置中") : t("重置偏好")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>;
}
