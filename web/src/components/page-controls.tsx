import { t, tr } from "../i18n/index.mjs";
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
  return <form className="mt-4 flex items-center justify-center gap-2" aria-label={tr`${label}分页`} aria-busy={loading} onSubmit={event => {
    event.preventDefault();
    const target = Number(draft);
    if (!loading && Number.isSafeInteger(target) && target >= 1 && target <= totalPages) navigate(target);
  }}>
    <IconButton icon={ArrowLeft} label={tr`上一页${label}`} disabled={loading || page <= 1} onClick={() => navigate(page - 1)} />
    <Input className="h-8 w-20 text-center tabular-nums" type="number" min={1} max={totalPages} step={1} required aria-label={tr`${label}页码`} value={draft} disabled={loading} onChange={event => setDraft(event.target.value)} />
    <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-muted-foreground" aria-live="polite">/ {totalPages}</span>
    <IconButton icon={CornerDownLeft} label={tr`跳转${label}页`} type="submit" disabled={loading} />
    <IconButton icon={ArrowRight} label={tr`下一页${label}`} disabled={loading || page >= totalPages} onClick={() => navigate(page + 1)} />
  </form>;
}
