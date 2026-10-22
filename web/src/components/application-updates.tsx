import { emitSignal, onSignal, offSignal } from '../shared/signals.mjs';
import { runUiCommand } from '../shared/ui-state.mjs';
import { SettingsRow } from "./settings-row";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpToLine, Download, LoaderCircle, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { confirmAction } from "./confirm-action";
import { useErrorNotice } from "./notifications";
import { dismissNotification, notify } from "../shared/notifications.mjs";
import { t, messageKey } from "../i18n/index.mjs";

type Status = {
  current_version: string; latest_version: string | null; phase: string; reason: string;
  can_download: boolean; can_install: boolean; release_url: string;
  downloaded_bytes: number; total_bytes: number; error: string | null;
};

const reasons: Record<string, string> = {
  manual_installation: "此安装布局需要手动更新。",
  source_installation: "源码部署请手动更新。", directory_read_only: "程序目录不可写，请手动更新。",
  data_inside_program: "数据位于程序文件内，请手动更新。", linked_installation: "程序文件使用了链接，请手动更新。",
  local_access_required: "请在运行 Pictide 的电脑上通过本机地址更新。",
  incompatible: "此版本需要手动升级，请查看发行说明。", manual_update: "此版本需要手动升级，请查看发行说明。",
  platform_unverified: "此平台尚未验证直接升级，请手动更新。",
};

async function request(action = ""): Promise<Status> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), action ? 90000 : 5000);
  try {
    const response = await fetch("/api/updates" + (action ? "/" + action : ""), {
      ...(action ? { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" } : {}),
      signal: controller.signal,
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.error || t("更新操作失败，请稍后重试。"));
    return body;
  } finally { clearTimeout(timeout); }
}

export function ApplicationUpdates() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const currentVersion = useRef<string | null>(null);
  const restarting = useRef(false);
  const restartStarted = useRef(0);
  useErrorNotice(t(messageKey(error)), { id: "application-updates" });
  const receive = useCallback((next: Status) => {
    if (currentVersion.current && currentVersion.current !== next.current_version) {
      // The user-triggered installation finished; load matching frontend assets.
      window.location.reload();
      return;
    }
    currentVersion.current = next.current_version;
    if (["preparing", "installing"].includes(next.phase)) {
      if (!restarting.current) restartStarted.current = Date.now();
      restarting.current = true;
      runUiCommand("updating");
    }
    if (restarting.current && !["preparing", "installing"].includes(next.phase)) {
      restarting.current = false;
      runUiCommand("update-finished");
    }
    setStatus(next);
    if (next.error) setError(next.error);
  }, []);
  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      try { const next = await request(); if (mounted) receive(next); }
      catch (failure) {
        if (!restarting.current && mounted) setError(failure instanceof Error ? failure.message : String(failure));
      }
      // Only poll local readiness during an explicitly initiated installation, never releases.
      if (mounted && restarting.current) {
        if (Date.now() - restartStarted.current >= 120000) {
          setError(t("未能重新连接 Pictide。请检查程序是否运行，或查看 logs/pictide.log。"));
          setStatus(previous => previous && { ...previous, phase: "error", can_download: false, can_install: false });
        } else timer = setTimeout(read, 800);
      }
    };
    const changed = () => { clearTimeout(timer); void read(); };
    void read();
    onSignal("updates-changed", changed);
    return () => { mounted = false; clearTimeout(timer); offSignal("updates-changed", changed); };
  }, [receive]);
  const act = async (action: string) => {
    if (busy) return;
    if (action === "install") {
      if (!runUiCommand("before-update")) {
        setError(t("请先保存未完成的修改，再安装更新。"));
        return;
      }
      if (!await confirmAction(t("安装更新并重启 Pictide？图片、偏好和模型会保留。"))) return;
    }
    setBusy(true); setError("");
    dismissNotification("application-update-check");
    try {
      const next = await request(action);
      receive(next);
      if (action === "check" && !next.error && next.latest_version) {
        const current = next.phase === "current" || next.latest_version === next.current_version;
        notify(() => current ? t("已是最新版本。") : [
          t("发现新版本 {version}", { version: `v${next.latest_version}` }),
          next.reason ? t(reasons[next.reason] || "此版本需要手动升级，请查看发行说明。") : "",
        ].filter(Boolean).join(" "), { id: "application-update-check", kind: current ? "success" : "info" });
      }
      if (action === "install") emitSignal("updates-changed");
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setBusy(false); }
  };
  const phase = status?.phase;
  const working = busy || ["checking", "downloading", "verifying", "preparing", "installing"].includes(phase || "");
  const newer = phase !== 'current' && !!status?.latest_version && status.latest_version !== status.current_version;
  return <SettingsRow stackOnMobile label={t("版本与更新")} className="items-start py-3" data-application-updates="">
    <div className="flex flex-col gap-2 w-full">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">{status ? `Pictide v${status.current_version}` : "Pictide"}</span>
        <Button type="button" variant="outline" size="sm" disabled={working || !status} onClick={() => void act("check")}>
          {working ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <RefreshCw aria-hidden="true" />}{t("检查更新")}
        </Button>
      </div>
      {status && newer && <div className="flex flex-wrap items-center gap-3 text-sm">
        <a className="underline underline-offset-4" href={status.release_url} target="_blank" rel="noreferrer">{t("发行说明")}</a>
        {status.can_download && phase !== "ready" && <Button type="button" variant="outline" size="sm" disabled={working} onClick={() => void act("download")}><Download aria-hidden="true" />{t("下载更新")}</Button>}
        {status.can_install && <Button type="button" size="sm" disabled={working} onClick={() => void act("install")}><ArrowUpToLine aria-hidden="true" />{t("安装并重启")}</Button>}
      </div>}
      {["downloading", "verifying", "preparing", "installing"].includes(phase || "") && <div className="flex flex-col gap-2 text-sm" role="status">
        <span>{t(phase === "installing" ? "正在安装，Pictide 将重新启动…" : phase === "preparing" ? "正在准备安装…" : phase === "verifying" ? "正在校验更新…" : "正在下载更新…")}</span>
        {phase === "downloading" && status && <div role="progressbar" aria-label={t("更新下载进度")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(status.downloaded_bytes / status.total_bytes * 100)} className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-[width]" style={{ width: `${status.downloaded_bytes / status.total_bytes * 100}%` }} /></div>}
      </div>}
    </div>
  </SettingsRow>;
}
