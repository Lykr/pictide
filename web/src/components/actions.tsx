import { useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { CircleHelp, type LucideIcon } from "lucide-react";
import { Button } from "./ui/button";

export function IconButton({ icon: Icon, label, tooltip = label, ...props }: ComponentProps<typeof Button> & { icon: LucideIcon; label: string; tooltip?: string }) {
  return <Button type="button" variant="ghost" size="icon-sm" {...props} aria-label={label} data-tooltip={tooltip}>
    <Icon aria-hidden="true" />
  </Button>;
}

export function HelpTip({ text, children, ...props }: ComponentProps<typeof Button> & { text: string; children?: ReactNode }) {
  return <Button type="button" variant="ghost" size="icon-xs" className="help-tip" {...props} aria-label={text} data-help="" data-tooltip={text}>
    {children ?? <CircleHelp size={14} aria-hidden="true" />}
  </Button>;
}

type Target = { node: HTMLElement; text: string; rect: DOMRect; container: HTMLElement };

/** One Radix tooltip bridge for React and controller-owned DOM. The bridge
 * reuses the official Tooltip for React and controller-owned controls. */
export function TooltipLayer() {
  const [target, setTarget] = useState<Target | null>(null);
  useEffect(() => {
    let pending: ReturnType<typeof setTimeout> | undefined;
    let active: HTMLElement | null = null;
    let previousDescription: string | null = null;
    let activeObserver: MutationObserver | undefined;
    const find = (node: EventTarget | null) => node instanceof Element ? node.closest<HTMLElement>("[data-tooltip]") : null;
    const hide = () => {
      clearTimeout(pending);
      activeObserver?.disconnect();
      if (active) {
        if (previousDescription === null) active.removeAttribute("aria-describedby");
        else active.setAttribute("aria-describedby", previousDescription);
      }
      active = null;
      setTarget(null);
    };
    const show = (node: HTMLElement) => {
      hide();
      const text = node.dataset.tooltip;
      if (!text || !node.isConnected || node.closest("[hidden],[inert]")) return;
      active = node;
      activeObserver = new MutationObserver(() => show(node));
      activeObserver.observe(node, { attributes: true, attributeFilter: ['data-tooltip'] });
      previousDescription = node.getAttribute("aria-describedby");
      node.setAttribute("aria-describedby", [previousDescription, "pictide-tooltip"].filter(Boolean).join(" "));
      setTarget({ node, text, rect: node.getBoundingClientRect(), container: node.closest<HTMLElement>("[data-slot=dialog-content],dialog[open],.image-card.immersive") ?? document.body });
    };
    const over = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      if (event.target instanceof Element && event.target.closest("#pictide-tooltip")) { clearTimeout(pending); return; }
      const node = find(event.target);
      if (!node || node === find(event.relatedTarget)) return;
      clearTimeout(pending);
      pending = setTimeout(() => show(node), 300);
    };
    const out = (event: PointerEvent) => {
      if (event.relatedTarget instanceof Element && event.relatedTarget.closest("#pictide-tooltip")) return;
      const fromTooltip = event.target instanceof Element && event.target.closest("#pictide-tooltip");
      if ((fromTooltip && find(event.relatedTarget) !== active) || find(event.target) !== find(event.relatedTarget)) {
        clearTimeout(pending);
        pending = setTimeout(hide, 150);
      }
    };
    const focus = (event: FocusEvent) => { const node = find(event.target); if (node && !node.hasAttribute("data-tooltip-hover-only")) show(node); else hide(); };
    const click = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("#pictide-tooltip")) return;
      const node = find(event.target);
      if (node?.hasAttribute("data-help")) {
        event.preventDefault();
        show(node);
      } else hide();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") hide();
      if (event.key === "Enter" || event.key === " ") {
        const node = find(event.target);
        if (node?.hasAttribute("data-help")) {
          event.preventDefault();
          show(node);
        }
      }
    };
    document.addEventListener("pointerover", over);
    document.addEventListener("pointerout", out);
    document.addEventListener("focusin", focus);
    document.addEventListener("focusout", hide);
    document.addEventListener("click", click);
    document.addEventListener("keydown", key);
    document.addEventListener("scroll", hide, true);
    document.addEventListener("close", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      hide();
      document.removeEventListener("pointerover", over);
      document.removeEventListener("pointerout", out);
      document.removeEventListener("focusin", focus);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("click", click);
      document.removeEventListener("keydown", key);
      document.removeEventListener("scroll", hide, true);
      document.removeEventListener("close", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, []);
  if (!target) return null;
  return createPortal(<TooltipProvider delayDuration={0}>
    <Tooltip open>
      <TooltipTrigger asChild>
        <span aria-hidden="true" tabIndex={-1} style={{ position: "fixed", pointerEvents: "none", left: target.rect.left, top: target.rect.top, width: target.rect.width, height: target.rect.height }} />
      </TooltipTrigger>
        <TooltipContent container={target.container} id="pictide-tooltip" className="z-[100] max-w-[min(300px,calc(100vw-24px))] whitespace-normal break-words leading-relaxed select-text" side="top" sideOffset={7} collisionPadding={12}>
          {target.text}
        </TooltipContent>
    </Tooltip>
  </TooltipProvider>, document.body);
}
