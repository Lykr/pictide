import { useEffect, useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "./ui/alert-dialog";

type Request = { message: string; resolve: (value: boolean) => void };
export function confirmAction(message: string): Promise<boolean> {
  return new Promise(resolve => document.dispatchEvent(new CustomEvent("pictide:confirm", { detail: { message, resolve } })));
}
export function ConfirmationLayer() {
  const [requests, setRequests] = useState<Request[]>([]);
  useEffect(() => {
    const receive = (event: Event) => setRequests(items => [...items, (event as CustomEvent<Request>).detail]);
    document.addEventListener("pictide:confirm", receive);
    return () => document.removeEventListener("pictide:confirm", receive);
  }, []);
  const request = requests[0];
  const finish = (value: boolean) => { request?.resolve(value); setRequests(items => items.slice(1)); };
  return <AlertDialog open={!!request} onOpenChange={(open: boolean) => { if (!open && request) finish(false); }}>
    <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>确认操作</AlertDialogTitle><AlertDialogDescription>{request?.message}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter><AlertDialogCancel onClick={(event: React.MouseEvent) => { event.preventDefault(); finish(false); }}>取消</AlertDialogCancel><AlertDialogAction onClick={(event: React.MouseEvent) => { event.preventDefault(); finish(true); }}>确认</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
