import { useEffect, useMemo, useState } from "react";
import { ArrowDownWideNarrow, ArrowDownAZ, ChevronDown, ListFilter, LoaderCircle, RotateCw, X } from "lucide-react";
import { IconButton } from "./actions";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from "./ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type LikedTag = { text: string; count: number };

export function LikedTagFilter({ visible, revision, disabled = false }: { visible: boolean; revision: number; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const [tags, setTags] = useState<LikedTag[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [byCount, setByCount] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!visible) { setOpen(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(false);
    void fetch("/api/liked/tags", { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("无法读取喜欢标签");
      const data = await response.json() as { tags: LikedTag[]; revision: number };
      if (!controller.signal.aborted) setTags(data.tags);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [visible, revision, retry]);

  const choices = useMemo(() => {
    const search = query.trim().toLowerCase();
    return tags.filter(tag => tag.text.toLowerCase().includes(search)).sort((a, b) => {
      const lexical = a.text < b.text ? -1 : a.text > b.text ? 1 : 0;
      return byCount ? b.count - a.count || lexical : lexical;
    });
  }, [tags, query, byCount]);
  const change = (next: string[]) => {
    setSelected(next);
    document.dispatchEvent(new CustomEvent("pictide:liked-filter", { detail: { tags: next } }));
  };
  const toggle = (text: string) => change(selected.includes(text) ? selected.filter(tag => tag !== text) : [...selected, text]);

  return <div hidden={!visible} className="mb-4 flex min-w-0 flex-wrap items-center gap-2">
    <Popover open={open && !disabled} onOpenChange={next => { setOpen(next); if (next) setQuery(""); }}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled} aria-label="筛选喜欢图片的标签" data-tooltip="多选时仅显示同时包含全部所选标签的喜欢图片。">
          <ListFilter aria-hidden="true" />标签{selected.length > 0 && <span className="tabular-nums">{selected.length}</span>}<ChevronDown aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 max-w-[calc(100vw-24px)] gap-0 p-1" aria-label="喜欢图片标签筛选">
        <Command shouldFilter={false}>
          <div className="flex min-w-0 items-center gap-1 pr-1">
            <div className="min-w-0 flex-1"><CommandInput value={query} onValueChange={setQuery} placeholder="搜索标签…" aria-label="搜索喜欢图片标签" /></div>
            <IconButton icon={byCount ? ArrowDownWideNarrow : ArrowDownAZ} label={byCount ? "图片数量降序，同数量按字典序；点击切换字典序" : "字典序升序；点击切换图片数量排序"} aria-pressed={byCount} onClick={() => setByCount(value => !value)} />
          </div>
          <CommandList aria-label="可筛选标签">
            {loading ? <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground" role="status"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />读取中</div>
              : error ? <div className="flex items-center justify-center gap-2 py-4 text-sm text-destructive" role="alert">标签读取失败<IconButton icon={RotateCw} label="重试读取标签" onClick={() => setRetry(value => value + 1)} /></div>
              : <><CommandEmpty>{query.trim() ? "没有匹配标签" : "喜欢图片暂无标签"}</CommandEmpty>
                <CommandGroup>{choices.map(tag => <CommandItem key={tag.text} value={tag.text} data-checked={selected.includes(tag.text)} onSelect={() => toggle(tag.text)}>
                  <Checkbox checked={selected.includes(tag.text)} tabIndex={-1} aria-hidden="true" className="pointer-events-none" />
                  <span className="min-w-0 flex-1 break-words">{tag.text}</span>
                  <CommandShortcut className="tracking-normal tabular-nums" aria-label={`${tag.count} 张喜欢图片`}>{tag.count}</CommandShortcut>
                </CommandItem>)}</CommandGroup></>}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
    {selected.map(text => <Badge key={text} variant="secondary" className="h-auto max-w-full gap-0 py-0 pl-2 pr-0">
      <span className="min-w-0 break-words whitespace-normal">{text}</span>
      <IconButton icon={X} label={`移除筛选：${text}`} size="icon-xs" disabled={disabled} onClick={() => change(selected.filter(tag => tag !== text))} />
    </Badge>)}
    {selected.length > 0 && <IconButton icon={X} label="清空标签筛选" disabled={disabled} onClick={() => change([])} />}
  </div>;
}
