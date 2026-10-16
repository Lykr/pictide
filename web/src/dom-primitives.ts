import { buttonVariants } from "./components/ui/button";
import { inputClassName } from "./components/ui/input";
import { textareaClassName } from "./components/ui/textarea";
import { nativeSelectClassName } from "./components/ui/native-select";
import { badgeVariants } from "./components/ui/badge";
import { cn } from "./lib/utils";
import { createIcon } from "./dom-icons";
export { createIcon } from "./dom-icons";

export function setAction(node: HTMLElement, icon: string, label: string, text?: string) {
  node.setAttribute("aria-label", label);
  node.dataset.tooltip = label;
  const size = node.hasAttribute("data-help") ? "icon-xs" : text ? "sm" : "icon-sm";
  node.dataset.size = size;
  node.className = cn(node.className, buttonVariants({ variant: (node.dataset.variant || "ghost") as "ghost", size }));
  node.replaceChildren(createIcon(icon));
  if (text) {
    const caption = document.createElement("span");
    caption.dataset.actionLabel = "";
    caption.textContent = text;
    node.append(caption);
  }
  return node;
}

/** Apply the same shadcn primitives to imperative editor nodes without
 * transferring their events, state or native validity into React. */
export function decorateElement(node: HTMLElement, tag: string, props: Record<string, unknown>) {
  const tokens = new Set(String(props.class ?? "").split(/\s+/));
  let classes = "";
  if (tag === "button") {
    const variant = tokens.has("help-tip") ? "ghost" : tokens.has("primary") ? "default" : tokens.has("danger") ? "destructive"
      : tokens.has("link") || tokens.has("slot-name") || tokens.has("category-option") ? "ghost" : "outline";
    const size = tokens.has("help-tip") ? "icon-xs" : "default";
    classes = buttonVariants({ variant, size });
    node.dataset.slot = "button";
    node.dataset.variant = variant;
    node.dataset.size = size;
    if (!("type" in props)) (node as HTMLButtonElement).type = "button";
  } else if (tag === "input" && props.type !== "checkbox" && props.type !== "radio") {
    classes = inputClassName;
    node.dataset.slot = "input";
  } else if (tag === "textarea") {
    classes = textareaClassName;
    node.dataset.slot = "textarea";
  } else if (tag === "select") {
    classes = nativeSelectClassName;
    node.dataset.slot = "native-select";
    node.dataset.size = "default";
  } else if (tag === "span" && tokens.has("badge")) {
    node.className = cn(badgeVariants({ variant: "outline" }), node.className);
    node.dataset.slot = "badge";
    node.dataset.variant = "outline";
    return node;
  } else if (tag === "label") {
    node.dataset.slot = "label";
  }
  if (classes) node.className = `${classes} ${node.className}`.trim();
  return node;
}
