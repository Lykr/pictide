import { useLayoutEffect, useSyncExternalStore, useRef } from "react";
import { createPortal, flushSync } from "react-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Checkbox } from "./ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { pickers, TagPicker } from "./tag-picker";
import { WorkflowPicker } from "./workflow-picker";

type Source = HTMLSelectElement | HTMLInputElement | HTMLDetailsElement | HTMLDialogElement | HTMLElement;
type Control = { source: Source; host: HTMLSpanElement; kind: string; key: number; content?: Node[]; summary?: HTMLElement; summaryNodes?: Node[]; summaryLabel?: string; opener?: HTMLElement | null };
const controls = new Map<Source, Control>();
const listeners = new Set<() => void>();
let revision = 0, serial = 0, queued = false, installed = false;
const patchedOptions = new WeakSet<HTMLOptionElement>();
const snapshot = () => revision;
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
function notify(immediate = false) {
  const update = () => { revision++; for (const listener of listeners) listener(); };
  if (immediate) flushSync(update); else update();
}
function schedule() {
  if (queued) return;
  queued = true;
  queueMicrotask(() => { queued = false; discover(); notify(); });
}
function property(source: HTMLElement, name: string) {
  let owner: object | null = source, descriptor: PropertyDescriptor | undefined;
  while (owner && !descriptor) { descriptor = Object.getOwnPropertyDescriptor(owner, name); owner = Object.getPrototypeOf(owner); }
  if (!descriptor?.get || !descriptor.set) return;
  Object.defineProperty(source, name, { configurable: true, get: () => descriptor.get!.call(source), set(value) { descriptor.set!.call(source, value); schedule(); } });
}
function title(source: HTMLElement) {
  const explicit = source.getAttribute("aria-label");
  if (explicit) return explicit;
  const label = source.closest("label") ?? (source.id ? document.querySelector(`label[for="${CSS.escape(source.id)}"]`) : null);
  if (!label) return "选择";
  const copy = label.cloneNode(true) as HTMLElement;
  copy.querySelectorAll("input,select,textarea,button,[data-control-host],[data-help]").forEach(node => node.remove());
  return copy.textContent?.trim() || "选择";
}
function emit(source: HTMLElement) {
  source.dispatchEvent(new Event("input", { bubbles: true }));
  source.dispatchEvent(new Event("change", { bubbles: true }));
  schedule();
}
function trigger(control: Control) { return control.host.querySelector<HTMLElement>("button,[role=combobox]"); }
function register(source: Source, kind: string) {
  if (controls.has(source) || source.hasAttribute("aria-hidden")) return;
  const host = document.createElement("span");
  host.dataset.controlHost = kind;
  source.before(host);
  source.dataset.controlProxy = kind;
  source.tabIndex = -1;
  const control: Control = { source, host, kind, key: ++serial };
  controls.set(source, control);
  if (kind === "dialog" || kind === "collapsible") {
    control.summary = kind === "collapsible" ? source.querySelector<HTMLElement>(":scope > summary") ?? undefined : undefined;
    if (control.summary?.childElementCount) { control.summaryNodes = [...control.summary.childNodes]; control.summaryLabel = control.summary.getAttribute("aria-label") || control.summary.textContent?.trim() || "展开"; }
    control.content = [...source.childNodes].filter(node => node !== control.summary);
    property(source, "open");
    const originalQuery = source.querySelector.bind(source);
    const originalQueryAll = source.querySelectorAll.bind(source);
    Object.defineProperty(source, "querySelector", { value: (selector: string) => originalQuery(selector) ?? host.querySelector(selector), configurable: true });
    Object.defineProperty(source, "querySelectorAll", { value: (selector: string) => host.querySelectorAll(selector).length ? host.querySelectorAll(selector) : originalQueryAll(selector), configurable: true });
  } else if (kind === "tabs" || kind === "toggle") {
    control.content = [...source.children];
  } else if (kind === "workflow") {
    for (const field of source.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input,select")) {
      for (const name of ["value", "disabled", "required", "selectedIndex"]) property(field, name);
      Object.defineProperty(field, "focus", { configurable: true, value: () => trigger(control)?.focus() });
      field.addEventListener("change", schedule);
    }
  } else if (kind === "select" || kind === "checkbox") {
    for (const name of kind === "select" ? ["value", "selectedIndex", "disabled", "required"] : ["checked", "disabled", "required", "indeterminate"]) property(source, name);
    Object.defineProperty(source, "focus", { configurable: true, value: (options?: FocusOptions) => trigger(control)?.focus(options) });
    Object.defineProperty(source, "reportValidity", { configurable: true, value: () => {
      const input = source as HTMLInputElement | HTMLSelectElement;
      if (input.validity.valid) return true;
      trigger(control)?.setAttribute("aria-invalid", "true"); trigger(control)?.focus();
      return false;
    } });
    source.addEventListener("change", schedule);
  }
}
function discover() {
  for (const source of document.querySelectorAll<HTMLSelectElement | HTMLInputElement>("select:not([data-control-proxy]):not([aria-hidden]),input[type=checkbox]:not([data-control-proxy]):not([aria-hidden])")) if (!source.closest("[data-workflow-picker]")) register(source, source.tagName === "SELECT" ? "select" : "checkbox");
  for (const source of document.querySelectorAll<HTMLDetailsElement>("details:not([data-control-proxy])")) register(source, "collapsible");
  for (const source of document.querySelectorAll<HTMLDialogElement>("dialog:not([data-control-proxy])")) register(source, "dialog");
  for (const source of document.querySelectorAll<HTMLElement>(".segmented:not([data-control-proxy])")) register(source, "toggle");
  for (const source of document.querySelectorAll<HTMLElement>(".settings-navigation:not([data-control-proxy])")) register(source, "tabs");
  for (const source of document.querySelectorAll<HTMLElement>("[data-tag-picker]:not([data-control-proxy])")) if (pickers.has(source)) register(source, "picker");
  for (const source of document.querySelectorAll<HTMLElement>("[data-workflow-picker]:not([data-control-proxy])")) register(source, "workflow");
  for (const [source, control] of controls) {
    if (!source.isConnected) { controls.delete(source); control.host.remove(); }
    else {
      control.host.hidden = source.hidden;
      if (source instanceof HTMLSelectElement) for (const option of source.options) if (!patchedOptions.has(option)) { patchedOptions.add(option); property(option, "selected"); }
    }
  }
}

