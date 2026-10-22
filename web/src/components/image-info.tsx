import { onSignal, offSignal } from '../shared/signals.mjs';
import { useUiFact } from '../shared/application-context';
import { t } from "../i18n/index.mjs";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { getUiState, subscribeUiState } from "../shared/ui-state.mjs";
import { Download, Info } from "lucide-react";
import { IconButton } from "./actions";
import { Button } from "./ui/button";
import { Popover, PopoverTrigger } from "./ui/popover";
import { ImageToolbarPopover } from "./image-toolbar-popover";
import { ImagePromptDetails } from "./image-prompt-details";

type ImageDetails = { id: string; seed: string; positive: string; negative: string };

export function ImageInfo() {
  const image: ImageDetails | null = useUiFact("imageInfo");
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const immersive = useSyncExternalStore(subscribeUiState, () => (getUiState() as Record<string, unknown>).roamImmersive === true);
  useEffect(() => {
    const close = () => setOpen(false);
    onSignal("close-image-info", close);
    return () => {
        offSignal("close-image-info", close);
    };
  }, []);
  return <>
    <Popover open={open && !!image} onOpenChange={setOpen}>
    <PopoverTrigger asChild><IconButton ref={triggerRef} icon={Info} label={t("图片信息")} disabled={!image} /></PopoverTrigger>
    <ImageToolbarPopover immersive={immersive} triggerRef={triggerRef} className="image-info-popover image-details-popover" align="start" aria-label={t("图片信息")}>
      {image && <ImagePromptDetails key={image.id} imageId={image.id} active={open && !!image} seed={image.seed} positive={image.positive} negative={image.negative}
        actions={<Button asChild variant="ghost" size="icon-sm"><a href={`/api/artifacts/${encodeURIComponent(image.id)}/prompts`} aria-label={t("下载提示词 JSON")} data-tooltip={t("下载提示词 JSON")} download><Download aria-hidden="true" /></a></Button>} />}
    </ImageToolbarPopover>
    </Popover>
  </>;
}
