import { t, tr, messageKey } from "../i18n/index.mjs";
import { useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Button } from "./ui/button";

type Choice = { id: string; text: string; categories?: string[]; enabled?: boolean };
type PickerOptions = { label: string; placeholder?: string; emptyText?: string; initialValue?: string; choices: (query: string) => Choice[]; onQuery: (query: string, id?: string) => void; onSelect?: (id: string) => void; onEmptyBackspace?: () => void };
export const pickers = new WeakMap<HTMLElement, PickerOptions>();
export function createTagPicker(options: PickerOptions) {
  const element = document.createElement("div");
  element.dataset.tagPicker = "";
  pickers.set(element, options);
  return element;
}
export function TagPicker({ source }: { source: HTMLElement }) {
  const options = pickers.get(source)!;
  const [query, setQuery] = useState(options.initialValue ?? "");
  const [open, setOpen] = useState(false);
  const choices = options.choices(query);
  return <Command shouldFilter={false} className="overflow-visible bg-transparent p-0">
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild><div className="flex min-w-0 items-center gap-1">
        <div className="min-w-0 flex-1"><CommandInput value={query} aria-label={t(messageKey(options.label))} aria-expanded={open} placeholder={t(messageKey(options.placeholder ?? "选择或输入标签、ID、类目…"))} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onKeyDown={event => {
          if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
            if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); }
            return;
          }
          if (event.key === "Backspace" && !query && options.onEmptyBackspace) {
            event.preventDefault(); event.stopPropagation(); options.onEmptyBackspace(); setOpen(false);
          }
        }} onValueChange={(value: string) => { setQuery(value); options.onQuery(value); setOpen(true); }} /></div>
        <PopoverTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={tr`展开${t(messageKey(options.label))}`}><ChevronsUpDown /></Button></PopoverTrigger>
      </div></PopoverAnchor>
      <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-72 p-0" onOpenAutoFocus={(event: Event) => event.preventDefault()} onInteractOutside={(event: Event) => { if (source.contains(event.target as Node)) event.preventDefault(); }}>
        <CommandList aria-label={t(messageKey(options.label))}>
          <CommandEmpty>{t(messageKey(options.emptyText ?? "没有匹配的已有标签"))}</CommandEmpty>
          <CommandGroup>{choices.map(choice => <CommandItem key={choice.id} value={choice.id} onSelect={() => {
            if (!open) return;
            if (options.onSelect) { options.onSelect(choice.id); setQuery(""); options.onQuery(""); }
            else { setQuery(choice.text); options.onQuery(choice.text, choice.id); }
            setOpen(false);
          }}>
            <span className="min-w-0"><span className="block">{choice.text}</span><span className="block text-xs text-muted-foreground">{choice.categories?.join(", ")}{choice.enabled === false ? t(" · 已停用") : ""}</span></span>
          </CommandItem>)}</CommandGroup>
        </CommandList>
      </PopoverContent>
    </Popover>
  </Command>;
}
