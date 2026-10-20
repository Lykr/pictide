import { useLayoutEffect, useMemo, useState, type ComponentProps, type RefObject } from "react";
import { cn } from "../lib/utils";
import { PopoverAnchor, PopoverContent } from "./ui/popover";
import "../styles/image-toolbar-popover.css";

type Props = ComponentProps<typeof PopoverContent> & {
  immersive: boolean;
  triggerRef: RefObject<HTMLButtonElement | null>;
};

// Keep Radix's focus/dismissal behavior, using the entire toolbar in immersion.
export function ImageToolbarPopover({ immersive, triggerRef, className, container, align, sideOffset, avoidCollisions, ...props }: Props) {
  const [toolbar, setToolbar] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    setToolbar(immersive ? triggerRef.current?.closest<HTMLElement>(".image-toolbar") ?? null : null);
  }, [immersive, triggerRef]);
  const anchor = useMemo(() => toolbar ? { current: toolbar } : undefined, [toolbar]);
  return <>
    {anchor && <PopoverAnchor virtualRef={anchor} />}
    <PopoverContent {...props}
      container={toolbar?.closest<HTMLElement>(".image-card") ?? container}
      align={immersive ? "center" : align} side="top"
      sideOffset={immersive ? 12 : sideOffset}
      avoidCollisions={immersive ? false : avoidCollisions}
      collisionPadding={12}
      className={cn(className, immersive && "image-toolbar-popover")} />
  </>;
}
