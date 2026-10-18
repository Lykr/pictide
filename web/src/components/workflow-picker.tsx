import { t } from "../i18n/index.mjs";
import { useLayoutEffect, useRef, useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Button } from "./ui/button";

/** Official editable combobox, backed by the controller's mode and name fields. */
export function WorkflowPicker({ source, host, emit }: { source: HTMLElement; host: HTMLElement; emit: (source: HTMLElement) => void }) {
  const mode = source.querySelector<HTMLSelectElement>("select")!;
  const name = source.querySelector<HTMLInputElement>("input")!;
  const [open, setOpen] = useState(false);
  const [filtering, setFiltering] = useState(false);
  const [activeItem, setActiveItem] = useState(mode.value);
  const input = useRef<HTMLInputElement>(null);
  // cmdk assumes its list is always visible; this combobox uses a Popover.
  useLayoutEffect(() => { input.current?.setAttribute("aria-expanded", String(open)); if (input.current) input.current.id = "workflow-name--control"; });
  useLayoutEffect(() => { if (open && !filtering) setActiveItem(mode.value); }, [open, filtering, mode.value]);
  const value = mode.value === "default" ? t("默认文生图") : name.value;
  const options = [...mode.options].filter(option => !filtering || option.value.startsWith("saved:") && option.text.toLocaleLowerCase().includes(value.toLocaleLowerCase()));
  return <Command shouldFilter={false} value={activeItem} onValueChange={setActiveItem} className="workflow-picker overflow-visible bg-transparent p-0">
    <Popover open={open} onOpenChange={next => { setOpen(next); if (!next) setFiltering(false); }}>
      <PopoverAnchor asChild><div className="flex min-w-0 items-center gap-1">
        <div className="min-w-0 flex-1"><CommandInput ref={input} value={value} aria-label={t("工作流")} aria-expanded={open} placeholder={t("选择工作流或输入名称")} maxLength={120} disabled={mode.disabled} required={name.required} onFocus={() => { setFiltering(false); setOpen(true); }} onKeyDown={event => { if (event.key === "ArrowDown") setOpen(true); }} onValueChange={text => {
          if (mode.value === "default") { mode.value = "custom"; emit(mode); }
          name.value = text; emit(name); setFiltering(true); setActiveItem("__draft-name"); setOpen(true);
        }} /></div>
        <PopoverTrigger asChild><Button variant="ghost" size="icon-sm" disabled={mode.disabled} aria-label={t("展开工作流列表")} onClick={() => setFiltering(false)}><ChevronsUpDown /></Button></PopoverTrigger>
      </div></PopoverAnchor>
      <PopoverContent align="start" className="max-w-[calc(100vw-24px)] p-0" style={{ width: host.getBoundingClientRect().width }} onOpenAutoFocus={event => event.preventDefault()} onInteractOutside={event => { if (host.contains(event.target as Node)) event.preventDefault(); }}>
        <CommandList aria-label={t("工作流列表")}><CommandEmpty>{t("没有匹配的工作流")}</CommandEmpty><CommandGroup>{filtering && value.trim() && <CommandItem value="__draft-name" onSelect={() => { setOpen(false); setFiltering(false); }}>{t("使用名称「{name}」", { name: value.trim() })}</CommandItem>}{options.map(option => <CommandItem key={option.value} value={option.value} onSelect={() => { mode.value = option.value; emit(mode); setOpen(false); setFiltering(false); }}>
          {option.value === "default" ? t("默认文生图") : option.value === "custom" ? t("自定义 API 工作流") : option.text}
        </CommandItem>)}</CommandGroup></CommandList>
      </PopoverContent>
    </Popover>
  </Command>;
}
