import { forwardRef, type ComponentProps, type ReactNode } from "react";
import { cn } from "../lib/utils";
import "../styles/image-toolbar.css";

type Props = Omit<ComponentProps<"div">, "children"> & {
  information: ReactNode;
  navigation: ReactNode;
  trailing?: ReactNode;
};

// Slots own placement; callers own actions and their state.
export const ImageToolbar = forwardRef<HTMLDivElement, Props>(function ImageToolbar(
  { information, navigation, trailing, className, ...props }, ref,
) {
  return <div {...props} ref={ref} className={cn("image-toolbar", className)} data-image-toolbar="">
    <div className="image-info" data-toolbar-slot="information">{information}</div>
    <div className="image-navigation" data-toolbar-slot="navigation">{navigation}</div>
    {trailing && <div className="image-anchor" data-toolbar-slot="trailing">{trailing}</div>}
  </div>;
});
