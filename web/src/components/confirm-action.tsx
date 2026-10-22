import { t, messageKey } from "../i18n/index.mjs";
import { useEffect, useSyncExternalStore } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "./ui/alert-dialog";

type Request = { message: string; resolve: (value: boolean) => void };
let requests: Request[] = [];
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
const snapshot = () => requests;
const update = (next: Request[]) => { requests = next; for (const listener of listeners) listener(); };
export function confirmAction(message: string): Promise<boolean> {
  return new Promise(resolve => update([...requests, { message, resolve }]));
}
export function ConfirmationLayer() {
  const queue = useSyncExternalStore(subscribe, snapshot);
  useEffect(() => () => { for (const item of requests) item.resolve(false); update([]); }, []);
  const request = queue[0];
  const finish = (value: boolean) => { request?.resolve(value); update(requests.filter(item => item !== request)); };
  return <AlertDialog open={!!request} onOpenChange={(open: boolean) => { if (!open && request) finish(false); }}>
    <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("确认操作")}</AlertDialogTitle><AlertDialogDescription>{t(messageKey(request?.message ?? ""))}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter><AlertDialogCancel onClick={(event: React.MouseEvent) => { event.preventDefault(); finish(false); }}>{t("取消")}</AlertDialogCancel><AlertDialogAction onClick={(event: React.MouseEvent) => { event.preventDefault(); finish(true); }}>{t("确认")}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