/** One React tree owns official component interactions. Hidden form elements only
 * retain the existing controllers' value/options/checked and validity contracts. */
function install() {
  if (installed) return;
  installed = true;
  const observer = new MutationObserver(mutations => {
    if (mutations.some(mutation => {
      const target = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
      if (target?.closest("[data-control-proxy]") || target?.matches("fieldset")) return true;
      if (mutation.type !== "childList") return false;
      return [...mutation.addedNodes, ...mutation.removedNodes].some(node => node instanceof Element && (node.matches("select,input[type=checkbox],details,dialog,.segmented,.settings-navigation,[data-tag-picker],[data-control-proxy]") || !!node.querySelector("select:not([aria-hidden]),input[type=checkbox]:not([aria-hidden]),details,dialog,[data-tag-picker],[data-control-proxy]")));
    })) schedule();
  });
  observer.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true, attributeFilter: ["disabled", "hidden", "open", "required", "selected", "label", "value", "class", "aria-label", "aria-selected", "aria-pressed"] });
  HTMLDialogElement.prototype.showModal = function () {
    register(this, "dialog");
    const control = controls.get(this)!;
    if (!this.open) control.opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    this.open = true; discover(); notify(true);
  };
  HTMLDialogElement.prototype.close = function (value?: string) {
    if (!this.open) return;
    if (value !== undefined) this.returnValue = value;
    this.open = false; notify(true);
    this.dispatchEvent(new Event("close"));
  };
  document.addEventListener("invalid", event => {
    if (event.target instanceof HTMLElement) {
      const target = event.target;
      let opened = false;
      for (const control of controls.values()) if (control.kind === "collapsible" && control.host.contains(target) && !(control.source as HTMLDetailsElement).open) { (control.source as HTMLDetailsElement).open = true; opened = true; }
      if (opened) notify(true);
    }
    if (event.target instanceof HTMLElement) {
      const control = controls.get(event.target) ?? controls.get(event.target.closest<HTMLElement>("[data-workflow-picker]")!);
      if (control) { event.preventDefault(); trigger(control)?.focus(); }
    }
  }, true);
  discover(); schedule();
}

