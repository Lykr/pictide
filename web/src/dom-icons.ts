// Reuse the installed Lucide SVG data for controller-owned controls.
import { __iconNode as Plus } from "lucide-react/dist/esm/icons/plus.js";
import { __iconNode as Copy } from "lucide-react/dist/esm/icons/copy.js";
import { __iconNode as Trash2 } from "lucide-react/dist/esm/icons/trash-2.js";
import { __iconNode as Save } from "lucide-react/dist/esm/icons/save.js";
import { __iconNode as ChevronUp } from "lucide-react/dist/esm/icons/chevron-up.js";
import { __iconNode as ChevronDown } from "lucide-react/dist/esm/icons/chevron-down.js";
import { __iconNode as RefreshCw } from "lucide-react/dist/esm/icons/refresh-cw.js";
import { __iconNode as Play } from "lucide-react/dist/esm/icons/play.js";
import { __iconNode as Shuffle } from "lucide-react/dist/esm/icons/shuffle.js";
import { __iconNode as Eye } from "lucide-react/dist/esm/icons/eye.js";
import { __iconNode as X } from "lucide-react/dist/esm/icons/x.js";
import { __iconNode as Check } from "lucide-react/dist/esm/icons/check.js";
import { __iconNode as ArrowUp } from "lucide-react/dist/esm/icons/arrow-up.js";
import { __iconNode as ArrowDown } from "lucide-react/dist/esm/icons/arrow-down.js";
import { __iconNode as ArrowLeft } from "lucide-react/dist/esm/icons/arrow-left.js";
import { __iconNode as ArrowRight } from "lucide-react/dist/esm/icons/arrow-right.js";
import { __iconNode as CircleHelp } from "lucide-react/dist/esm/icons/circle-question-mark.js";
import { __iconNode as Settings } from "lucide-react/dist/esm/icons/settings.js";
import { __iconNode as Clock } from "lucide-react/dist/esm/icons/clock.js";
import { __iconNode as CircleCheck } from "lucide-react/dist/esm/icons/circle-check.js";
import { __iconNode as CircleX } from "lucide-react/dist/esm/icons/circle-x.js";
import { __iconNode as LoaderCircle } from "lucide-react/dist/esm/icons/loader-circle.js";
import { __iconNode as CircleSlash } from "lucide-react/dist/esm/icons/circle-slash.js";

import { __iconNode as GripVertical } from "lucide-react/dist/esm/icons/grip-vertical.js";

const icons: Record<string, [string, Record<string, string>][] > = { GripVertical, Plus, Copy, Trash2, Save, ChevronUp, ChevronDown, RefreshCw, Play, Shuffle, Eye, X, Check, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, CircleHelp, Settings, Clock, CircleCheck, CircleX, LoaderCircle, CircleSlash };
export function createIcon(name: string): SVGSVGElement {
  const nodes = icons[name];
  if (!nodes) throw new Error(`Unknown action icon: ${name}`);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false" })) svg.setAttribute(key, value);
  for (const [tag, attrs] of nodes) {
    const child = document.createElementNS(svg.namespaceURI, tag);
    for (const [key, value] of Object.entries(attrs)) if (key !== "key") child.setAttribute(key, value);
    svg.append(child);
  }
  return svg;
}
