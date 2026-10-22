import type { ComponentProps, ReactNode } from "react";
import { cn } from "../lib/utils";
import "../styles/settings-row.css";

type Props = ComponentProps<"div"> & {
  label: ReactNode;
  stackOnMobile?: boolean;
  separated?: boolean;
};

export function SettingsRow({ label, children, stackOnMobile = false, separated = false, className, ...props }: Props) {
  return <div {...props} className={cn("settings-row", className)} data-stack-mobile={stackOnMobile} data-separated={separated}>
    <div className="settings-row-caption">{label}</div>
    <div className="settings-row-control">{children}</div>
  </div>;
}