function SelectControl({ control }: { control: Control }) {
  const source = control.source as HTMLSelectElement;
  const disabled = source.matches(":disabled");
  const empty = `__pictide_empty_${control.key}__`;
  if (source.multiple) return <div data-slot="multi-select" role="group" aria-label={title(source)} className="grid max-h-44 gap-1.5 overflow-y-auto p-1">
    {[...source.options].map((option, index) => <Label key={`${index}:${option.value}`}>
      <Checkbox aria-label={option.label} checked={option.selected} disabled={disabled || option.disabled} onCheckedChange={(checked: boolean | "indeterminate") => { option.selected = checked === true; emit(source); }} /><span className="min-w-0 break-words leading-normal">{option.label}</span>
    </Label>)}
  </div>;
  const selected = source.options[source.selectedIndex];
  return <Select value={selected ? selected.value || empty : ""} disabled={disabled} onValueChange={(value: string) => { source.value = value === empty ? "" : value; emit(source); }}>
    <SelectTrigger id={source.id ? `${source.id}--control` : undefined} className="w-full min-w-0" size={source.dataset.size === "sm" ? "sm" : "default"} aria-label={title(source)} aria-invalid={!source.validity.valid || source.getAttribute("aria-invalid") === "true"} data-tooltip={source.dataset.tooltip}>
      <SelectValue placeholder={source.getAttribute("placeholder") || "选择"} />
    </SelectTrigger>
    <SelectContent position="popper" align="start"><SelectGroup>
      {[...source.options].map((option, index) => <SelectItem key={`${index}:${option.value}`} value={option.value || empty} disabled={option.disabled || option.parentElement instanceof HTMLOptGroupElement && option.parentElement.disabled}>{option.label || "选择"}</SelectItem>)}
    </SelectGroup></SelectContent>
  </Select>;
}
function CheckControl({ control }: { control: Control }) {
  const source = control.source as HTMLInputElement;
  return <Checkbox id={source.id ? `${source.id}--control` : undefined} aria-label={title(source)} aria-invalid={!source.validity.valid || source.getAttribute("aria-invalid") === "true"} checked={source.indeterminate ? "indeterminate" : source.checked} disabled={source.matches(":disabled")} onCheckedChange={(checked: boolean | "indeterminate") => { source.checked = checked === true; emit(source); }} onClick={(event: React.MouseEvent) => event.stopPropagation()} />;
}
function Transplanted({ nodes, className, returnTo }: { nodes: Node[]; className?: string; returnTo: HTMLElement }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const container = ref.current!; container.append(...nodes); schedule();
    return () => { for (const node of nodes) if (node.parentNode === container) returnTo.append(node); };
  }, [nodes, returnTo]);
  return <div ref={ref} className={className} data-controller-content="" />;
}
function CollapsibleControl({ control }: { control: Control }) {
  const source = control.source as HTMLDetailsElement;
  const summary = control.summary;
  return <Collapsible className={source.className} open={source.open} onOpenChange={(open: boolean) => { source.open = open; source.dispatchEvent(new Event("toggle")); }}>
    <CollapsibleTrigger asChild><Button variant="ghost" className="collapsible-label" aria-label={control.summaryLabel || summary?.textContent?.trim() || "展开"} data-tooltip={summary?.dataset.tooltip}>
      {source.open ? <ChevronDown /> : <ChevronRight />}{control.summaryNodes ? <Transplanted nodes={control.summaryNodes} returnTo={summary!} className="contents" /> : summary?.textContent}
    </Button></CollapsibleTrigger>
    <CollapsibleContent forceMount hidden={!source.open}><Transplanted nodes={control.content!} returnTo={source} /></CollapsibleContent>
  </Collapsible>;
}
function DialogControl({ control }: { control: Control }) {
  const source = control.source as HTMLDialogElement;
  const content = useRef<HTMLDivElement>(null);
  const contain = (event: Event & { detail?: { originalEvent?: Event } }) => {
    const target = event.detail?.originalEvent?.target ?? event.target;
    if (target instanceof Node && content.current?.contains(target) || target instanceof Element && target.closest("[data-slot=select-content],[data-slot=popover-content],[data-slot=tooltip-content]")) event.preventDefault();
  };
  return <Dialog open={source.open} onOpenChange={(open: boolean) => {
    if (open) return;
    const event = new Event("cancel", { cancelable: true }); source.dispatchEvent(event);
    if (!event.defaultPrevented) source.close();
  }}>
    <DialogContent ref={content} className={`${source.className} controller-dialog`} aria-describedby={undefined} showCloseButton={false} onInteractOutside={contain} onPointerDownOutside={contain} onCloseAutoFocus={(event: Event) => { event.preventDefault(); control.opener?.focus(); }}>
      <DialogTitle asChild><span className="sr-only">{source.getAttribute("aria-label") || control.content?.map(node => node instanceof Element ? node.querySelector("h2,h3")?.textContent || (node.matches("h2,h3") ? node.textContent : "") : "").join("").trim() || "编辑"}</span></DialogTitle>
      <Transplanted nodes={control.content!} returnTo={source} className="dialog-scroll-content" />
    </DialogContent>
  </Dialog>;
}
function ToggleControl({ control }: { control: Control }) {
  const source = control.source as HTMLElement;
  const buttons = (control.content ?? []).filter((node): node is HTMLButtonElement => node instanceof HTMLButtonElement);
  const active = buttons.findIndex(button => button.getAttribute("aria-pressed") === "true");
  return <ToggleGroup type="single" value={String(active)} size="sm" aria-label={source.getAttribute("aria-label") || "切换视图"} onValueChange={(value: string) => { if (value !== "") buttons[Number(value)]?.click(); }}>
    {buttons.map((button, index) => <ToggleGroupItem key={index} value={String(index)} disabled={button.disabled}>{button.textContent}</ToggleGroupItem>)}
  </ToggleGroup>;
}
function TabsControl({ control }: { control: Control }) {
  const buttons = (control.content ?? []).filter((node): node is HTMLButtonElement => node instanceof HTMLButtonElement);
  const active = buttons.findIndex(button => button.classList.contains("active"));
  return <Tabs value={String(active)} orientation="horizontal" onValueChange={(value: string) => buttons[Number(value)]?.click()}>
    <TabsList aria-label={control.source.getAttribute("aria-label") || "设置分类"}>{buttons.map((button, index) => <TabsTrigger key={index} value={String(index)} disabled={button.disabled}>{button.textContent}</TabsTrigger>)}</TabsList>
  </Tabs>;
}
export function ControlLayer() {
  useSyncExternalStore(subscribe, snapshot);
  useLayoutEffect(install, []);
  return <>{[...controls.values()].map(control => createPortal(
    control.kind === "select" ? <SelectControl control={control} /> : control.kind === "checkbox" ? <CheckControl control={control} /> : control.kind === "dialog" ? <DialogControl control={control} /> : control.kind === "toggle" ? <ToggleControl control={control} /> : control.kind === "tabs" ? <TabsControl control={control} /> : control.kind === "picker" ? <TagPicker source={control.source} /> : control.kind === "workflow" ? <WorkflowPicker source={control.source} host={control.host} emit={emit} /> : <CollapsibleControl control={control} />,
    control.host, String(control.key)))}</>;
}
