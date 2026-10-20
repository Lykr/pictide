import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Toast } from "radix-ui";
import { CheckCircle2, CircleAlert, Info, TriangleAlert, X } from "lucide-react";
import { Button } from "./ui/button";
import { t, messageKey } from "../i18n/index.mjs";
import { dismissNotification, notificationSnapshot, notificationText, notifyError, subscribeNotifications } from "../shared/notifications.mjs";
import "../styles/notifications.css";

export function useErrorNotice(message: string | null | undefined, { id, retry, visible = true }: { id?: string; retry?: () => unknown; visible?: boolean } = {}) {
  const latestRetry = useRef(retry);
  latestRetry.current = retry;
  useEffect(() => {
    if (!message || !visible) { if (id) dismissNotification(id); return; }
    notifyError(message, { id, action: retry ? { label: () => t("重试"), onClick: () => latestRetry.current?.() } : undefined });
  }, [message, id, visible, !!retry]);
}

export function NotificationLayer() {
  const notices = useSyncExternalStore(subscribeNotifications, notificationSnapshot);
  const [host] = useState(() => {
    const element = document.createElement("div");
    element.className = "notification-layer";
    element.dataset.notifications = "true";
    // Modal isolation must preserve this subtree; Radix Toast owns live announcements.
    element.setAttribute("aria-live", "off");
    if (typeof element.showPopover === "function") element.popover = "manual";
    return element;
  });
  const active = notices.length > 0;
  useEffect(() => {
    let reporting = false;
    const invalid = (event: Event) => {
      const field = event.target;
      if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)) return;
      event.preventDefault();
      if (reporting) return;
      reporting = true;
      notifyError(field.validationMessage, { id: "form-validation" });
      field.focus({ preventScroll: true });
      queueMicrotask(() => { reporting = false; });
    };
    document.addEventListener("invalid", invalid, true);
    return () => document.removeEventListener("invalid", invalid, true);
  }, []);
  useLayoutEffect(() => {
    const place = () => {
      const dialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][data-state="open"],[role="alertdialog"][data-state="open"]'));
      const target = document.fullscreenElement || dialogs.at(-1) || document.querySelector(".image-card.immersive") || document.body;
      if (host.parentElement !== target) target.appendChild(host);
      // Immersive isolation and modal aria hiding can mark the old host inert.
      host.inert = false;
      host.removeAttribute("aria-hidden");
      if (host.popover === "manual") {
        if (active && !host.matches(":popover-open")) host.showPopover();
        if (!active && host.matches(":popover-open")) host.hidePopover();
      }
    };
    place();
    const observer = new MutationObserver(place);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-state", "class", "inert", "aria-hidden"] });
    document.addEventListener("fullscreenchange", place);
    return () => { observer.disconnect(); document.removeEventListener("fullscreenchange", place); };
  }, [host, active]);
  useEffect(() => () => host.remove(), [host]);
  return createPortal(<Toast.Provider label={t("通知")} swipeDirection="right" announcerContainer={host}>
    {notices.map(notice => {
      const Icon = notice.kind === "error" ? CircleAlert : notice.kind === "success" ? CheckCircle2 : notice.kind === "warning" ? TriangleAlert : Info;
      return <Toast.Root key={notice.sequence} className="notification-card" data-kind={notice.kind} open={notice.open} duration={notice.duration} onOpenChange={open => { if (!open) dismissNotification(notice.id); }}>
        <Icon className="notification-icon" aria-hidden="true" />
        <div className="notification-content">
          <Toast.Description className="notification-description">{t(messageKey(notificationText(notice.message)))}</Toast.Description>
          {notice.action && <Toast.Action asChild altText={t(messageKey(notificationText(notice.action.label)))}>
            <Button type="button" variant="outline" size="sm" onClick={() => {
              Promise.resolve().then(() => notice.action?.onClick()).catch(error => notifyError(error instanceof Error ? error.message : String(error)));
            }}>{t(messageKey(notificationText(notice.action.label)))}</Button>
          </Toast.Action>}
        </div>
        <Toast.Close asChild><Button type="button" variant="ghost" size="icon-sm" className="notification-close" aria-label={t("关闭通知")}><X aria-hidden="true" /></Button></Toast.Close>
      </Toast.Root>;
    })}
    <Toast.Viewport className="notification-viewport" label={t("通知（{hotkey}）")} />
  </Toast.Provider>, host);
}
