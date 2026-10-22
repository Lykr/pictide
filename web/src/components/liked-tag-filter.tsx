import { runUiCommand } from '../shared/ui-state.mjs';
import { useErrorNotice } from "./notifications";
import { t, tr, locale } from "../i18n/index.mjs";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownWideNarrow, ArrowDownAZ, ChevronDown, ListFilter, LoaderCircle, X } from "lucide-react";
import { IconButton } from "./actions";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from "./ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "./ui/select";

type LikedTag = { text: string; count: number };
const TAG_BATCH_SIZE = 50;

export function LikedTagFilter({ visible, revision, disabled = false, sort = "latest" }: { visible: boolean; revision: number; disabled?: boolean; sort?: "latest" | "score" }) {
  const [open, setOpen] = useState(false);
  const [tags, setTags] = useState<LikedTag[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [byCount, setByCount] = useState(false);
  const [shown, setShown] = useState(TAG_BATCH_SIZE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useErrorNotice(error ? t("标签读取失败") : "", { id: "liked-tags", visible, retry: () => setRetry(value => value + 1) });

  useEffect(() => {
    if (!visible) { setOpen(false); return; }
    const controller = new AbortController();
    setLoading(true); setError(false);
    void fetch("/api/liked/tags", { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(t("无法读取喜欢标签"));
      const data = await response.json() as { tags: LikedTag[]; revision: number };
      if (!controller.signal.aborted) setTags(data.tags);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [visible, revision, retry]);

  const orderedTags = useMemo(() => [...tags].sort((a, b) => {
    const lexical = a.text < b.text ? -1 : a.text > b.text ? 1 : 0;
    return byCount ? b.count - a.count || lexical : lexical;
  }), [tags, byCount]);
  const choices = useMemo(() => {
    const search = query.trim().toLowerCase();
    return search ? orderedTags.filter(tag => tag.text.toLowerCase().includes(search)) : orderedTags;
  }, [orderedTags, query]);
  const visibleChoices = choices.slice(0, shown);
  const change = (next: string[]) => {
    setSelected(next);
    runUiCommand("liked-filter", { tags: next });
  };
  const toggle = (text: string) => change(selected.includes(text) ? selected.filter(tag => tag !== text) : [...selected, text]);

  return <div hidden={!visible} className="mb-4 flex min-w-0 flex-wrap items-center gap-2">
    <Popover open={open && !disabled} onOpenChange={next => { setOpen(next); if (next) { setQuery(""); setShown(TAG_BATCH_SIZE); } }}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled} aria-label={t("筛选喜欢图片的标签")} data-tooltip={t("多选时仅显示同时包含全部所选标签的喜欢图片。")}>
          <ListFilter aria-hidden="true" />{t("标签")}{selected.length > 0 && <span className="tabular-nums">{selected.length}</span>}<ChevronDown aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 max-w-[calc(100vw-24px)] gap-0 p-1" aria-label={t("喜欢图片标签筛选")}>
        <Command shouldFilter={false}>
          <div className="flex min-w-0 items-center gap-1 pr-1">
            <div className="min-w-0 flex-1"><CommandInput value={query} onValueChange={next => { setQuery(next); setShown(TAG_BATCH_SIZE); }} placeholder={t("搜索标签…")} aria-label={t("搜索喜欢图片标签")} /></div>
            <IconButton icon={byCount ? ArrowDownWideNarrow : ArrowDownAZ} label={byCount ? t("图片数量降序，同数量按字典序；点击切换字典序") : t("字典序升序；点击切换图片数量排序")} aria-pressed={byCount} onClick={() => { setByCount(value => !value); setShown(TAG_BATCH_SIZE); }} />
          </div>
          <CommandList aria-label={t("可筛选标签")}>
            {loading ? <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground" role="status"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />{t("读取中")}</div>
              : <><CommandEmpty>{query.trim() ? t("没有匹配标签") : t("喜欢图片暂无标签")}</CommandEmpty>
                <CommandGroup>{visibleChoices.map(tag => <CommandItem key={tag.text} value={tag.text} data-checked={selected.includes(tag.text)} onSelect={() => toggle(tag.text)}>
                  <Checkbox checked={selected.includes(tag.text)} tabIndex={-1} aria-hidden="true" className="pointer-events-none" />
                  <span className="min-w-0 flex-1 break-words">{tag.text}</span>
                  <CommandShortcut className="tracking-normal tabular-nums" aria-label={tr`${tag.count} 张喜欢图片`}>{tag.count.toLocaleString(locale())}</CommandShortcut>
                </CommandItem>)}</CommandGroup></>}
          </CommandList>
        </Command>
        {!loading && !error && shown < choices.length && <Button type="button" variant="ghost" size="sm" className="w-full" onClick={() => setShown(value => value + TAG_BATCH_SIZE)}>{t("加载更多")}</Button>}
      </PopoverContent>
    </Popover>
    {selected.map(text => <Badge key={text} variant="secondary" className="h-auto max-w-full gap-0 py-0 pl-2 pr-0">
      <span className="min-w-0 break-words whitespace-normal">{text}</span>
      <IconButton icon={X} label={tr`移除筛选：${text}`} size="icon-xs" disabled={disabled} onClick={() => change(selected.filter(tag => tag !== text))} />
    </Badge>)}
    {selected.length > 0 && <IconButton icon={X} label={t("清空标签筛选")} disabled={disabled} onClick={() => change([])} />}
    <div className="ml-auto flex items-center gap-1">
      <Select value={sort} disabled={disabled} onValueChange={next => runUiCommand("liked-sort", { sort: next })}>
        <SelectTrigger size="sm" aria-label={t("喜欢图片排序")} data-tooltip-hover-only="" data-tooltip={sort === "score" ? t("偏好评分使用图片缓存，点击刷新后更新。") : t("按时间从新到旧排列。")}><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="latest">{t("最新优先")}</SelectItem><SelectItem value="score">{t("偏好评分")}</SelectItem></SelectContent>
      </Select>
    </div>
  </div>;
}
