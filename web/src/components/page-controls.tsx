import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CornerDownLeft } from "lucide-react";
import { IconButton } from "./actions";
import { Input } from "./ui/input";

export const DEFAULT_PAGE_SIZE = 15;
type PageControlsProps = {
  label: string; page: number; totalPages: number; loading?: boolean;
  onPageChange: (page: number) => void;
};

/** Shared numbered pagination; fetching and list state stay with each view. */
export function PageControls({ label, page, totalPages, loading = false, onPageChange }: PageControlsProps) {
  const [draft, setDraft] = useState(String(page));
  useEffect(() => { setDraft(String(page)); }, [page]);
  const navigate = (target: number) => {
    setDraft(String(target));
    if (target !== page) onPageChange(target);
  };
  return <form className="mt-4 flex items-center justify-center gap-2" aria-label={`${label}分页`} aria-busy={loading} onSubmit={event => {
    event.preventDefault();
    const target = Number(draft);
    if (!loading && Number.isSafeInteger(target) && target >= 1 && target <= totalPages) navigate(target);
  }}>
    <IconButton icon={ArrowLeft} label={`上一页${label}`} disabled={loading || page <= 1} onClick={() => navigate(page - 1)} />
    <Input className="h-8 w-20 text-center tabular-nums" type="number" min={1} max={totalPages} step={1} required aria-label={`${label}页码`} value={draft} disabled={loading} onChange={event => setDraft(event.target.value)} />
    <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted-foreground" aria-live="polite">/ {totalPages}</span>
    <IconButton icon={CornerDownLeft} label={`跳转${label}页`} type="submit" disabled={loading} />
    <IconButton icon={ArrowRight} label={`下一页${label}`} disabled={loading || page >= totalPages} onClick={() => navigate(page + 1)} />
  </form>;
}

type JobPageState = { page: number; totalPages: number; loading: boolean; visible: boolean };
export function JobPageControls() {
  const [state, setState] = useState<JobPageState>({ page: 1, totalPages: 1, loading: false, visible: false });
  useEffect(() => {
    const receive = (event: Event) => setState({ ...(event as CustomEvent<JobPageState>).detail });
    document.addEventListener("pictide:jobs-pagination", receive);
    return () => document.removeEventListener("pictide:jobs-pagination", receive);
  }, []);
  return <div hidden={!state.visible}><PageControls label="任务" {...state} onPageChange={page => document.dispatchEvent(new CustomEvent("pictide:jobs-page", { detail: { page } }))} /></div>;
}
