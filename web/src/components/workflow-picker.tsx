import { t } from "../i18n/index.mjs";
import { useLayoutEffect, useRef, useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "./ui/command";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "./ui/popover";
import { Button } from "./ui/button";

/** Editable workflow selector with explicit draft values and callbacks. */
export function WorkflowPicker({ mode, name, options, disabled, onModeChange, onNameChange }: {
  mode: string; name: string; options: { value: string; text: string }[]; disabled?: boolean;
  onModeChange: (value: string) => void; onNameChange: (value: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [filtering, setFiltering] = useState(false);
  const [activeItem, setActiveItem] = useState(mode);
  const input = useRef<HTMLInputElement>(null);
  // cmdk assumes its list is always visible; this combobox uses a Popover.
  useLayoutEffect(() => { input.current?.setAttribute("aria-expanded", String(open)); if (input.current) input.current.id = "workflow-name--control"; });
  useLayoutEffect(() => { if (open && !filtering) setActiveItem(mode); }, [open, filtering, mode]);
  const value = mode === "default" ? t("默认文生图") : name;
  const choices = options.filter(option => !filtering || option.value.startsWith("saved:") && option.text.toLocaleLowerCase().includes(value.toLocaleLowerCase()));
  return <Command ref={host} shouldFilter={false} value={activeItem} onValueChange={setActiveItem} className="workflow-picker overflow-visible bg-transparent p-0">
    <Popover open={open} onOpenChange={next => { setOpen(next); if (!next) setFiltering(false); }}>
      <PopoverAnchor asChild><div className="flex min-w-0 items-center gap-1">
        <div className="min-w-0 flex-1"><CommandInput ref={input} value={value} aria-label={t("工作流")} aria-expanded={open} placeholder={t("选择工作流或输入名称")} maxLength={120} disabled={disabled} required={mode !== 'default'} onFocus={() => { setFiltering(false); setOpen(true); }} onKeyDown={event => { if (event.key === "ArrowDown") setOpen(true); }} onValueChange={text => {
          if (mode === "default") { onModeChange("custom"); }
          onNameChange(text); setFiltering(true); setActiveItem("__draft-name"); setOpen(true);
        }} /></div>
        <PopoverTrigger asChild><Button variant="ghost" size="icon-sm" disabled={disabled} aria-label={t("展开工作流列表")} onClick={() => setFiltering(false)}><ChevronsUpDown /></Button></PopoverTrigger>
      </div></PopoverAnchor>
      <PopoverContent align="start" className="max-w-[calc(100vw-24px)] p-0" style={{ width: host.current?.getBoundingClientRect()?.width }} onOpenAutoFocus={event => event.preventDefault()} onInteractOutside={event => { if (host.current?.contains(event.target as Node)) event.preventDefault(); }}>
        <CommandList aria-label={t("工作流列表")}><CommandEmpty>{t("没有匹配的工作流")}</CommandEmpty><CommandGroup>{filtering && value.trim() && <CommandItem value="__draft-name" onSelect={() => { setOpen(false); setFiltering(false); }}>{t("使用名称「{name}」", { name: value.trim() })}</CommandItem>}{choices.map(option => <CommandItem key={option.value} value={option.value} onSelect={() => { onModeChange(option.value); setOpen(false); setFiltering(false); }}>
          {option.value === "default" ? t("默认文生图") : option.value === "custom" ? t("自定义 API 工作流") : option.text}
        </CommandItem>)}</CommandGroup></CommandList>
      </PopoverContent>
    </Popover>
  </Command>;
}
